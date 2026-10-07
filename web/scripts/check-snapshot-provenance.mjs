import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import { createServer } from 'vite'
import {
  loadCollectorCollectionStatus,
  validateVerifiedSnapshot,
} from '../api/_verifiedSnapshot.js'

function expect(condition, code) {
  if (!condition) throw new Error(code)
}

const source = readFileSync(new URL('../src/services/runtimeStatusApi.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const api = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

const now = Date.now()
const revision = new Date(now - 5 * 60_000).toISOString()
const statusValue = {
  schema_version: '0.1', service: 'MedicalChannelAI', ready: true, degraded: false,
  production_ready: false, ai: { configured: true },
  collection: { available: true, outcome: 'COMPLETED', attempted_at: revision, completed_at: revision, failures: [] },
  snapshot: {
    available: true, source_mode: 'DATABASE', runtime_origin: null,
    snapshot_as_of: revision, freshness: 'FRESH', age_minutes: 5,
    stale_after_minutes: 1800, today_card_count: 1, opportunity_pool_count: 1,
    degraded: false, collection_coverage: {
      complete: true, last_complete_as_of: revision, updated_source_ids: [], failed_source_ids: [],
    },
  },
}
const meta = {
  snapshot_as_of: revision, source: 'DATABASE', degraded: false, reason: null,
  collection_coverage: statusValue.snapshot.collection_coverage,
}

api.clearRuntimeStatusCacheForTests()
globalThis.fetch = async () => ({ ok: true, json: async () => statusValue })
let loaded = await api.getRuntimeStatus()
expect(api.runtimeSnapshotWarning(loaded, true, meta) === null, 'DISPLAYED_REVISION_MATCHES_STATUS')
expect(api.runtimeAutomationUnavailableReason(loaded, true, meta) === null, 'MATCHED_REVISION_AUTOMATION_AVAILABLE')
const originalDateNow = Date.now
Date.now = () => Date.parse(revision) + 31 * 60 * 60_000
expect(api.runtimeSnapshotWarning(loaded, true, meta)?.includes('31 小时'), 'ELAPSED_DISPLAY_CLOCK_BECOMES_STALE')
expect(Boolean(api.runtimeAutomationUnavailableReason(loaded, true, meta)), 'ELAPSED_DISPLAY_CLOCK_BLOCKS_AUTOMATION')
Date.now = originalDateNow

const staleMeta = { ...meta, snapshot_as_of: new Date(now - 72 * 60 * 60_000).toISOString() }
expect(api.runtimeSnapshotWarning(loaded, true, staleMeta)?.includes('版本或来源与服务端状态不一致'), 'STALE_DISPLAY_REVISION_WARNED')
expect(Boolean(api.runtimeAutomationUnavailableReason(loaded, true, staleMeta)), 'STALE_DISPLAY_REVISION_BLOCKED')
const staleStatus = {
  ...statusValue,
  degraded: true,
  snapshot: {
    ...statusValue.snapshot,
    snapshot_as_of: staleMeta.snapshot_as_of,
    freshness: 'STALE',
    age_minutes: 4320,
    collection_coverage: { ...statusValue.snapshot.collection_coverage, last_complete_as_of: staleMeta.snapshot_as_of },
  },
}
const staleMatchingMeta = { ...meta, ...staleStatus.snapshot.collection_coverage, snapshot_as_of: staleMeta.snapshot_as_of }
expect(api.runtimeSnapshotWarning(staleStatus, true, staleMatchingMeta)?.includes('72'), 'MATCHED_OLD_REVISION_STALE_WARNING')
expect(Boolean(api.runtimeAutomationUnavailableReason(staleStatus, true, staleMatchingMeta)), 'MATCHED_OLD_REVISION_STALE_BLOCKED')
const sourceMismatch = { ...meta, source: 'RUNTIME_CACHE', runtime_origin: 'BUNDLED' }
expect(api.runtimeSnapshotWarning(loaded, true, sourceMismatch)?.includes('版本或来源'), 'SAME_CLOCK_SOURCE_MISMATCH_WARNED')
expect(Boolean(api.runtimeAutomationUnavailableReason(loaded, true, sourceMismatch)), 'SAME_CLOCK_SOURCE_MISMATCH_BLOCKED')
for (const unknownMeta of [
  { ...meta, snapshot_as_of: null },
  { ...meta, snapshot_as_of: 'invalid-date' },
  { ...meta, snapshot_as_of: new Date(now + 60 * 60_000).toISOString() },
  null,
]) {
  expect(Boolean(api.runtimeSnapshotWarning(loaded, true, unknownMeta)), 'MISSING_INVALID_FUTURE_OR_UNKNOWN_CLOCK_WARNED')
  expect(Boolean(api.runtimeAutomationUnavailableReason(loaded, true, unknownMeta)), 'MISSING_INVALID_FUTURE_OR_UNKNOWN_CLOCK_BLOCKED')
}

for (const degradedMeta of [
  { ...meta, source: 'BUNDLED_FALLBACK', degraded: true, reason: 'RUNTIME_CACHE_READ_FAILED' },
  { ...meta, source: 'EXTERNAL', degraded: true, reason: 'SNAPSHOT_SOURCE_UNKNOWN' },
  { ...meta, degraded: true, reason: 'REMOTE_REFRESH_FAILED' },
  { ...meta, degraded: true, reason: 'COLLECTION_COVERAGE_PARTIAL', collection_coverage: { complete: false, last_complete_as_of: null, updated_source_ids: ['tjmugh'], failed_source_ids: ['ccgp_regional'] } },
  { ...meta, degraded: true, reason: 'COLLECTION_COVERAGE_UNKNOWN', collection_coverage: null },
]) {
  expect(Boolean(api.runtimeSnapshotWarning(loaded, true, degradedMeta)), `DEGRADED_META_WARNED:${degradedMeta.reason}`)
  expect(Boolean(api.runtimeAutomationUnavailableReason(loaded, true, degradedMeta)), `DEGRADED_META_BLOCKED:${degradedMeta.reason}`)
}

const failedCollectorStatus = {
  ...statusValue,
  degraded: true,
  degraded_reason: 'COLLECTION_BLOCKED',
  collection: {
    available: true, outcome: 'BLOCKED', attempted_at: revision, completed_at: null,
    failures: [{ source_id: 'ccgp_regional', market_code: 'CN-TJ', stage: 'regional_bj', category: 'ACCESS_DENIED', error_code: 'HTTP_403' }],
  },
}
expect(api.runtimeSnapshotWarning(failedCollectorStatus, true, meta)?.includes('HTTP_403'), 'RECENT_COLLECTOR_FAILURE_IDENTIFIED')
expect(Boolean(api.runtimeAutomationUnavailableReason(failedCollectorStatus, true, meta)), 'RECENT_COLLECTOR_FAILURE_BLOCKED')

api.clearRuntimeStatusCacheForTests()
globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => statusValue })
loaded = await api.getRuntimeStatus()
expect(loaded === null, 'HTTP_503_BODY_NOT_ACCEPTED_AS_STATUS')
expect(Boolean(api.runtimeSnapshotWarning(loaded, true, meta)), 'HTTP_503_UNKNOWN_WARNED')
expect(Boolean(api.runtimeAutomationUnavailableReason(loaded, true, meta)), 'HTTP_503_AUTOMATION_BLOCKED')

api.clearRuntimeStatusCacheForTests()
const pendingStatusResponses = []
globalThis.fetch = () => new Promise((resolve) => pendingStatusResponses.push(resolve))
const supersededStatusRequest = api.getRuntimeStatus()
const latestStatusRequest = api.getRuntimeStatus(true)
const newestStatus = { ...statusValue, snapshot: { ...statusValue.snapshot, snapshot_as_of: new Date(now + 60_000).toISOString() } }
pendingStatusResponses[1]({ ok: true, json: async () => newestStatus })
expect((await latestStatusRequest)?.snapshot.snapshot_as_of === newestStatus.snapshot.snapshot_as_of, 'FORCED_STATUS_NEW_REVISION_RETURNED')
pendingStatusResponses[0]({ ok: true, json: async () => statusValue })
expect(await supersededStatusRequest === null, 'LATE_OLD_STATUS_REQUEST_DISCARDED')
expect((await api.getRuntimeStatus())?.snapshot.snapshot_as_of === newestStatus.snapshot.snapshot_as_of, 'LATE_OLD_STATUS_DID_NOT_REPLACE_CACHE')

const complete = await loadCollectorCollectionStatus(async () => ({
  stages: {
    regional_bj: { status: 'FAILED', terminal: true, started_at: revision, completed_at: revision, diagnostics: [{
      source_id: 'ccgp_regional', market_code: 'CN-BJ', stage: 'index_discovery', category: 'ACCESS_DENIED', error_code: 'HTTP_403', official_url: 'https://private.invalid/path',
    }] },
    publish: { status: 'BLOCKED', terminal: true, started_at: revision, completed_at: revision, diagnostics: [] },
  },
}))
expect(complete.outcome === 'FAILED', 'PARTIAL_SOURCE_FAILURE_BLOCKS_CYCLE')
expect(complete.failures[0]?.error_code === 'HTTP_403', 'PUBLIC_FAILURE_CODE_PRESENT')
expect(!JSON.stringify(complete).includes('private.invalid'), 'PUBLIC_FAILURE_URL_OMITTED')
const tolerated = await loadCollectorCollectionStatus(async () => ({
  stages: {
    regional_bj: { status: 'COMPLETED', terminal: true, started_at: revision, completed_at: revision, diagnostics: [{
      source_id: 'ccgp_regional', market_code: 'CN-BJ', stage: 'verified_detail', category: 'PARSER_REJECTED', error_code: 'DETAIL_REJECTED',
    }] },
    publish: { status: 'COMPLETED', terminal: true, started_at: revision, completed_at: revision, diagnostics: [] },
  },
}))
expect(tolerated.outcome === 'COMPLETED', 'TOLERATED_DETAIL_FAILURE_DOES_NOT_BLOCK_CYCLE')
expect(tolerated.warnings[0]?.error_code === 'DETAIL_REJECTED', 'TOLERATED_DIAGNOSTIC_REMAINS_LOCATABLE')

// Mirrors collector_runtime.py's regional incremental coverage IDs.
const pythonRegionalCoverageFixture = {
  complete: false,
  last_complete_as_of: new Date(Date.parse(revision) - 86_400_000).toISOString(),
  updated_source_ids: ['ccgp_regional:he'],
  failed_source_ids: ['ccgp_regional:bj'],
}
const bundledFixture = JSON.parse(readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'))
const regionalSnapshot = validateVerifiedSnapshot({
  ...bundledFixture,
  snapshot_as_of: revision,
  collection_coverage: pythonRegionalCoverageFixture,
})
expect(regionalSnapshot.collection_coverage.updated_source_ids[0] === 'ccgp_regional:he', 'PYTHON_REGIONAL_UPDATED_SOURCE_ACCEPTED')
expect(regionalSnapshot.collection_coverage.failed_source_ids[0] === 'ccgp_regional:bj', 'PYTHON_REGIONAL_FAILED_SOURCE_ACCEPTED')
let invalidRegionalSourceRejected = false
try {
  validateVerifiedSnapshot({
    ...bundledFixture,
    snapshot_as_of: revision,
    collection_coverage: { ...pythonRegionalCoverageFixture, updated_source_ids: ['ccgp_regional:he:extra'] },
  })
} catch (error) {
  invalidRegionalSourceRejected = error?.message === 'VERIFIED_SNAPSHOT_COVERAGE_INVALID'
}
expect(invalidRegionalSourceRejected, 'MULTIPLE_REGIONAL_DELIMITERS_REJECTED')

const regionalDiagnostic = await loadCollectorCollectionStatus(async () => ({
  stages: {
    regional_he: { status: 'FAILED', terminal: true, started_at: revision, completed_at: revision, diagnostics: [{
      source_id: 'ccgp_regional:he', market_code: 'HE', stage: 'regional_he', category: 'ACCESS_DENIED', error_code: 'HTTP_403',
    }] },
    publish: { status: 'BLOCKED', terminal: true, started_at: revision, completed_at: revision, diagnostics: [] },
  },
}))
expect(regionalDiagnostic.failures[0]?.source_id === 'ccgp_regional:he', 'PYTHON_REGIONAL_DIAGNOSTIC_SOURCE_PRESERVED')

console.log('Snapshot provenance behavior checks: PASS')

// Exercise the actual static service through Vite's TS/alias loader. A failed
// refresh must keep the displayed payload clock and mark that loaded copy stale.
const vite = await createServer({
  configFile: resolve(new URL('../vite.config.ts', import.meta.url).pathname),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})
const stored = new Map()
globalThis.window = { location: { origin: 'https://app.example' } }
globalThis.localStorage = {
  getItem(key) { return stored.get(key) ?? null },
  setItem(key, value) { stored.set(key, String(value)) },
  removeItem(key) { stored.delete(key) },
}
const bundledPath = new URL('../public/data/today-actions.public.json', import.meta.url)
const bundled = JSON.parse(readFileSync(bundledPath, 'utf8'))
const realNow = Date.now
let fakeNow = realNow()
Date.now = () => fakeNow
let fetchCalls = 0
globalThis.fetch = async () => {
  fetchCalls += 1
  if (fetchCalls === 1) {
    return {
      ok: true,
      headers: { get(name) { return name.toLowerCase() === 'x-medicalchannelai-snapshot-source' ? 'DATABASE' : null } },
      async json() { return structuredClone(bundled) },
    }
  }
  if (fetchCalls === 2) throw new Error('OFFLINE_REFRESH')
  const newer = structuredClone(bundled)
  newer.snapshot_as_of = new Date(Date.parse(bundled.snapshot_as_of) + 60_000).toISOString()
  return {
    ok: true,
    headers: { get(name) { return name.toLowerCase() === 'x-medicalchannelai-snapshot-source' ? 'DATABASE' : null } },
    async json() { return newer },
  }
}
try {
  const { StaticSnapshotTodayActionsService } = await vite.ssrLoadModule('/src/services/StaticSnapshotTodayActionsService.ts')
  const client = await vite.ssrLoadModule('/src/services/verifiedSnapshotClient.ts')
  const service = new StaticSnapshotTodayActionsService('https://app.example/api/public-snapshot')
  const first = await service.getTodayActions()
  expect(first.refreshed_at === bundled.snapshot_as_of, 'STATIC_SERVICE_USES_PAYLOAD_CLOCK')
  fakeNow += 60_001
  const afterFailure = await service.getTodayActions()
  expect(fetchCalls === 2, 'STATIC_SERVICE_RETRIES_AFTER_TTL')
  expect(afterFailure.refreshed_at === bundled.snapshot_as_of, 'STATIC_SERVICE_FAILURE_DOES_NOT_ADVANCE_CLOCK')
  expect(afterFailure.snapshot_meta?.degraded === true, 'STATIC_SERVICE_FAILURE_MARKED_DEGRADED')
  expect(afterFailure.snapshot_meta?.reason === 'SNAPSHOT_REFRESH_FAILED', 'STATIC_SERVICE_FAILURE_REASON')
  fakeNow += 60_001
  const afterRecovery = await service.getTodayActions()
  expect(fetchCalls === 3, 'STATIC_SERVICE_RETRIES_UNTIL_SUCCESS')
  expect(afterRecovery.refreshed_at === new Date(Date.parse(bundled.snapshot_as_of) + 60_000).toISOString(), 'STATIC_SERVICE_SUCCESS_USES_NEW_PAYLOAD_CLOCK')
  expect(afterRecovery.snapshot_meta?.reason === 'COLLECTION_COVERAGE_UNKNOWN', 'LEGACY_COVERAGE_REMAINS_UNKNOWN')
  console.log('Static snapshot last-good behavior checks: PASS')

  client.resetVerifiedSnapshotClient()
  let clientCalls = 0
  globalThis.fetch = async (_url, _init) => {
    clientCalls += 1
    if (clientCalls === 1) return {
      ok: true,
      headers: { get() { return null } },
      async json() { return {
        schema_version: '0.1', mode: 'TODAY_ACTIONS', snapshot_as_of: revision,
        cards: [], card_count: 0, collection_coverage: {
          complete: false, last_complete_as_of: null,
          updated_source_ids: ['ccgp_regional:he'], failed_source_ids: ['ccgp_regional:bj'],
        },
      } },
    }
    if (clientCalls === 2) return { ok: false, status: 503, headers: { get() { return null } } }
    return {
      ok: true,
      headers: { get() { return null } },
      async json() { return {
        schema_version: '0.1', mode: 'TODAY_ACTIONS', snapshot_as_of: revision,
        cards: [], card_count: 0, collection_coverage: {
          complete: true, last_complete_as_of: revision, updated_source_ids: [], failed_source_ids: [],
        },
      } },
    }
  }
  const external = await client.loadVerifiedSnapshot('https://other.example/snapshot.json')
  expect(external.meta.source === 'EXTERNAL' && external.meta.degraded, 'EXTERNAL_SOURCE_HEADER_ABSENCE_DEGRADED')
  expect(external.meta.collection_coverage?.updated_source_ids[0] === 'ccgp_regional:he', 'CLIENT_PRESERVES_PYTHON_REGIONAL_SOURCE_ID')
  fakeNow += 60_001
  let clientFailure = null
  try { await client.loadVerifiedSnapshot('https://other.example/snapshot.json') } catch (error) { clientFailure = error }
  expect(clientFailure?.message === 'SNAPSHOT_HTTP_503', 'CLIENT_REJECTS_HTTP_FAILURE')
  await client.loadVerifiedSnapshot('https://other.example/snapshot.json')
  expect(clientCalls === 3, 'CLIENT_FAILED_REFRESH_RETRIES_IMMEDIATELY')
  client.resetVerifiedSnapshotClient()
  globalThis.fetch = async () => ({
    ok: true,
    url: 'https://attacker.example/redirected.json',
    headers: { get(name) { return name.toLowerCase() === 'x-medicalchannelai-snapshot-source' ? 'DATABASE' : null } },
    async json() { return { ...bundled, snapshot_as_of: revision } },
  })
  const spoofedExternal = await client.loadVerifiedSnapshot('https://other.example/snapshot.json')
  expect(spoofedExternal.meta.source === 'EXTERNAL' && spoofedExternal.meta.degraded, 'EXTERNAL_HEADER_CANNOT_ASSERT_DATABASE')
  client.resetVerifiedSnapshotClient()
  const redirectedSameOrigin = await client.loadVerifiedSnapshot('https://app.example/api/public-snapshot')
  expect(redirectedSameOrigin.meta.source === 'EXTERNAL' && redirectedSameOrigin.meta.degraded, 'CROSS_ORIGIN_REDIRECT_CANNOT_ASSERT_DATABASE')
  console.log('Snapshot client source and retry behavior checks: PASS')
} finally {
  Date.now = realNow
  await vite.close()
}
