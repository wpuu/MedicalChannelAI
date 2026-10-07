import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import handler from '../api/ai/analyze.js'
import { snapshotCoverageAutomationError } from '../api/ai/_analyzeCore.js'
import { clearVerifiedSnapshotCacheForTests } from '../api/_verifiedSnapshot.js'

const snapshot = JSON.parse(readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'))
const opportunityId = snapshot.cards[0].opportunity_id
snapshot.snapshot_as_of = new Date().toISOString()
snapshot.collection_coverage = {
  complete: false,
  last_complete_as_of: null,
  updated_source_ids: ['tjnothop'],
  failed_source_ids: ['tjmugh'],
}

assert.equal(snapshotCoverageAutomationError(snapshot), 'VERIFIED_SNAPSHOT_COVERAGE_INCOMPLETE')
assert.equal(snapshotCoverageAutomationError({ snapshot_as_of: snapshot.snapshot_as_of }), null)
assert.equal(snapshotCoverageAutomationError({ collection_coverage: { complete: true } }), null)

const savedFetch = globalThis.fetch
const names = ['VERIFIED_SNAPSHOT_URL', 'VITE_VERIFIED_SNAPSHOT_URL', 'DATABASE_URL', 'POSTGRES_URL', 'AI_PREWARM_TOKEN']
const saved = new Map(names.map((name) => [name, process.env[name]]))
const snapshotUrl = 'https://snapshots.example/verified.json'
let snapshotReads = 0
let otherCalls = 0
try {
  process.env.VERIFIED_SNAPSHOT_URL = snapshotUrl
  process.env.VITE_VERIFIED_SNAPSHOT_URL = ''
  process.env.DATABASE_URL = ''
  process.env.POSTGRES_URL = ''
  process.env.AI_PREWARM_TOKEN = 'offline-test-only'
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async (url) => {
    if (String(url) !== snapshotUrl) {
      otherCalls += 1
      throw new Error('Unexpected database/provider request in offline test')
    }
    snapshotReads += 1
    return new Response(JSON.stringify(snapshot), { status: 200 })
  }

  for (const [body, query, authorization] of [
    [{ opportunity_id: opportunityId }, {}, undefined],
    [{ opportunity_ids: [opportunityId], cache_only: false }, {}, undefined],
    [{ opportunity_ids: [opportunityId], cache_only: true }, {}, undefined],
    [{ limit: 1 }, { route: 'prewarm' }, 'Bearer offline-test-only'],
  ]) {
    const response = {
      statusCode: null, body: null,
      setHeader() {},
      status(code) { this.statusCode = code; return this },
      json(value) { this.body = value; return this },
    }
    await handler({
      method: 'POST', body, query,
      headers: { origin: 'https://trial.example', host: 'trial.example', authorization },
    }, response)
    assert.equal(response.statusCode, 409)
    assert.equal(response.body.error, 'VERIFIED_SNAPSHOT_COVERAGE_INCOMPLETE')
  }
  assert.ok(snapshotReads > 0)
  assert.equal(otherCalls, 0)
} finally {
  globalThis.fetch = savedFetch
  for (const [name, value] of saved) {
    if (value === undefined) delete process.env[name]
    else process.env[name] = value
  }
  clearVerifiedSnapshotCacheForTests()
}
console.log('Partial coverage AI boundary: PASS (single, batch, cache-only, prewarm; no provider/database requests)')
