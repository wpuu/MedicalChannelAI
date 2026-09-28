import { readFileSync } from 'node:fs'
import handler from '../api/ai/analyze.js'
import { marketCodeForSnapshotCard, runtimeWindowStatus } from '../api/ai/_analyzeCore.js'
import { clearVerifiedSnapshotCacheForTests } from '../api/_verifiedSnapshot.js'

const snapshot = JSON.parse(
  readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'),
)
const knownOpportunityId = snapshot.cards?.[0]?.opportunity_id
if (!knownOpportunityId) throw new Error('AI_BOUNDARY_TEST_NO_VERIFIED_CARD')

function mockResponse() {
  return {
    headers: {},
    statusCode: null,
    body: null,
    setHeader(name, value) {
      this.headers[String(name).toLowerCase()] = value
    },
    status(code) {
      this.statusCode = code
      return this
    },
    json(payload) {
      this.body = payload
      return this
    },
  }
}

async function invoke({ method = 'POST', body = {}, origin, host = 'trial.example', ip = '198.51.100.1' } = {}) {
  const response = mockResponse()
  const headers = { host, 'x-forwarded-for': ip }
  if (origin) headers.origin = origin
  await handler({ method, headers, body }, response)
  return response
}

function expectStatus(response, expected, code) {
  if (response.statusCode !== expected) {
    throw new Error(`${code}: expected ${expected}, got ${response.statusCode}`)
  }
}

function successfulProviderResponse() {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      choices: [{ message: { content: JSON.stringify({
        headline: '先核对官方原文',
        focus: [{ ref: '#1', reason: 'CLEAR_DEVICE_DEMAND' }],
      }) } }],
    }),
  }
}

const savedKeys = process.env.AGNES_API_KEYS
const savedKey = process.env.AGNES_API_KEY
const savedRemote = process.env.VERIFIED_SNAPSHOT_URL
const savedPublicRemote = process.env.VITE_VERIFIED_SNAPSHOT_URL
const savedPilot = process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED
const savedFetch = globalThis.fetch
process.env.AGNES_API_KEYS = ''
process.env.AGNES_API_KEY = ''
process.env.VERIFIED_SNAPSHOT_URL = ''
process.env.VITE_VERIFIED_SNAPSHOT_URL = ''
clearVerifiedSnapshotCacheForTests()

try {
  process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED = '1'
  let response = await invoke({ body: { opportunity_id: knownOpportunityId } })
  expectStatus(response, 403, 'AI_PILOT_BOUNDARY_ORIGIN_REQUIRED')
  if (response.body?.error !== 'SAME_ORIGIN_REQUIRED') throw new Error('AI_PILOT_BOUNDARY_ORIGIN_CODE')

  // The remaining cases exercise the public grounded AI core. Keep them isolated
  // from Preview/Pilot build environment variables so authentication does not
  // mask request-shape, grounding, provider, retry, and rate-limit assertions.
  process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED = ''

  const dateOnlyFacts = {
    registration_deadline: null,
    registration_deadline_date: '2026-07-10',
    bid_deadline: null,
  }
  if (runtimeWindowStatus(dateOnlyFacts, Date.parse('2026-07-10T23:30:00+08:00')) !== 'OPEN') {
    throw new Error('AI_DATE_ONLY_DEADLINE_DAY_MUST_REMAIN_OPEN')
  }
  if (runtimeWindowStatus(dateOnlyFacts, Date.parse('2026-07-11T00:01:00+08:00')) !== 'CLOSED') {
    throw new Error('AI_DATE_ONLY_DEADLINE_NEXT_DAY_MUST_CLOSE')
  }

  response = await invoke({ method: 'GET' })
  expectStatus(response, 405, 'AI_BOUNDARY_GET')
  if (response.body?.error !== 'METHOD_NOT_ALLOWED') throw new Error('AI_BOUNDARY_GET_CODE')

  response = await invoke({ body: { opportunity_id: knownOpportunityId } })
  expectStatus(response, 403, 'AI_BOUNDARY_ORIGIN_REQUIRED')
  if (response.body?.error !== 'SAME_ORIGIN_REQUIRED') throw new Error('AI_BOUNDARY_ORIGIN_CODE')

  response = await invoke({
    origin: 'https://other.example',
    body: { opportunity_id: knownOpportunityId },
  })
  expectStatus(response, 403, 'AI_BOUNDARY_CROSS_ORIGIN')

  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: knownOpportunityId, facts: { forged: true } },
    ip: '198.51.100.2',
  })
  expectStatus(response, 400, 'AI_BOUNDARY_UNEXPECTED_FIELDS')
  if (response.body?.error !== 'UNEXPECTED_FIELDS') throw new Error('AI_BOUNDARY_UNEXPECTED_FIELDS_CODE')

  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: 'not-a-verified-opportunity' },
    ip: '198.51.100.3',
  })
  expectStatus(response, 404, 'AI_BOUNDARY_UNKNOWN_ID')
  if (response.body?.error !== 'VERIFIED_OPPORTUNITY_NOT_FOUND') throw new Error('AI_BOUNDARY_UNKNOWN_ID_CODE')

  // Per-card next steps are deterministic public-fact rules: they work with no
  // provider key and never call the model.
  let providerCalls = 0
  globalThis.fetch = async () => {
    providerCalls += 1
    throw new Error('PER_CARD_MUST_NOT_FETCH')
  }
  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: knownOpportunityId },
    ip: '198.51.100.4',
  })
  expectStatus(response, 200, 'AI_BOUNDARY_RULES_WITHOUT_KEY')
  if (response.body?.decision_source !== 'PUBLIC_FACT_RULES') throw new Error('AI_BOUNDARY_RULES_SOURCE')
  if (!response.body?.decision?.action) throw new Error('AI_BOUNDARY_RULES_DECISION')
  if (providerCalls !== 0) throw new Error(`AI_BOUNDARY_RULES_CALLED_PROVIDER:${providerCalls}`)
  globalThis.fetch = savedFetch

  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_ids: [knownOpportunityId, 'not-a-verified-opportunity'] },
    ip: '198.51.100.4',
  })
  expectStatus(response, 200, 'AI_BOUNDARY_BATCH_RULES')
  if (response.body?.items?.[0]?.status !== 'READY') throw new Error('AI_BOUNDARY_BATCH_READY')
  if (response.body?.items?.[1]?.status === 'READY') throw new Error('AI_BOUNDARY_BATCH_UNKNOWN_READY')

  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: knownOpportunityId, page_brief: { markets: ['TJ'] } },
    ip: '198.51.100.4',
  })
  expectStatus(response, 400, 'AI_BOUNDARY_PAGE_BRIEF_EXCLUSIVE')

  const poolOnlyOpportunityId = 'verified-pool-only-regression'
  const poolOnlyCard = JSON.parse(JSON.stringify(snapshot.cards[0]))
  poolOnlyCard.opportunity_id = poolOnlyOpportunityId
  poolOnlyCard.rank = 6
  const remoteSnapshot = JSON.parse(JSON.stringify(snapshot))
  remoteSnapshot.opportunity_pool = [...snapshot.cards, poolOnlyCard]
  remoteSnapshot.opportunity_pool_count = remoteSnapshot.opportunity_pool.length
  remoteSnapshot.matched_count = remoteSnapshot.opportunity_pool.length
  process.env.VERIFIED_SNAPSHOT_URL = 'https://snapshot.example/today-actions.public.json'
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    text: async () => JSON.stringify(remoteSnapshot),
  })
  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: poolOnlyOpportunityId },
    ip: '198.51.100.6',
  })
  expectStatus(response, 200, 'AI_BOUNDARY_POOL_ONLY_ID')
  if (response.body?.decision_source !== 'PUBLIC_FACT_RULES') {
    throw new Error('AI_BOUNDARY_POOL_ONLY_ID_NOT_GROUNDED')
  }

  const expiredDateOnlyId = 'verified-date-only-expired-regression'
  const expiredCard = JSON.parse(JSON.stringify(snapshot.cards[0]))
  expiredCard.opportunity_id = expiredDateOnlyId
  expiredCard.rank = 7
  expiredCard.facts.registration_deadline = null
  expiredCard.facts.registration_deadline_date = '2000-01-01'
  expiredCard.facts.registration_deadline_precision = 'DAY'
  expiredCard.facts.bid_deadline = null
  const expiredRemote = JSON.parse(JSON.stringify(snapshot))
  expiredRemote.opportunity_pool = [...snapshot.cards, expiredCard]
  expiredRemote.opportunity_pool_count = expiredRemote.opportunity_pool.length
  expiredRemote.matched_count = expiredRemote.opportunity_pool.length
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    text: async () => JSON.stringify(expiredRemote),
  })
  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: expiredDateOnlyId },
    ip: '198.51.100.7',
  })
  expectStatus(response, 409, 'AI_BOUNDARY_DATE_ONLY_CLOSED')
  if (response.body?.error !== 'OPPORTUNITY_WINDOW_CLOSED') {
    throw new Error('AI_BOUNDARY_DATE_ONLY_CLOSED_CODE')
  }

  // ---- Page brief: the only path that calls the model ----------------------
  // Build a snapshot whose cards stay open regardless of the test date.
  const briefCard = JSON.parse(JSON.stringify(snapshot.cards[0]))
  briefCard.opportunity_id = 'page-brief-boundary-card'
  briefCard.facts.registration_deadline = '2099-01-10T16:00:00+08:00'
  briefCard.facts.registration_deadline_date = null
  briefCard.facts.registration_deadline_precision = 'MINUTE'
  briefCard.facts.bid_deadline = '2099-01-20T10:00:00+08:00'
  const briefMarket = marketCodeForSnapshotCard(briefCard)
  if (!briefMarket) throw new Error('AI_BOUNDARY_BRIEF_MARKET_UNKNOWN')
  const briefSnapshot = JSON.parse(JSON.stringify(snapshot))
  // Keep only the synthetic open card in the brief's market so ref #1 is it.
  briefSnapshot.cards = snapshot.cards.filter((card) => marketCodeForSnapshotCard(card) !== briefMarket)
  briefSnapshot.card_count = briefSnapshot.cards.length
  briefSnapshot.opportunity_pool = [...briefSnapshot.cards, briefCard]
  briefSnapshot.opportunity_pool_count = briefSnapshot.opportunity_pool.length
  briefSnapshot.matched_count = briefSnapshot.opportunity_pool.length
  const snapshotText = JSON.stringify(briefSnapshot)
  const isSnapshotUrl = (url) => String(url).startsWith('https://snapshot.example/')
  const snapshotResponse = () => ({ ok: true, status: 200, headers: { get: () => null }, text: async () => snapshotText })
  clearVerifiedSnapshotCacheForTests()
  const briefBody = (extra = {}) => ({ page_brief: { markets: [briefMarket] }, ...extra })

  // Without a key: rule brief, never an error page.
  globalThis.fetch = async (url) => {
    if (isSnapshotUrl(url)) return snapshotResponse()
    throw new Error('UNEXPECTED_PROVIDER_CALL')
  }
  response = await invoke({ origin: 'https://trial.example', body: briefBody(), ip: '198.51.100.11' })
  expectStatus(response, 200, 'AI_BRIEF_UNCONFIGURED')
  if (response.body?.brief?.brief_source !== 'RULES') throw new Error('AI_BRIEF_UNCONFIGURED_SOURCE')
  if (response.body?.ai_error !== 'AI_NOT_CONFIGURED') throw new Error('AI_BRIEF_UNCONFIGURED_CODE')

  process.env.AGNES_API_KEYS = 'fake-key-a,fake-key-b'

  // cache_only never calls the provider even with keys.
  response = await invoke({ origin: 'https://trial.example', body: briefBody({ cache_only: true }), ip: '198.51.100.11' })
  expectStatus(response, 200, 'AI_BRIEF_CACHE_ONLY')
  if (response.body?.brief?.brief_source !== 'RULES') throw new Error('AI_BRIEF_CACHE_ONLY_SOURCE')

  let seenAuthorization = []
  let seenUrls = []
  let providerAttempt = 0
  const providerFetch = (provider) => async (url, options = {}) => {
    if (isSnapshotUrl(url)) return snapshotResponse()
    providerAttempt += 1
    seenUrls.push(String(url))
    seenAuthorization.push(options.headers?.Authorization ?? null)
    return provider(providerAttempt)
  }

  // Provider 429 stops immediately (no retry, no key rotation) and degrades to rules.
  globalThis.fetch = providerFetch(() => ({ ok: false, status: 429 }))
  response = await invoke({ origin: 'https://trial.example', body: briefBody(), ip: '198.51.100.8' })
  expectStatus(response, 200, 'AI_PROVIDER_429_FALLS_BACK')
  if (response.body?.ai_error !== 'AI_RATE_LIMITED') throw new Error('AI_PROVIDER_429_CODE')
  if (response.body?.brief?.brief_source !== 'RULES') throw new Error('AI_PROVIDER_429_SOURCE')
  if (providerAttempt !== 1) throw new Error(`AI_PROVIDER_429_RETRIED:${providerAttempt}`)
  if (new Set(seenAuthorization).size !== 1) throw new Error('AI_PROVIDER_429_ROTATED_KEY')
  let responseText = JSON.stringify(response.body)
  if (responseText.includes('fake-key-a') || responseText.includes('fake-key-b')) {
    throw new Error('AI_MULTI_KEY_SECRET_LEAK')
  }

  // Provider 503 is retried once on the same key and route.
  providerAttempt = 0
  seenAuthorization = []
  seenUrls = []
  globalThis.fetch = providerFetch((attempt) => attempt === 1 ? { ok: false, status: 503 } : successfulProviderResponse())
  response = await invoke({ origin: 'https://trial.example', body: briefBody(), ip: '198.51.100.9' })
  expectStatus(response, 200, 'AI_PROVIDER_503_RETRY_SUCCESS')
  if (response.body?.brief?.brief_source !== 'AI') throw new Error('AI_PROVIDER_503_RETRY_NOT_AI')
  if (response.body?.brief?.focus?.[0]?.opportunity_id !== 'page-brief-boundary-card') throw new Error('AI_PROVIDER_BRIEF_REF_NOT_RESOLVED')
  if (providerAttempt !== 2) throw new Error(`AI_PROVIDER_503_RETRY_ATTEMPTS:${providerAttempt}`)
  if (new Set(seenAuthorization).size !== 1) throw new Error('AI_PROVIDER_503_RETRY_ROTATED_KEY')
  if (new Set(seenUrls).size !== 1) throw new Error('AI_PROVIDER_503_RETRY_CHANGED_ROUTE')

  // Network failure retries once on the alternate route.
  providerAttempt = 0
  seenAuthorization = []
  seenUrls = []
  globalThis.fetch = providerFetch((attempt) => {
    if (attempt === 1) {
      const error = new TypeError('fetch failed')
      error.cause = { code: 'ENOTFOUND' }
      throw error
    }
    return successfulProviderResponse()
  })
  response = await invoke({ origin: 'https://trial.example', body: briefBody(), ip: '198.51.100.10' })
  expectStatus(response, 200, 'AI_PROVIDER_NETWORK_ALTERNATE_SUCCESS')
  if (providerAttempt !== 2) throw new Error(`AI_PROVIDER_NETWORK_RETRY_ATTEMPTS:${providerAttempt}`)
  if (new Set(seenAuthorization).size !== 1) throw new Error('AI_PROVIDER_NETWORK_RETRY_ROTATED_KEY')
  if (!seenUrls[0]?.startsWith('https://apihub.agnes-ai.com/v1/')) {
    throw new Error(`AI_PROVIDER_PRIMARY_ROUTE_UNEXPECTED:${seenUrls[0]}`)
  }
  if (!seenUrls[1]?.startsWith('https://apihub.agnes-ai.cn/v1/')) {
    throw new Error(`AI_PROVIDER_ALTERNATE_ROUTE_NOT_USED:${seenUrls[1]}`)
  }
  responseText = JSON.stringify(response.body)
  if (responseText.includes('fake-key-a') || responseText.includes('fake-key-b')) {
    throw new Error('AI_NETWORK_RETRY_SECRET_LEAK')
  }

  // Rate limiting protects actual provider work: 10 generations per client
  // window, then the page degrades to the rule brief without a provider call.
  // Rule next steps never consume this budget.
  providerAttempt = 0
  globalThis.fetch = providerFetch(() => successfulProviderResponse())
  for (let index = 0; index < 12; index += 1) {
    response = await invoke({ origin: 'https://trial.example', body: { opportunity_id: 'page-brief-boundary-card' }, ip: '198.51.100.5' })
    if (response.statusCode !== 200) throw new Error(`AI_RULES_RATE_${index}:${response.statusCode}`)
  }
  if (providerAttempt !== 0) throw new Error('AI_RULES_USED_PROVIDER')
  for (let index = 0; index < 10; index += 1) {
    response = await invoke({ origin: 'https://trial.example', body: briefBody(), ip: '198.51.100.5' })
    expectStatus(response, 200, `AI_BOUNDARY_RATE_PROVIDER_PRE_${index}`)
    if (response.body?.brief?.brief_source !== 'AI') throw new Error(`AI_BOUNDARY_RATE_PRE_NOT_AI_${index}`)
  }
  response = await invoke({ origin: 'https://trial.example', body: briefBody(), ip: '198.51.100.5' })
  expectStatus(response, 200, 'AI_BOUNDARY_RATE_LIMIT')
  if (response.body?.ai_error !== 'AI_RATE_LIMITED') throw new Error('AI_BOUNDARY_RATE_LIMIT_CODE')
  if (response.body?.brief?.brief_source !== 'RULES') throw new Error('AI_BOUNDARY_RATE_LIMIT_SOURCE')
  if (providerAttempt !== 10) throw new Error(`AI_BOUNDARY_RATE_PROVIDER_CALL_COUNT:${providerAttempt}`)

  console.log('AI boundary checks: PASS')
} finally {
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = savedFetch
  if (savedKeys === undefined) delete process.env.AGNES_API_KEYS
  else process.env.AGNES_API_KEYS = savedKeys
  if (savedKey === undefined) delete process.env.AGNES_API_KEY
  else process.env.AGNES_API_KEY = savedKey
  if (savedRemote === undefined) delete process.env.VERIFIED_SNAPSHOT_URL
  else process.env.VERIFIED_SNAPSHOT_URL = savedRemote
  if (savedPublicRemote === undefined) delete process.env.VITE_VERIFIED_SNAPSHOT_URL
  else process.env.VITE_VERIFIED_SNAPSHOT_URL = savedPublicRemote
  if (savedPilot === undefined) delete process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED
  else process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED = savedPilot
}
