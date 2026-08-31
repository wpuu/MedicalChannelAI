import statusHandler from '../api/status.js'
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
  expect(response.body?.snapshot?.available === false, 'STATUS_REMOTE_FAILURE_AVAILABLE')
  expect(response.body?.snapshot?.source_mode === 'REMOTE', 'STATUS_REMOTE_FAILURE_MODE')
  expect(response.body?.ai?.configured === true, 'STATUS_REMOTE_FAILURE_AI_BOOL')
  expect(!JSON.stringify(response.body).includes(secret), 'STATUS_REMOTE_FAILURE_SECRET_LEAK')

  process.env.VERIFIED_SNAPSHOT_URL = 'not-a-url'
  clearVerifiedSnapshotCacheForTests()
  response = await invoke('GET')
  expect(response.statusCode === 503, 'STATUS_INVALID_REMOTE_HTTP')
  expect(response.body?.snapshot?.source_mode === 'UNAVAILABLE', 'STATUS_INVALID_REMOTE_MODE')

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
