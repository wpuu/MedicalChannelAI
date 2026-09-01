import statusHandler, { snapshotFreshness } from '../api/status.js'
import { clearVerifiedSnapshotCacheForTests } from '../api/_verifiedSnapshot.js'

function expect(condition, code) {
  if (!condition) throw new Error(code)
}

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

async function invoke(method = 'GET') {
  const response = mockResponse()
  await statusHandler({ method }, response)
  return response
}

const savedKeys = process.env.AGNES_API_KEYS
const savedKey = process.env.AGNES_API_KEY
const savedRemote = process.env.VERIFIED_SNAPSHOT_URL
const savedPublicRemote = process.env.VITE_VERIFIED_SNAPSHOT_URL
const savedFetch = globalThis.fetch

try {
  const fixedNow = Date.parse('2026-09-01T12:00:00Z')
  let freshness = snapshotFreshness('2026-08-31T07:00:00Z', fixedNow)
  expect(freshness.freshness === 'FRESH', 'STATUS_FRESHNESS_FRESH')
  expect(freshness.degraded === false, 'STATUS_FRESHNESS_FRESH_NOT_DEGRADED')
  expect(freshness.age_minutes === 1740, 'STATUS_FRESHNESS_FRESH_AGE')

  freshness = snapshotFreshness('2026-08-31T05:00:00Z', fixedNow)
  expect(freshness.freshness === 'STALE', 'STATUS_FRESHNESS_STALE')
  expect(freshness.degraded === true, 'STATUS_FRESHNESS_STALE_DEGRADED')
  expect(freshness.age_minutes === 1860, 'STATUS_FRESHNESS_STALE_AGE')

  freshness = snapshotFreshness('2026-09-01T12:16:00Z', fixedNow)
  expect(freshness.freshness === 'INVALID', 'STATUS_FRESHNESS_FUTURE_INVALID')
  expect(freshness.age_minutes === null, 'STATUS_FRESHNESS_FUTURE_AGE_NULL')

  freshness = snapshotFreshness('not-a-date', fixedNow)
  expect(freshness.freshness === 'INVALID', 'STATUS_FRESHNESS_DATE_INVALID')

  process.env.AGNES_API_KEYS = ''
  process.env.AGNES_API_KEY = ''
  process.env.VERIFIED_SNAPSHOT_URL = ''
  process.env.VITE_VERIFIED_SNAPSHOT_URL = ''
  clearVerifiedSnapshotCacheForTests()

  let response = await invoke('GET')
  expect(response.statusCode === 200, 'STATUS_BUNDLED_HTTP')
  expect(response.body?.ready === true, 'STATUS_BUNDLED_READY')
  expect(response.body?.production_ready === false, 'STATUS_PRODUCTION_READY_FALSE')
  expect(response.body?.snapshot?.available === true, 'STATUS_SNAPSHOT_AVAILABLE')
  expect(response.body?.snapshot?.source_mode === 'BUNDLED', 'STATUS_BUNDLED_MODE')
  expect(['FRESH', 'STALE'].includes(response.body?.snapshot?.freshness), 'STATUS_BUNDLED_FRESHNESS')
  expect(typeof response.body?.snapshot?.stale_after_minutes === 'number', 'STATUS_STALE_THRESHOLD')
  expect(response.body?.ai?.configured === false, 'STATUS_AI_UNCONFIGURED')

  response = await invoke('POST')
  expect(response.statusCode === 405, 'STATUS_METHOD_REJECTED')

  const secret = 'status-test-secret-key-must-not-leak'
  process.env.AGNES_API_KEYS = secret
  response = await invoke('GET')
  expect(response.statusCode === 200, 'STATUS_AI_CONFIGURED_HTTP')
  expect(response.body?.ai?.configured === true, 'STATUS_AI_CONFIGURED_BOOL')
  expect(!JSON.stringify(response.body).includes(secret), 'STATUS_AI_SECRET_LEAK')

  process.env.VERIFIED_SNAPSHOT_URL = 'https://snapshot.example/unavailable.json'
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async () => ({ ok: false, status: 503 })
  response = await invoke('GET')
  expect(response.statusCode === 503, 'STATUS_REMOTE_FAILURE_HTTP')
  expect(response.body?.ready === false, 'STATUS_REMOTE_FAILURE_READY')
  expect(response.body?.degraded === true, 'STATUS_REMOTE_FAILURE_DEGRADED')
  expect(response.body?.snapshot?.available === false, 'STATUS_REMOTE_FAILURE_AVAILABLE')
  expect(response.body?.snapshot?.source_mode === 'REMOTE', 'STATUS_REMOTE_FAILURE_MODE')
  expect(response.body?.snapshot?.freshness === 'UNAVAILABLE', 'STATUS_REMOTE_FAILURE_FRESHNESS')
  expect(response.body?.ai?.configured === true, 'STATUS_REMOTE_FAILURE_AI_BOOL')
  expect(!JSON.stringify(response.body).includes(secret), 'STATUS_REMOTE_FAILURE_SECRET_LEAK')

  process.env.VERIFIED_SNAPSHOT_URL = 'not-a-url'
  clearVerifiedSnapshotCacheForTests()
  response = await invoke('GET')
  expect(response.statusCode === 503, 'STATUS_INVALID_REMOTE_HTTP')
  expect(response.body?.snapshot?.source_mode === 'UNAVAILABLE', 'STATUS_INVALID_REMOTE_MODE')
  expect(response.body?.snapshot?.freshness === 'UNAVAILABLE', 'STATUS_INVALID_REMOTE_FRESHNESS')

  console.log('Runtime status checks: PASS')
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
