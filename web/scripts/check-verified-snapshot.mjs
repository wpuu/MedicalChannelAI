import snapshotHandler from '../api/public-snapshot.js'
import {
  bundledVerifiedSnapshot,
  clearVerifiedSnapshotCacheForTests,
  loadVerifiedSnapshot,
  publishVerifiedSnapshotToRuntimeCache,
  selectPublishedRuntimeSnapshot,
} from '../api/_verifiedSnapshot.js'

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

async function invokeSnapshot(method = 'GET', { body, headers = {} } = {}) {
  const response = mockResponse()
  await snapshotHandler({ method, body, headers }, response)
  return response
}

function memoryCache() {
  const values = new Map()
  const setCalls = []
  return {
    setCalls,
    async get(key) { return values.get(key) ?? null },
    async set(key, value, options) {
      setCalls.push({ key, options })
      values.set(key, structuredClone(value))
    },
  }
}

async function expectRemoteRejected(payload, expectedMessage, code) {
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    text: async () => JSON.stringify(payload),
  })
  let failure = null
  try {
    await loadVerifiedSnapshot()
  } catch (error) {
    failure = error
  }
  expect(
    expectedMessage instanceof RegExp
      ? expectedMessage.test(failure?.message ?? '')
      : failure?.message === expectedMessage,
    code,
  )
}

const savedRemote = process.env.VERIFIED_SNAPSHOT_URL
const savedPublicRemote = process.env.VITE_VERIFIED_SNAPSHOT_URL
const savedPublishToken = process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN
const savedFetch = globalThis.fetch

try {
  process.env.VERIFIED_SNAPSHOT_URL = ''
  process.env.VITE_VERIFIED_SNAPSHOT_URL = ''
  process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = ''
  clearVerifiedSnapshotCacheForTests()

  const bundled = await loadVerifiedSnapshot()
  expect(bundled.schema_version === '0.1', 'SNAPSHOT_BUNDLED_SCHEMA')
  expect(bundled.mode === 'TODAY_ACTIONS', 'SNAPSHOT_BUNDLED_MODE')
  expect(Array.isArray(bundled.cards), 'SNAPSHOT_BUNDLED_CARDS')
  expect(
    bundled.snapshot_as_of === bundledVerifiedSnapshot().snapshot_as_of,
    'SNAPSHOT_BUNDLED_AS_OF',
  )
  expect(
    bundled.cards.every((card) => card.priority?.score_type === 'ZERO_CONFIG_PUBLIC_FACTS_V2'),
    'SNAPSHOT_BUNDLED_RANKING_MUST_BE_V2',
  )

  const baselineMs = Date.parse(bundledVerifiedSnapshot().snapshot_as_of)
  const testNowMs = baselineMs + 10 * 60 * 1000
  const published = structuredClone(bundledVerifiedSnapshot())
  published.snapshot_as_of = new Date(baselineMs + 60 * 1000).toISOString()
  const cache = memoryCache()
  const stored = await publishVerifiedSnapshotToRuntimeCache(published, { cache, nowMs: testNowMs })
  expect(stored.snapshot_as_of === published.snapshot_as_of, 'SNAPSHOT_RUNTIME_PUBLISH_STORED')
  expect(cache.setCalls.length === 1, 'SNAPSHOT_RUNTIME_PUBLISH_SINGLE_WRITE')
  expect(
    cache.setCalls[0]?.key === 'medicalchannelai:verified-snapshot:published:v2',
    'SNAPSHOT_RUNTIME_PUBLISH_V2_KEY',
  )
  expect(
    cache.setCalls[0]?.options === undefined,
    'SNAPSHOT_RUNTIME_PUBLISH_MUST_NOT_HAVE_TTL_OR_TAGS',
  )
  expect(
    selectPublishedRuntimeSnapshot(stored, bundledVerifiedSnapshot(), testNowMs)?.snapshot_as_of
      === published.snapshot_as_of,
    'SNAPSHOT_RUNTIME_PUBLISH_NEWER_SELECTED',
  )

  const olderPublished = structuredClone(published)
  olderPublished.snapshot_as_of = new Date(baselineMs + 30 * 1000).toISOString()
  let rollbackFailure = null
  try {
    await publishVerifiedSnapshotToRuntimeCache(olderPublished, { cache, nowMs: testNowMs })
  } catch (error) {
    rollbackFailure = error
  }
  expect(
    rollbackFailure?.message === 'RUNTIME_SNAPSHOT_ROLLBACK_REJECTED',
    'SNAPSHOT_RUNTIME_PUBLISH_ROLLBACK_REJECTED',
  )

  const conflictingPublished = structuredClone(published)
  conflictingPublished.input_candidate_count += 1
  let conflictFailure = null
  try {
    await publishVerifiedSnapshotToRuntimeCache(conflictingPublished, { cache, nowMs: testNowMs })
  } catch (error) {
    conflictFailure = error
  }
  expect(
    conflictFailure?.message === 'RUNTIME_SNAPSHOT_REVISION_CONFLICT',
    'SNAPSHOT_RUNTIME_PUBLISH_REVISION_CONFLICT_REJECTED',
  )

  const invalidPublished = structuredClone(published)
  invalidPublished.cards[0].facts.verification_status = 'PARTIAL'
  let invalidPublishFailure = null
  try {
    await publishVerifiedSnapshotToRuntimeCache(invalidPublished, { cache, nowMs: testNowMs })
  } catch (error) {
    invalidPublishFailure = error
  }
  expect(
    /^VERIFIED_SNAPSHOT_CARD_NOT_VERIFIED:/.test(invalidPublishFailure?.message ?? ''),
    'SNAPSHOT_RUNTIME_PUBLISH_INVALID_REJECTED',
  )

  const futurePublished = structuredClone(published)
  futurePublished.snapshot_as_of = new Date(testNowMs + 16 * 60 * 1000).toISOString()
  let futureFailure = null
  try {
    await publishVerifiedSnapshotToRuntimeCache(futurePublished, { cache: memoryCache(), nowMs: testNowMs })
  } catch (error) {
    futureFailure = error
  }
  expect(
    futureFailure?.message === 'RUNTIME_SNAPSHOT_FUTURE_REJECTED',
    'SNAPSHOT_RUNTIME_PUBLISH_FUTURE_REJECTED',
  )
  expect(
    selectPublishedRuntimeSnapshot(futurePublished, bundledVerifiedSnapshot(), testNowMs) === null,
    'SNAPSHOT_RUNTIME_FUTURE_NOT_SELECTED',
  )

  let endpoint = await invokeSnapshot('GET')
  expect(endpoint.statusCode === 200, 'SNAPSHOT_ENDPOINT_GET_STATUS')
  expect(endpoint.body?.schema_version === '0.1', 'SNAPSHOT_ENDPOINT_GET_BODY')
  expect(
    endpoint.headers['x-medicalchannelai-snapshot-source'] === 'BUNDLED',
    'SNAPSHOT_ENDPOINT_BUNDLED_SOURCE',
  )
  endpoint = await invokeSnapshot('DELETE')
  expect(endpoint.statusCode === 405, 'SNAPSHOT_ENDPOINT_DELETE_STATUS')
  endpoint = await invokeSnapshot('PUT', { body: bundledVerifiedSnapshot() })
  expect(endpoint.statusCode === 503, 'SNAPSHOT_PUBLISH_MISSING_SERVER_TOKEN_FAILS_CLOSED')
  process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = 'test-publish-token-1234567890'
  endpoint = await invokeSnapshot('PUT', {
    body: bundledVerifiedSnapshot(),
    headers: { authorization: 'Bearer wrong-token' },
  })
  expect(endpoint.statusCode === 401, 'SNAPSHOT_PUBLISH_BAD_TOKEN_REJECTED')

  process.env.VERIFIED_SNAPSHOT_URL = 'http://snapshot.example/data.json'
  clearVerifiedSnapshotCacheForTests()
  let invalidUrlError = null
  try {
    await loadVerifiedSnapshot()
  } catch (error) {
    invalidUrlError = error
  }
  expect(
    invalidUrlError?.message === 'VERIFIED_SNAPSHOT_URL_NOT_HTTPS',
    'SNAPSHOT_HTTP_REMOTE_MUST_BE_REJECTED',
  )

  process.env.VERIFIED_SNAPSHOT_URL = 'https://snapshot.example/data.json'
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async () => ({ ok: false, status: 503 })
  let remoteFailure = null
  try {
    await loadVerifiedSnapshot()
  } catch (error) {
    remoteFailure = error
  }
  expect(
    remoteFailure?.message === 'VERIFIED_SNAPSHOT_HTTP_503',
    'SNAPSHOT_REMOTE_FAILURE_MUST_NOT_FALL_BACK',
  )
  clearVerifiedSnapshotCacheForTests()
  endpoint = await invokeSnapshot('GET')
  expect(endpoint.statusCode === 503, 'SNAPSHOT_ENDPOINT_REMOTE_FAILURE_STATUS')
  expect(
    endpoint.body?.error === 'VERIFIED_SNAPSHOT_UNAVAILABLE',
    'SNAPSHOT_ENDPOINT_REMOTE_FAILURE_CODE',
  )

  const internalFieldPayload = structuredClone(bundledVerifiedSnapshot())
  internalFieldPayload.cards[0].provider = 'must-never-reach-browser'
  await expectRemoteRejected(
    internalFieldPayload,
    /^VERIFIED_SNAPSHOT_INTERNAL_FIELD:/,
    'SNAPSHOT_REMOTE_INTERNAL_FIELD_MUST_BE_REJECTED',
  )

  const privateContextPayload = structuredClone(bundledVerifiedSnapshot())
  privateContextPayload.cards[0].customer_context.hospital_relationship = {
    hospital_name: '不得进入公共快照',
  }
  await expectRemoteRejected(
    privateContextPayload,
    /^VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:/,
    'SNAPSHOT_REMOTE_PRIVATE_CONTEXT_MUST_BE_REJECTED',
  )

  const unverifiedPayload = structuredClone(bundledVerifiedSnapshot())
  unverifiedPayload.cards[0].facts.verification_status = 'PARTIAL'
  await expectRemoteRejected(
    unverifiedPayload,
    /^VERIFIED_SNAPSHOT_CARD_NOT_VERIFIED:/,
    'SNAPSHOT_REMOTE_UNVERIFIED_CARD_MUST_BE_REJECTED',
  )

  const legacyRankingPayload = structuredClone(bundledVerifiedSnapshot())
  legacyRankingPayload.cards[0].priority.score_type = 'ZERO_CONFIG_PUBLIC_FACTS_ONLY'
  await expectRemoteRejected(
    legacyRankingPayload,
    /^VERIFIED_SNAPSHOT_RANKING_VERSION_INVALID:/,
    'SNAPSHOT_REMOTE_V1_RANKING_MUST_BE_REJECTED',
  )

  const wrongRankingMaxPayload = structuredClone(bundledVerifiedSnapshot())
  wrongRankingMaxPayload.cards[0].priority.components.find(
    (item) => item.code === 'INTERVENTION_STAGE',
  ).max_points = 40
  await expectRemoteRejected(
    wrongRankingMaxPayload,
    /^VERIFIED_SNAPSHOT_PRIORITY_COMPONENT_INVALID:/,
    'SNAPSHOT_REMOTE_V1_MAX_POINTS_MUST_BE_REJECTED',
  )

  const privateScorePayload = structuredClone(bundledVerifiedSnapshot())
  const privateComponent = privateScorePayload.cards[0].priority.components.find(
    (item) => item.code === 'RELATIONSHIP',
  )
  privateComponent.points = 1
  privateScorePayload.cards[0].priority.score += 1
  await expectRemoteRejected(
    privateScorePayload,
    /^VERIFIED_SNAPSHOT_PRIVATE_SCORE_PRESENT:/,
    'SNAPSHOT_REMOTE_ZERO_CONFIG_PRIVATE_SCORE_MUST_BE_REJECTED',
  )

  const insecureEvidencePayload = structuredClone(bundledVerifiedSnapshot())
  insecureEvidencePayload.cards[0].evidence_source_urls = ['http://example.com/not-official']
  await expectRemoteRejected(
    insecureEvidencePayload,
    /^VERIFIED_SNAPSHOT_EVIDENCE_INVALID:/,
    'SNAPSHOT_REMOTE_HTTP_EVIDENCE_MUST_BE_REJECTED',
  )

  const badCardCountPayload = structuredClone(bundledVerifiedSnapshot())
  badCardCountPayload.card_count += 1
  await expectRemoteRejected(
    badCardCountPayload,
    'VERIFIED_SNAPSHOT_CARD_COUNT_MISMATCH',
    'SNAPSHOT_REMOTE_CARD_COUNT_MUST_MATCH',
  )

  const poolPayload = structuredClone(bundledVerifiedSnapshot())
  poolPayload.opportunity_pool = structuredClone(poolPayload.cards)
  poolPayload.opportunity_pool_count = poolPayload.opportunity_pool.length
  poolPayload.matched_count = poolPayload.opportunity_pool.length
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    text: async () => JSON.stringify(poolPayload),
  })
  const poolRemote = await loadVerifiedSnapshot()
  expect(
    poolRemote.opportunity_pool_count === poolRemote.opportunity_pool.length,
    'SNAPSHOT_REMOTE_POOL_VALID',
  )

  const badPoolCountPayload = structuredClone(poolPayload)
  badPoolCountPayload.opportunity_pool_count += 1
  await expectRemoteRejected(
    badPoolCountPayload,
    'VERIFIED_SNAPSHOT_POOL_COUNT_MISMATCH',
    'SNAPSHOT_REMOTE_POOL_COUNT_MUST_MATCH',
  )

  const badMatchedCountPayload = structuredClone(poolPayload)
  badMatchedCountPayload.matched_count += 1
  await expectRemoteRejected(
    badMatchedCountPayload,
    'VERIFIED_SNAPSHOT_MATCHED_COUNT_MISMATCH',
    'SNAPSHOT_REMOTE_MATCHED_COUNT_MUST_MATCH',
  )

  clearVerifiedSnapshotCacheForTests()
  endpoint = await invokeSnapshot('GET')
  expect(endpoint.statusCode === 503, 'SNAPSHOT_ENDPOINT_INVALID_REMOTE_STATUS')
  expect(
    endpoint.body?.error === 'VERIFIED_SNAPSHOT_UNAVAILABLE',
    'SNAPSHOT_ENDPOINT_INVALID_REMOTE_CODE',
  )

  const remotePayload = structuredClone(bundledVerifiedSnapshot())
  remotePayload.snapshot_as_of = '2026-08-31T12:34:56+08:00'
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    text: async () => JSON.stringify(remotePayload),
  })
  const remote = await loadVerifiedSnapshot()
  expect(remote.snapshot_as_of === remotePayload.snapshot_as_of, 'SNAPSHOT_REMOTE_AS_OF')
  expect(remote !== bundled, 'SNAPSHOT_REMOTE_NOT_BUNDLED')
  endpoint = await invokeSnapshot('GET')
  expect(endpoint.statusCode === 200, 'SNAPSHOT_ENDPOINT_REMOTE_STATUS')
  expect(
    endpoint.headers['x-medicalchannelai-snapshot-source'] === 'REMOTE',
    'SNAPSHOT_ENDPOINT_REMOTE_SOURCE',
  )

  console.log('Verified snapshot checks: PASS')
} finally {
  clearVerifiedSnapshotCacheForTests()
  globalThis.fetch = savedFetch
  if (savedRemote === undefined) delete process.env.VERIFIED_SNAPSHOT_URL
  else process.env.VERIFIED_SNAPSHOT_URL = savedRemote
  if (savedPublicRemote === undefined) delete process.env.VITE_VERIFIED_SNAPSHOT_URL
  else process.env.VITE_VERIFIED_SNAPSHOT_URL = savedPublicRemote
  if (savedPublishToken === undefined) delete process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN
  else process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = savedPublishToken
}
