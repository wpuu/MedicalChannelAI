import { readFileSync } from 'node:fs'
import handler from '../api/ai/analyze.js'
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
  const headers = {
    host,
    'x-forwarded-for': ip,
  }
  if (origin) headers.origin = origin
  await handler({ method, headers, body }, response)
  return response
}

function expectStatus(response, expected, code) {
  if (response.statusCode !== expected) {
    throw new Error(`${code}: expected ${expected}, got ${response.statusCode}`)
  }
}

const savedKeys = process.env.AGNES_API_KEYS
const savedKey = process.env.AGNES_API_KEY
const savedRemote = process.env.VERIFIED_SNAPSHOT_URL
const savedPublicRemote = process.env.VITE_VERIFIED_SNAPSHOT_URL
const savedFetch = globalThis.fetch
process.env.AGNES_API_KEYS = ''
process.env.AGNES_API_KEY = ''
process.env.VERIFIED_SNAPSHOT_URL = ''
process.env.VITE_VERIFIED_SNAPSHOT_URL = ''
clearVerifiedSnapshotCacheForTests()

try {
  let response = await invoke({ method: 'GET' })
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

  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: knownOpportunityId },
    ip: '198.51.100.4',
  })
  expectStatus(response, 503, 'AI_BOUNDARY_UNCONFIGURED')
  if (response.body?.error !== 'AI_NOT_CONFIGURED') throw new Error('AI_BOUNDARY_UNCONFIGURED_CODE')

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
  expectStatus(response, 503, 'AI_BOUNDARY_POOL_ONLY_ID')
  if (response.body?.error !== 'AI_NOT_CONFIGURED') {
    throw new Error('AI_BOUNDARY_POOL_ONLY_ID_NOT_GROUNDED')
  }

  process.env.VERIFIED_SNAPSHOT_URL = ''
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = savedFetch

  for (let index = 0; index < 10; index += 1) {
    response = await invoke({
      origin: 'https://trial.example',
      body: { opportunity_id: knownOpportunityId },
      ip: '198.51.100.5',
    })
    expectStatus(response, 503, `AI_BOUNDARY_RATE_PRE_${index}`)
  }
  response = await invoke({
    origin: 'https://trial.example',
    body: { opportunity_id: knownOpportunityId },
    ip: '198.51.100.5',
  })
  expectStatus(response, 429, 'AI_BOUNDARY_RATE_LIMIT')
  if (response.body?.error !== 'AI_RATE_LIMITED') throw new Error('AI_BOUNDARY_RATE_LIMIT_CODE')

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
}
