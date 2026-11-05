import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { evaluateSourceHealth, REQUIRED_SOURCE_IDS, SOURCE_STALE_AFTER_SECONDS, sourceIdsForOpportunity } from '../api/_sourceHealth.js'
import statusHandler, { snapshotFreshness } from '../api/status.js'
import { clearVerifiedSnapshotCacheForTests, setDurableSnapshotSourceForTests } from '../api/_verifiedSnapshot.js'

const now = Date.parse('2026-11-05T08:00:00Z')
function healthyMetadata() {
  return {
    schema_version: '0.1',
    sources: Object.fromEntries(REQUIRED_SOURCE_IDS.map((id) => [id, {
      last_successful_scan_at: new Date(now - 60_000).toISOString(),
      last_attempt_at: new Date(now - 60_000).toISOString(),
      stale_after_seconds: SOURCE_STALE_AFTER_SECONDS[id],
      failure_reason: null,
    }])),
  }
}
const snapshot = { snapshot_as_of: new Date(now).toISOString(), source_health: healthyMetadata() }
const unchanged = structuredClone(snapshot)
assert.equal(evaluateSourceHealth(snapshot, now).status, 'HEALTHY')
assert.deepEqual(snapshot, unchanged, 'evaluation must not mutate committed metadata')

const stale = structuredClone(snapshot)
stale.source_health.sources.tjzyefy.last_successful_scan_at = new Date(now - 25 * 3600_000).toISOString()
assert.equal(snapshotFreshness(stale.snapshot_as_of, now).freshness, 'FRESH')
assert.equal(evaluateSourceHealth(stale, now).sources.tjzyefy.status, 'STALE', 'a different source publish cannot refresh this source')
assert.equal(evaluateSourceHealth(stale, now).status, 'STALE')
assert.equal(evaluateSourceHealth({ snapshot_as_of: new Date(now).toISOString() }, now).status, 'UNKNOWN')

for (const invalid of [null, 0, -1, '86400', 100000000]) {
  const sample = structuredClone(snapshot)
  sample.source_health.sources.tjzyefy.stale_after_seconds = invalid
  assert.equal(evaluateSourceHealth(sample, now).sources.tjzyefy.status, 'UNKNOWN')
}
for (const invalid of [null, 'not-a-date', '2026-11-05T08:00:00', '2026-11-05T08:16:00Z']) {
  const sample = structuredClone(snapshot)
  sample.source_health.sources.tjzyefy.last_successful_scan_at = invalid
  assert.equal(evaluateSourceHealth(sample, now).sources.tjzyefy.status, 'UNKNOWN')
}
const failed = structuredClone(snapshot)
failed.source_health.sources.tjzyefy.last_attempt_at = new Date(now).toISOString()
failed.source_health.sources.tjzyefy.failure_reason = 'INDEX_SCAN_FAILED'
assert.equal(evaluateSourceHealth(failed, now).sources.tjzyefy.status, 'FAILING')
assert.equal(evaluateSourceHealth(failed, now).sources.tjzyefy.age_seconds, 60)
delete failed.source_health.sources.tjzyefy
assert.equal(evaluateSourceHealth(failed, now).sources.tjzyefy.status, 'UNKNOWN')

for (const [id, expected] of [
  ['tjzyefy_intent_1', ['tjzyefy_intent']], ['tjzyefy_1', ['tjzyefy']],
  ['tjfch_1', ['tjfch', 'tjfch_test']], ['ccgp_tj_1', ['ccgp']],
  ['ccgp_bj_1', ['regional_bj']], ['ccgp_hl_1', ['regional_hl']], ['unknown_1', []],
]) assert.deepEqual(sourceIdsForOpportunity({ opportunity_id: id }), expected)
assert.deepEqual(sourceIdsForOpportunity({ opportunity_id: 'tjfch_1', source_id: 'tjfch_test' }), ['tjfch_test'])
assert.deepEqual(sourceIdsForOpportunity({ opportunity_id: 'tjzyefy_1', source_id: 'unknown' }), [])

const savedNow = Date.now
const savedRemote = process.env.VERIFIED_SNAPSHOT_URL
const savedPublicRemote = process.env.VITE_VERIFIED_SNAPSHOT_URL
try {
  Date.now = () => now
  process.env.VERIFIED_SNAPSHOT_URL = ''
  process.env.VITE_VERIFIED_SNAPSHOT_URL = ''
  const raw = JSON.parse(readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'))
  for (const [metadata, degraded] of [[healthyMetadata(), false], [stale.source_health, true], [undefined, true]]) {
    const payload = { ...structuredClone(raw), snapshot_as_of: new Date(now).toISOString() }
    if (metadata) payload.source_health = metadata
    else delete payload.source_health
    setDurableSnapshotSourceForTests(async () => ({ snapshot_hash: 'a'.repeat(64), payload }))
    const response = {
      setHeader() {}, status(code) { this.statusCode = code; return this },
      json(body) { this.body = body; return this },
    }
    await statusHandler({ method: 'GET' }, response)
    assert.equal(response.statusCode, 200)
    assert.equal(response.body.ready, true, 'readable and fresh are separate axes')
    assert.equal(response.body.snapshot.freshness, 'FRESH')
    assert.equal(response.body.snapshot.source_mode, 'DATABASE')
    assert.equal(response.body.degraded, degraded)
  }
} finally {
  Date.now = savedNow
  setDurableSnapshotSourceForTests(null)
  clearVerifiedSnapshotCacheForTests()
  if (savedRemote === undefined) delete process.env.VERIFIED_SNAPSHOT_URL
  else process.env.VERIFIED_SNAPSHOT_URL = savedRemote
  if (savedPublicRemote === undefined) delete process.env.VITE_VERIFIED_SNAPSHOT_URL
  else process.env.VITE_VERIFIED_SNAPSHOT_URL = savedPublicRemote
}
console.log('Committed snapshot source health checks: PASS')
