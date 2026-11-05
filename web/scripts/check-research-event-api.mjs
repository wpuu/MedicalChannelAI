import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import handler, { outreachWindow } from '../api/ai/analyze.js'
import coreHandler, {
  callProviderWithTransientRetry,
  publicWindowCacheState,
  runtimeWindowStatus,
  sanitizeSnapshotFacts,
} from '../api/ai/_analyzeCore.js'
import { runtimeRefreshSnapshotCard, researchEventWindowClosed } from '../api/_runtimeOpportunityTime.js'
import { publicSnapshotForFollowup, sanitizeStoredSnapshot } from '../api/_privateCore.js'
import { clearVerifiedSnapshotCacheForTests } from '../api/_verifiedSnapshot.js'
import { resetRateLimitForTests } from '../api/_sharedRateLimit.js'
import { healthySourceMetadata } from './fixtures/verifiedSnapshot.mjs'

// Exercise the actual Python parser and projection against the frozen official
// article before consuming the resulting public facts through the JS layers.
const webDir = fileURLToPath(new URL('..', import.meta.url))
const frozen = JSON.parse(execFileSync('python', ['-c', `
import json
from datetime import datetime
from pathlib import Path
from medical_channel_pipeline.tjzxfc_market_research import parse_tjzxfc_market_research
from medical_channel_pipeline.public_snapshot import build_public_snapshot
record = parse_tjzxfc_market_research(
    Path('pipeline/tests/fixtures/tjzxfc_hazardous_research_20261028.html').read_text(encoding='utf-8'),
    source_url='https://www.tjzxfc.cn/system/2026/10/28/030364590.shtml',
    index_url='https://www.tjzxfc.cn/ywgk/zbgg/index.shtml',
    index_published_at='2026-10-28', expected_title='天津市中心妇产科医院调研公告',
    observed_at='2026-11-06T01:00:00+00:00', opportunity_id='tjzxfc_research_event_api_fixture')
print(json.dumps(build_public_snapshot([record], datetime.fromisoformat('2026-11-04T09:29:59+08:00')), ensure_ascii=False))
`], { cwd: webDir, env: { ...process.env, PYTHONPATH: 'pipeline' }, encoding: 'utf8' }))
const card = frozen.opportunity_pool[0]
const eventAt = card.facts.research_event_at
const eventMs = Date.parse(eventAt)
const use = '检验科、病理科、产前诊断、实验室等使用。'
const eventText = '携带资料及样品，现场讲解产品。时间：2026年11月4日9:30'
assert.equal(eventAt, '2026-11-04T09:30:00+08:00')
const facts = sanitizeSnapshotFacts(card.facts)
assert.equal(facts.product_use, use)
assert.equal(facts.research_event_text, eventText)
assert.equal(facts.research_event_at, eventAt)
assert.equal(facts.registration_deadline, null)
assert.equal(facts.bid_deadline, null)
assert.equal(runtimeWindowStatus(facts, eventMs - 1), 'OPEN')
assert.equal(publicWindowCacheState(facts, 'OPEN', eventMs - 1), 'OPEN:NO_DEADLINE')
assert.equal(runtimeRefreshSnapshotCard(card, eventMs - 1).priority.components.find((row) => row.code === 'DEADLINE_URGENCY').points, 0)

const stored = sanitizeStoredSnapshot(publicSnapshotForFollowup(card))
for (const field of ['research_event_at', 'research_event_text', 'product_use']) {
  assert.equal(stored.facts[field], card.facts[field], `private snapshot lost ${field}`)
}
for (const now of [eventMs, eventMs + 1, Date.parse('2026-11-06T01:00:00Z')]) {
  assert.equal(runtimeRefreshSnapshotCard(card, now), null)
  assert.equal(runtimeWindowStatus(facts, now), 'CLOSED')
  assert.equal(runtimeWindowStatus(sanitizeSnapshotFacts(stored.facts), now), 'CLOSED')
  assert.equal(outreachWindow(card.facts, now).open, false)
}
for (const invalid of ['2026-11-04', '2026-11-04T09:30:00', '2026-02-30T09:30:00+08:00', '2026-11-04T24:00:00+08:00', '2026-11-04T09:30:00+99:00']) {
  const invalidFacts = { ...card.facts, research_event_at: invalid }
  assert.equal(researchEventWindowClosed(invalidFacts, eventMs - 1), true, invalid)
  assert.equal(runtimeWindowStatus(sanitizeSnapshotFacts(invalidFacts), eventMs - 1), 'CLOSED', invalid)
}

const OriginalDate = globalThis.Date
let nowMs = eventMs - 1
globalThis.Date = class extends OriginalDate {
  constructor(...args) { super(...(args.length ? args : [nowMs])) }
  static now() { return nowMs }
}
const envKeys = ['DATABASE_URL', 'POSTGRES_URL', 'VERIFIED_SNAPSHOT_URL', 'VITE_VERIFIED_SNAPSHOT_URL', 'AGNES_API_KEYS', 'AGNES_API_KEY', 'MCAI_RATE_LIMIT_STORE']
const saved = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]))
const savedFetch = globalThis.fetch
for (const key of envKeys) delete process.env[key]
process.env.VERIFIED_SNAPSHOT_URL = 'https://research-event.audit.example/fixture'
process.env.AGNES_API_KEY = 'local-mock-provider-key'
process.env.MCAI_RATE_LIMIT_STORE = 'memory'
let fixture
let providerCalls = 0
let crossEventOnProviderReturn = false
let providerFacts
function setFixture(id) {
  fixture = structuredClone(frozen)
  fixture.source_health = healthySourceMetadata(eventMs - 1)
  fixture.opportunity_pool[0].opportunity_id = id
  fixture.opportunity_pool[0].source_id = 'tjzxfc'
  fixture.cards = fixture.opportunity_pool.slice(0, 5)
}
globalThis.fetch = async (url, init) => {
  if (String(url) === process.env.VERIFIED_SNAPSHOT_URL) {
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(fixture) }
  }
  assert(String(url).includes('/chat/completions'), `unexpected external request: ${url}`)
  providerCalls++
  providerFacts = JSON.parse(JSON.parse(init.body).messages[1].content)['已核验公开事实']
  return { ok: true, status: 200, json: async () => {
    if (crossEventOnProviderReturn) nowMs = eventMs
    return { choices: [{ message: { content: JSON.stringify({ action_codes: ['VERIFY_REQUIREMENTS'] }) } }] }
  } }
}

async function invoke(body, privateOverlay = false) {
  clearVerifiedSnapshotCacheForTests()
  const response = {
    statusCode: null, body: null, setHeader() {},
    status(code) { this.statusCode = code; return this },
    json(value) { this.body = value; return this },
  }
  const request = { method: 'POST', body,
    headers: { host: 'audit.example', origin: 'https://audit.example', 'x-forwarded-for': '198.51.100.119' },
    ...(privateOverlay ? { __medicalChannelPrivateDecisionOverlay: { matching_product_capabilities: [] } } : {}),
  }
  await (privateOverlay ? coreHandler : handler)(request, response)
  return response
}

try {
  resetRateLimitForTests()
  const id = 'tjzxfc_research_event_cache_fixture'
  setFixture(id)
  let response = await invoke({ opportunity_id: id })
  assert.equal(response.statusCode, 200)
  assert.equal(providerCalls, 1)
  assert.equal(providerFacts['现场调研或讲解时间'], eventAt)
  assert.equal(providerFacts['现场调研或讲解原文'], eventText)
  assert.equal(providerFacts['产品用途原文'], use)
  assert.equal(providerFacts['报名或文件获取截止时间'], null)
  assert.equal(providerFacts['投标截止时间'], null)
  response = await invoke({ opportunity_id: id })
  assert.equal(response.statusCode, 200)
  assert.equal(providerCalls, 1, 'warm cache missed before event')

  nowMs = eventMs
  for (const privateOverlay of [false, true]) {
    response = await invoke({ opportunity_id: id }, privateOverlay)
    assert.equal(response.statusCode, 409)
    assert.equal(response.body.error, 'OPPORTUNITY_WINDOW_CLOSED')
  }
  for (const cacheOnly of [false, true]) {
    response = await invoke({ opportunity_ids: [id], cache_only: cacheOnly })
    assert.equal(response.statusCode, 200)
    assert.equal(response.body.items[0].status, 'NOT_ELIGIBLE')
    assert.equal(response.body.items[0].error, 'OPPORTUNITY_WINDOW_CLOSED')
  }
  assert.equal(providerCalls, 1, 'expired event used cached answer or invoked provider')
  await assert.rejects(callProviderWithTransientRetry({ facts, baseUrl: 'https://mock.audit.example' }, ['mock-key'], id), { code: 'OPPORTUNITY_WINDOW_CLOSED' })
  assert.equal(providerCalls, 1, 'expired event invoked direct provider/retry')

  crossEventOnProviderReturn = true
  for (const mode of ['single', 'private', 'batch']) {
    nowMs = eventMs - 1
    const crossId = `tjzxfc_research_event_cross_${mode}`
    setFixture(crossId)
    response = await invoke(mode === 'batch' ? { opportunity_ids: [crossId] } : { opportunity_id: crossId }, mode === 'private')
    if (mode === 'batch') {
      assert.equal(response.body.items[0].status, 'NOT_ELIGIBLE')
      assert.equal(response.body.items[0].error, 'OPPORTUNITY_WINDOW_CLOSED')
      assert.equal(response.body.ready_count, 0)
    } else {
      assert.equal(response.statusCode, 409)
      assert.equal(response.body.error, 'OPPORTUNITY_WINDOW_CLOSED')
    }
  }
  assert.equal(providerCalls, 4)
  console.log('Research event API: PASS (frozen official parser/projection, runtime/AI/private preservation, exact closure, no invented deadline, crossing provider await)')
} finally {
  globalThis.Date = OriginalDate
  globalThis.fetch = savedFetch
  clearVerifiedSnapshotCacheForTests()
  resetRateLimitForTests()
  for (const [key, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
}
