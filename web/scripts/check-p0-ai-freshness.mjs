import assert from 'node:assert/strict'
import handler from '../api/ai/analyze.js'
import coreHandler, { prewarmSharedPublicDecisions, verifiedSnapshotAutomationError } from '../api/ai/_analyzeCore.js'
import { clearVerifiedSnapshotCacheForTests } from '../api/_verifiedSnapshot.js'
import { resetRateLimitForTests } from '../api/_sharedRateLimit.js'
import { installSnapshotTestClock, makeVerifiedSnapshot, SNAPSHOT_TEST_NOW_MS } from './fixtures/verifiedSnapshot.mjs'

const restoreClock = installSnapshotTestClock()
const envKeys = ['DATABASE_URL', 'POSTGRES_URL', 'VERIFIED_SNAPSHOT_URL', 'VITE_VERIFIED_SNAPSHOT_URL', 'AGNES_API_KEYS', 'AGNES_API_KEY']
const saved = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]))
const savedFetch = globalThis.fetch
let fixture = makeVerifiedSnapshot()
let unavailable = false
let providerCalls = 0
for (const key of envKeys) delete process.env[key]
process.env.VERIFIED_SNAPSHOT_URL = 'https://snapshot.audit.example/fixture'
process.env.AGNES_API_KEY = 'local-mock-provider-key'
globalThis.fetch = async (url) => {
  if (String(url) === process.env.VERIFIED_SNAPSHOT_URL) {
    if (unavailable) return { ok: false, status: 503 }
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(fixture) }
  }
  assert(String(url).includes('/chat/completions'), `unexpected network path: ${url}`)
  providerCalls++
  return {
    ok: true, status: 200,
    json: async () => ({ choices: [{ message: { content: JSON.stringify({ action_codes: ['VERIFY_REQUIREMENTS'] }) } }] }),
  }
}

async function invoke(body, { privateOverlay = false } = {}) {
  clearVerifiedSnapshotCacheForTests()
  const response = {
    statusCode: null, body: null,
    setHeader() {},
    status(code) { this.statusCode = code; return this },
    json(value) { this.body = value; return this },
  }
  const request = {
    method: 'POST',
    headers: { host: 'audit.example', origin: 'https://audit.example', 'x-forwarded-for': '198.51.100.101' },
    body,
    ...(privateOverlay ? { __medicalChannelPrivateDecisionOverlay: { matching_product_capabilities: [] } } : {}),
  }
  await (privateOverlay ? coreHandler : handler)(request, response)
  return response
}

try {
  resetRateLimitForTests()
  const id = fixture.cards[0].opportunity_id
  let response = await invoke({ opportunity_id: id })
  assert.equal(response.statusCode, 200)
  assert.equal(providerCalls, 1)
  response = await invoke({ opportunity_id: id })
  assert.equal(response.statusCode, 200)
  assert.equal(providerCalls, 1, 'fresh cache hit called provider')

  for (const [name, asOfMs] of [
    ['older than 30 hours', SNAPSHOT_TEST_NOW_MS - 30 * 60 * 60 * 1000 - 1],
    ['future anomaly', SNAPSHOT_TEST_NOW_MS + 10 * 60 * 1000 + 1],
  ]) {
    fixture = makeVerifiedSnapshot({ asOfMs })
    for (const body of [
      { opportunity_id: id },
      { opportunity_ids: [id] },
      { opportunity_ids: [id], cache_only: true },
      { opportunity_id: id, customer_context: { matching_product_capabilities: [{ category: '医疗设备', capability_type: 'DIRECT_UNCONFIRMED' }] } },
    ]) {
      response = await invoke(body)
      assert.equal(response.statusCode, 409, name)
      assert.equal(response.body.error, 'VERIFIED_SNAPSHOT_NOT_FRESH')
      assert.equal(providerCalls, 1, `${name}: provider ran before freshness gate`)
    }
    response = await invoke({ opportunity_id: id }, { privateOverlay: true })
    assert.equal(response.statusCode, 409, `${name}: private overlay bypassed core gate`)
    assert.equal(providerCalls, 1)
    await assert.rejects(prewarmSharedPublicDecisions({ snapshot: fixture }), { code: 'VERIFIED_SNAPSHOT_NOT_FRESH' })
  }

  // Both edges are inclusive, using the same server clock for single/batch.
  for (const asOfMs of [SNAPSHOT_TEST_NOW_MS - 30 * 60 * 60 * 1000, SNAPSHOT_TEST_NOW_MS + 10 * 60 * 1000]) {
    fixture = makeVerifiedSnapshot({ asOfMs })
    response = await invoke({ opportunity_id: id })
    assert.equal(response.statusCode, 200)
    response = await invoke({ opportunity_ids: [id], cache_only: true })
    assert.equal(response.statusCode, 200)
  }
  assert.equal(verifiedSnapshotAutomationError({ snapshot_as_of: 'invalid' }), 'VERIFIED_SNAPSHOT_NOT_FRESH')
  assert.equal(verifiedSnapshotAutomationError({}), 'VERIFIED_SNAPSHOT_NOT_FRESH')

  for (const mutate of [
    (snapshot) => { delete snapshot.source_health },
    (snapshot) => { delete snapshot.source_health.sources.ccgp },
    (snapshot) => {
      const row = snapshot.source_health.sources.ccgp
      row.last_successful_scan_at = new Date(SNAPSHOT_TEST_NOW_MS - (row.stale_after_seconds + 1) * 1000).toISOString()
      row.last_attempt_at = row.last_successful_scan_at
    },
    (snapshot) => { snapshot.source_health.sources.ccgp.failure_reason = 'VERIFICATION_FAILED' },
  ]) {
    fixture = makeVerifiedSnapshot()
    mutate(fixture)
    response = await invoke({ opportunity_id: id })
    assert.equal(response.statusCode, 409)
    assert.equal(response.body.error, 'SOURCE_HEALTH_UNAVAILABLE')
    response = await invoke({ opportunity_ids: [id], cache_only: true })
    assert.equal(response.statusCode, 200)
    assert.equal(response.body.items[0].status, 'ERROR')
    assert.equal(response.body.items[0].error, 'SOURCE_HEALTH_UNAVAILABLE')
    assert.equal(providerCalls, 1, 'source health gate was bypassed by cached decision or batch')
  }

  // A failing unrelated source must remain visible without blocking a healthy
  // opportunity. A mixed batch rejects only the candidate from the failing one.
  fixture = makeVerifiedSnapshot({ ids: [id, 'tjzyefy_p0_fixture'] })
  fixture.opportunity_pool[1].source_id = 'tjzyefy'
  fixture.source_health.sources.tjzyefy.failure_reason = 'VERIFICATION_FAILED'
  response = await invoke({ opportunity_ids: [id, 'tjzyefy_p0_fixture'], cache_only: true })
  assert.equal(response.statusCode, 200)
  assert.equal(response.body.items[0].error, undefined)
  assert.equal(response.body.items[1].error, 'SOURCE_HEALTH_UNAVAILABLE')

  fixture = makeVerifiedSnapshot({ ids: ['ccgp_tj_p0_new_batch'] })
  response = await invoke({ opportunity_ids: [fixture.cards[0].opportunity_id] })
  assert.equal(response.statusCode, 200)
  assert.equal(response.body.ready_count, 1)
  assert.equal(providerCalls, 2, 'fresh eligible batch did not generate exactly once')

  unavailable = true
  response = await invoke({ opportunity_id: id })
  assert.equal(response.statusCode, 503)
  assert.equal(response.body.error, 'VERIFIED_SNAPSHOT_UNAVAILABLE')
  assert.equal(providerCalls, 2)
  unavailable = false
  fixture = { schema_version: 'invalid' }
  response = await invoke({ opportunity_ids: [id], cache_only: true })
  assert.equal(response.statusCode, 503)
  assert.equal(providerCalls, 2)
  console.log('P0 AI freshness: PASS (public/private core, single/batch/cache-only/prewarm, exact time edges, source isolation, zero provider work on rejection)')
} finally {
  restoreClock()
  globalThis.fetch = savedFetch
  clearVerifiedSnapshotCacheForTests()
  resetRateLimitForTests()
  for (const [key, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
}
