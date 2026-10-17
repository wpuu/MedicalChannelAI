import { createHash } from 'node:crypto'
import { getCache } from '@vercel/functions'
import {
  latestPublicVerifiedSnapshotIfChanged,
  latestPublicVerifiedSnapshotForPublish,
} from './_publicIntelligenceDb.js'
import bundledSnapshot from '../public/data/today-actions.public.json' with { type: 'json' }
import { filterSnapshotToMedicalChannel } from './_medicalChannelScope.js'

const REMOTE_CACHE_TTL_MS = 60 * 1000
const REMOTE_TIMEOUT_MS = 6000
const MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
const MAX_RUNTIME_SNAPSHOT_BYTES = 1900 * 1024
const MAX_TODAY_CARDS = 5
const MAX_OPPORTUNITY_POOL = 500
// Regional coverage source IDs use a single lowercase two-letter suffix,
// e.g. `ccgp_regional:he`. Keep all other source IDs on the legacy grammar.
const SAFE_SOURCE_ID = /^(?:[a-zA-Z0-9_.-]{1,80}|[a-zA-Z0-9_.-]{1,77}:[a-z]{2})$/
const RUNTIME_SNAPSHOT_FUTURE_TOLERANCE_MS = 15 * 60 * 1000
const BUNDLED_SNAPSHOT_REVISION = String(bundledSnapshot?.snapshot_as_of || 'unknown')
  .replace(/[^0-9A-Za-z]/g, '')
  .slice(0, 40) || 'unknown'
// The exact bundled revision remains the rollback-safe cache seed. Separately,
// the authenticated GitHub verified-data publisher may update PUBLISHED_RUNTIME_SNAPSHOT_KEY
// without deploying code. Vercel Runtime Cache isolates Preview and Production.
const BUNDLED_RUNTIME_SNAPSHOT_KEY =
  `medicalchannelai:verified-snapshot:${BUNDLED_SNAPSHOT_REVISION}:v3`
const PUBLISHED_RUNTIME_SNAPSHOT_KEY = 'medicalchannelai:verified-snapshot:published:v2'
const COLLECTOR_RUNTIME_STATE_KEY = 'medicalchannelai:collector-runtime-state:v2'
const BUNDLED_RUNTIME_SNAPSHOT_TTL_SECONDS = 7 * 24 * 60 * 60
const ZERO_CONFIG_SCORE_TYPE_V2 = 'ZERO_CONFIG_PUBLIC_FACTS_V2'
const V2_PRIORITY_MAX_POINTS = new Map([
  ['PRODUCT_EXECUTION_CAPABILITY', 25],
  ['RELATIONSHIP', 10],
  ['EXECUTION_FLEXIBILITY', 5],
  ['INTERVENTION_STAGE', 25],
  ['DEADLINE_URGENCY', 10],
  ['PROJECT_AMOUNT', 10],
  ['PRODUCT_SPECIFICITY', 8],
  ['PUBLICATION_FRESHNESS', 7],
])
const ZERO_CONFIG_PRIVATE_COMPONENTS = new Set([
  'PRODUCT_EXECUTION_CAPABILITY',
  'RELATIONSHIP',
  'EXECUTION_FLEXIBILITY',
])
const ZERO_CONFIG_PUBLIC_SCORE_MAX = 60

const FORBIDDEN_PUBLIC_KEYS = new Set([
  'model_requests', 'model_input', 'task_payloads', 'agnes_dispatch_plan', 'lease', 'lease_id',
  'provider', 'api_key', 'upstream_model', 'completion_nonce', 'task_id', 'private_key',
  'access_token', 'refresh_token',
])
const FORBIDDEN_PUBLIC_PREFIXES = [
  'model_input_', 'agnes_dispatch_', 'provider_', 'lease_', 'api_key_', 'upstream_model_',
  'private_key_', 'access_token_', 'refresh_token_',
]

let remoteCache = null
let remoteInFlight = null
// Warm-instance memo for the durable (Neon) snapshot. Every API request used to
// download the full ~1.5MB JSONB payload and deep-validate it 3 times
// (~90ms CPU); the pilot AI path did this twice per request. Now a warm
// instance re-checks only the snapshot_hash at most every
// DURABLE_RECHECK_MS and reuses the validated, scoped copy while the hash is
// unchanged. Callers always receive a private deep copy, so accidental
// mutation by one request can never leak into another.
const DURABLE_RECHECK_MS = 15 * 1000
let durableMemo = null
let durableInFlight = null
let durableSource = latestPublicVerifiedSnapshotIfChanged
let bundledScopedMemo = null
let lastSourceMode = 'BUNDLED'
let lastRuntimeOrigin = null
let runtimePublishQueue = Promise.resolve()

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}
function assertPublicSnapshotBoundary(value, path = '$') {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertPublicSnapshotBoundary(item, `${path}[${index}]`))
    return
  }
  const record = asObject(value)
  if (!record) return
  for (const [key, child] of Object.entries(record)) {
    const normalized = key.toLowerCase()
    if (FORBIDDEN_PUBLIC_KEYS.has(normalized) || FORBIDDEN_PUBLIC_PREFIXES.some((prefix) => normalized.startsWith(prefix))) {
      throw new Error(`VERIFIED_SNAPSHOT_INTERNAL_FIELD:${path}.${key}`)
    }
    assertPublicSnapshotBoundary(child, `${path}.${key}`)
  }
}
function assertHttpsUrl(value, code) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(code)
  let url
  try { url = new URL(value) } catch { throw new Error(code) }
  if (url.protocol !== 'https:') throw new Error(code)
}
function assertPublicCustomerContext(value, path) {
  const context = asObject(value)
  if (!context || context.context_type !== 'CUSTOMER_PRIVATE_FACTS') throw new Error(`VERIFIED_SNAPSHOT_CUSTOMER_CONTEXT_INVALID:${path}`)
  if (context.business_role !== null) throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.business_role`)
  if (context.hospital_relationship !== null) throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.hospital_relationship`)
  if (!Array.isArray(context.matching_product_capabilities) || context.matching_product_capabilities.length !== 0) throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.matching_product_capabilities`)
  const policy = asObject(context.partnering_policy)
  if (!policy) throw new Error(`VERIFIED_SNAPSHOT_CUSTOMER_CONTEXT_INVALID:${path}.partnering_policy`)
  for (const key of ['can_seek_temporary_manufacturer', 'can_cooperate_with_channel_partner', 'can_do_rental_projects']) {
    if (policy[key] !== null) throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.partnering_policy.${key}`)
  }
}
function assertV2Priority(value, path) {
  const priority = asObject(value)
  if (!priority || priority.score_type !== ZERO_CONFIG_SCORE_TYPE_V2) {
    throw new Error(`VERIFIED_SNAPSHOT_RANKING_VERSION_INVALID:${path}`)
  }
  if (!Array.isArray(priority.components) || priority.components.length !== V2_PRIORITY_MAX_POINTS.size) {
    throw new Error(`VERIFIED_SNAPSHOT_PRIORITY_COMPONENTS_INVALID:${path}`)
  }

  const seen = new Set()
  let score = 0
  for (const componentValue of priority.components) {
    const component = asObject(componentValue)
    const code = component?.code
    if (typeof code !== 'string' || seen.has(code) || !V2_PRIORITY_MAX_POINTS.has(code)) {
      throw new Error(`VERIFIED_SNAPSHOT_PRIORITY_COMPONENT_INVALID:${path}`)
    }
    seen.add(code)
    const expectedMax = V2_PRIORITY_MAX_POINTS.get(code)
    const points = component.points
    if (
      component.max_points !== expectedMax ||
      typeof points !== 'number' ||
      !Number.isInteger(points) ||
      points < 0 ||
      points > expectedMax
    ) {
      throw new Error(`VERIFIED_SNAPSHOT_PRIORITY_COMPONENT_INVALID:${path}.${code}`)
    }
    if (ZERO_CONFIG_PRIVATE_COMPONENTS.has(code) && points !== 0) {
      throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_SCORE_PRESENT:${path}.${code}`)
    }
    score += points
  }

  if (seen.size !== V2_PRIORITY_MAX_POINTS.size) {
    throw new Error(`VERIFIED_SNAPSHOT_PRIORITY_COMPONENTS_INVALID:${path}`)
  }
  if (
    typeof priority.score !== 'number' ||
    !Number.isInteger(priority.score) ||
    priority.score !== score ||
    priority.score < 0 ||
    priority.score > ZERO_CONFIG_PUBLIC_SCORE_MAX
  ) {
    throw new Error(`VERIFIED_SNAPSHOT_PRIORITY_SCORE_INVALID:${path}`)
  }
}
function assertPublicCard(value, path) {
  const card = asObject(value)
  if (!card || typeof card.opportunity_id !== 'string' || !card.opportunity_id.trim()) throw new Error(`VERIFIED_SNAPSHOT_CARD_INVALID:${path}`)
  const facts = asObject(card.facts)
  if (!facts || facts.verification_status !== 'VERIFIED') throw new Error(`VERIFIED_SNAPSHOT_CARD_NOT_VERIFIED:${path}`)
  if (!Array.isArray(card.evidence_source_urls) || card.evidence_source_urls.length === 0) throw new Error(`VERIFIED_SNAPSHOT_EVIDENCE_INVALID:${path}`)
  card.evidence_source_urls.forEach((url, index) => assertHttpsUrl(url, `VERIFIED_SNAPSHOT_EVIDENCE_INVALID:${path}.evidence_source_urls[${index}]`))
  assertPublicCustomerContext(card.customer_context, `${path}.customer_context`)
  assertV2Priority(card.priority, `${path}.priority`)
}
function assertUniqueOpportunityIds(items, code) {
  const seen = new Set()
  for (const item of items) {
    if (seen.has(item.opportunity_id)) throw new Error(code)
    seen.add(item.opportunity_id)
  }
  return seen
}
function configuredRemoteUrl() {
  const raw = (process.env.VERIFIED_SNAPSHOT_URL || process.env.VITE_VERIFIED_SNAPSHOT_URL || '').trim()
  if (!raw) return null
  let url
  try { url = new URL(raw) } catch { throw new Error('VERIFIED_SNAPSHOT_URL_INVALID') }
  const localDevelopment = process.env.NODE_ENV !== 'production' && (url.hostname === 'localhost' || url.hostname === '127.0.0.1') && (url.protocol === 'http:' || url.protocol === 'https:')
  if (url.protocol !== 'https:' && !localDevelopment) throw new Error('VERIFIED_SNAPSHOT_URL_NOT_HTTPS')
  return url.toString()
}
export function validateVerifiedSnapshot(value) {
  const snapshot = asObject(value)
  if (!snapshot) throw new Error('VERIFIED_SNAPSHOT_INVALID')
  assertPublicSnapshotBoundary(snapshot)
  if (snapshot.schema_version !== '0.1' || snapshot.mode !== 'TODAY_ACTIONS') throw new Error('VERIFIED_SNAPSHOT_SCHEMA_INVALID')
  if (typeof snapshot.snapshot_as_of !== 'string' || Number.isNaN(Date.parse(snapshot.snapshot_as_of))) throw new Error('VERIFIED_SNAPSHOT_AS_OF_INVALID')
  if (snapshot.collection_coverage !== undefined) {
    const coverage = asObject(snapshot.collection_coverage)
    if (!coverage || typeof coverage.complete !== 'boolean') throw new Error('VERIFIED_SNAPSHOT_COVERAGE_INVALID')
    if (coverage.last_complete_as_of !== null && coverage.last_complete_as_of !== undefined &&
      (typeof coverage.last_complete_as_of !== 'string' || Number.isNaN(Date.parse(coverage.last_complete_as_of)))) {
      throw new Error('VERIFIED_SNAPSHOT_COVERAGE_INVALID')
    }
    for (const field of ['updated_source_ids', 'failed_source_ids']) {
      const items = coverage[field]
      if (!Array.isArray(items) || items.length > 20 || items.some((item) => typeof item !== 'string' || !SAFE_SOURCE_ID.test(item))) {
        throw new Error('VERIFIED_SNAPSHOT_COVERAGE_INVALID')
      }
    }
    const completeMs = typeof coverage.last_complete_as_of === 'string'
      ? Date.parse(coverage.last_complete_as_of)
      : null
    const snapshotMs = Date.parse(snapshot.snapshot_as_of)
    if (coverage.complete === true &&
      (completeMs !== snapshotMs || coverage.failed_source_ids.length !== 0)) {
      throw new Error('VERIFIED_SNAPSHOT_COVERAGE_INVALID')
    }
    if (coverage.complete === false && completeMs !== null && completeMs > snapshotMs) {
      throw new Error('VERIFIED_SNAPSHOT_COVERAGE_INVALID')
    }
  }
  if (!Array.isArray(snapshot.cards) || snapshot.cards.length > MAX_TODAY_CARDS) throw new Error('VERIFIED_SNAPSHOT_CARDS_INVALID')
  if (snapshot.card_count !== snapshot.cards.length) throw new Error('VERIFIED_SNAPSHOT_CARD_COUNT_MISMATCH')
  snapshot.cards.forEach((card, index) => assertPublicCard(card, `$.cards[${index}]`))
  assertUniqueOpportunityIds(snapshot.cards, 'VERIFIED_SNAPSHOT_DUPLICATE_TOP5_ID')
  const pool = snapshot.opportunity_pool
  if (pool !== undefined) {
    if (!Array.isArray(pool) || pool.length > MAX_OPPORTUNITY_POOL) throw new Error('VERIFIED_SNAPSHOT_POOL_INVALID')
    pool.forEach((card, index) => assertPublicCard(card, `$.opportunity_pool[${index}]`))
    const poolIds = assertUniqueOpportunityIds(pool, 'VERIFIED_SNAPSHOT_DUPLICATE_POOL_ID')
    if (snapshot.opportunity_pool_count !== pool.length) throw new Error('VERIFIED_SNAPSHOT_POOL_COUNT_MISMATCH')
    if (snapshot.matched_count !== pool.length) throw new Error('VERIFIED_SNAPSHOT_MATCHED_COUNT_MISMATCH')
    if (snapshot.cards.some((item) => !poolIds.has(item.opportunity_id))) throw new Error('VERIFIED_SNAPSHOT_TOP5_NOT_IN_POOL')
  } else if (snapshot.matched_count !== snapshot.cards.length) {
    throw new Error('VERIFIED_SNAPSHOT_MATCHED_COUNT_MISMATCH')
  }
  return snapshot
}
function scopedVerifiedSnapshot(snapshot) {
  return validateVerifiedSnapshot(filterSnapshotToMedicalChannel(snapshot))
}
export function bundledVerifiedSnapshot() {
  return validateVerifiedSnapshot(bundledSnapshot)
}
function parsedSnapshotTime(snapshot) {
  return Date.parse(snapshot?.snapshot_as_of || '')
}
export function selectPublishedRuntimeSnapshot(value, bundled = bundledVerifiedSnapshot(), nowMs = Date.now()) {
  let candidate
  let baseline
  try {
    candidate = validateVerifiedSnapshot(value)
    baseline = validateVerifiedSnapshot(bundled)
  } catch {
    return null
  }
  const candidateMs = parsedSnapshotTime(candidate)
  const baselineMs = parsedSnapshotTime(baseline)
  if (!Number.isFinite(candidateMs) || !Number.isFinite(baselineMs)) return null
  if (candidateMs <= baselineMs) return null
  if (candidateMs > nowMs + RUNTIME_SNAPSHOT_FUTURE_TOLERANCE_MS) return null
  return candidate
}
export function selectDurableVerifiedSnapshot(value, bundled = bundledVerifiedSnapshot(), nowMs = Date.now()) {
  let candidate
  let baseline
  try {
    candidate = validateVerifiedSnapshot(value)
    baseline = validateVerifiedSnapshot(bundled)
  } catch {
    return null
  }
  const candidateMs = parsedSnapshotTime(candidate)
  const baselineMs = parsedSnapshotTime(baseline)
  if (!Number.isFinite(candidateMs) || !Number.isFinite(baselineMs)) return null
  // Durable Postgres is authoritative even when it stores the exact bundled
  // revision. Runtime Cache stays stricter and must be strictly newer.
  if (candidateMs < baselineMs) return null
  if (candidateMs > nowMs + RUNTIME_SNAPSHOT_FUTURE_TOLERANCE_MS) return null
  return candidate
}
function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  const record = asObject(value)
  if (!record) return JSON.stringify(value)
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(',')}}`
}
function verifiedSnapshotHash(value) {
  return createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex')
}

export async function preflightVerifiedSnapshotPublish(value, options = {}) {
  const snapshot = validateVerifiedSnapshot(value)
  const serialized = JSON.stringify(snapshot)
  if (Buffer.byteLength(serialized, 'utf8') > MAX_RUNTIME_SNAPSHOT_BYTES) {
    throw new Error('RUNTIME_SNAPSHOT_TOO_LARGE')
  }
  const nowMs = Number.isFinite(options.nowMs) ? options.nowMs : Date.now()
  const candidateMs = parsedSnapshotTime(snapshot)
  const bundled = bundledVerifiedSnapshot()
  const bundledMs = parsedSnapshotTime(bundled)
  if (candidateMs < bundledMs) throw new Error('RUNTIME_SNAPSHOT_OLDER_THAN_BUNDLE')
  if (candidateMs > nowMs + RUNTIME_SNAPSHOT_FUTURE_TOLERANCE_MS) {
    throw new Error('RUNTIME_SNAPSHOT_FUTURE_REJECTED')
  }

  const cache = options.cache || getCache()
  const currentValue = await cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
  let alreadyPublished = false
  let currentRuntimeSnapshot = null
  if (currentValue) {
    try {
      const current = validateVerifiedSnapshot(currentValue)
      currentRuntimeSnapshot = current
      const currentMs = parsedSnapshotTime(current)
      if (candidateMs < currentMs) throw new Error('RUNTIME_SNAPSHOT_ROLLBACK_REJECTED')
      if (candidateMs === currentMs) {
        if (canonicalJson(current) !== canonicalJson(snapshot)) throw new Error('RUNTIME_SNAPSHOT_REVISION_CONFLICT')
        alreadyPublished = true
      }
    } catch (error) {
      if (['RUNTIME_SNAPSHOT_ROLLBACK_REJECTED', 'RUNTIME_SNAPSHOT_REVISION_CONFLICT'].includes(error?.message)) throw error
      // Invalid cached state is replaceable by a fully validated publisher payload.
    }
  }

  const durableLatest = options.durableLatest === undefined
    ? await latestPublicVerifiedSnapshotForPublish()
    : options.durableLatest
  let expectedBaseHash = null
  let expectedBaseAsOf = null
  if (durableLatest?.payload) {
    let current
    try { current = validateVerifiedSnapshot(durableLatest.payload) } catch { throw new Error('PUBLIC_SNAPSHOT_DURABLE_CURRENT_INVALID') }
    const currentMs = parsedSnapshotTime(current)
    if (candidateMs < currentMs) throw new Error('PUBLIC_SNAPSHOT_ROLLBACK_REJECTED')
    if (candidateMs === currentMs && canonicalJson(current) !== canonicalJson(snapshot)) {
      throw new Error('PUBLIC_SNAPSHOT_REVISION_CONFLICT')
    }

    const candidateCoverage = asObject(snapshot.collection_coverage)
    const isCompleteSnapshot = candidateCoverage?.complete === true
    const durableMs = parsedSnapshotTime(current)
    expectedBaseHash = durableLatest.snapshot_hash || verifiedSnapshotHash(current)
    expectedBaseAsOf = current.snapshot_as_of
    const bundledMs = parsedSnapshotTime(bundledVerifiedSnapshot())
    if (!isCompleteSnapshot && durableMs > bundledMs) {
      const runtimeIsDurableBase = currentRuntimeSnapshot &&
        parsedSnapshotTime(currentRuntimeSnapshot) === durableMs &&
        canonicalJson(currentRuntimeSnapshot) === canonicalJson(current)
      const candidateIsDurableBase = candidateMs === durableMs && canonicalJson(snapshot) === canonicalJson(current)
      if (!runtimeIsDurableBase && !candidateIsDurableBase) {
        throw new Error('PUBLIC_SNAPSHOT_BASE_UNAVAILABLE')
      }
    }
  }

  const coverage = asObject(snapshot.collection_coverage)
  return {
    snapshot,
    serialized,
    cache,
    alreadyPublished,
    requireBaseMatch: coverage?.complete !== true,
    expectedBaseHash,
    expectedBaseAsOf,
  }
}

export async function publishVerifiedSnapshotToRuntimeCache(value, options = {}) {
  const preflight = options.preflight || await preflightVerifiedSnapshotPublish(value, options)
  const { snapshot, serialized, cache, alreadyPublished } = preflight
  const operation = async () => {
    const currentValue = await cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
    if (currentValue) {
      try {
        const current = validateVerifiedSnapshot(currentValue)
        const candidateMs = parsedSnapshotTime(snapshot)
        const currentMs = parsedSnapshotTime(current)
        if (candidateMs < currentMs) throw new Error('RUNTIME_SNAPSHOT_ROLLBACK_REJECTED')
        if (candidateMs === currentMs) {
          if (canonicalJson(current) !== canonicalJson(snapshot)) throw new Error('RUNTIME_SNAPSHOT_REVISION_CONFLICT')
          return current
        }
      } catch (error) {
        if (['RUNTIME_SNAPSHOT_ROLLBACK_REJECTED', 'RUNTIME_SNAPSHOT_REVISION_CONFLICT'].includes(error?.message)) throw error
        // Invalid cache state can be replaced by a completely validated payload.
      }
    } else if (alreadyPublished) {
      throw new Error('RUNTIME_SNAPSHOT_READBACK_FAILED')
    }

    // This is the authoritative latest verified snapshot, not an expendable cache entry.
    // Freshness is enforced from snapshot_as_of by /api/status and AI automation guards.
    // Do not attach TTL/tags here: cross-deployment TTL metadata can diverge and evict the
    // stable published key even while daily publisher round-trips are succeeding.
    await cache.set(PUBLISHED_RUNTIME_SNAPSHOT_KEY, snapshot)
    const readBack = await cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
    const verifiedReadBack = validateVerifiedSnapshot(readBack)
    if (canonicalJson(verifiedReadBack) !== canonicalJson(snapshot)) throw new Error('RUNTIME_SNAPSHOT_READBACK_MISMATCH')
    return verifiedReadBack
  }
  const queued = runtimePublishQueue.then(operation, operation)
  runtimePublishQueue = queued.then(() => undefined, () => undefined)
  return queued
}
async function fetchRemoteSnapshot(remoteUrl) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REMOTE_TIMEOUT_MS)
  try {
    const response = await fetch(remoteUrl, { method: 'GET', signal: controller.signal, headers: { Accept: 'application/json' }, cache: 'no-store' })
    if (!response.ok) throw new Error(`VERIFIED_SNAPSHOT_HTTP_${response.status}`)
    const declaredLength = Number(response.headers.get('content-length') || '0')
    if (declaredLength > MAX_SNAPSHOT_BYTES) throw new Error('VERIFIED_SNAPSHOT_TOO_LARGE')
    const text = await response.text()
    if (Buffer.byteLength(text, 'utf8') > MAX_SNAPSHOT_BYTES) throw new Error('VERIFIED_SNAPSHOT_TOO_LARGE')
    const snapshot = validateVerifiedSnapshot(JSON.parse(text))
    // Start the TTL after a valid response has actually been received and checked.
    remoteCache = { url: remoteUrl, expiresAt: Date.now() + REMOTE_CACHE_TTL_MS, snapshot }
    return { snapshot, degraded: false, reason: null }
  } finally {
    clearTimeout(timeout)
  }
}
async function loadRemoteSnapshot(remoteUrl) {
  if (remoteCache?.url === remoteUrl && remoteCache.expiresAt > Date.now()) {
    return { snapshot: remoteCache.snapshot, degraded: false, reason: null }
  }
  if (remoteInFlight?.url === remoteUrl) return remoteInFlight.promise
  const request = fetchRemoteSnapshot(remoteUrl).catch((error) => {
    if (remoteCache?.url === remoteUrl) {
      return { snapshot: remoteCache.snapshot, degraded: true, reason: 'REMOTE_REFRESH_FAILED' }
    }
    throw error
  })
  const created = { url: remoteUrl, promise: request }
  remoteInFlight = created
  try {
    return await request
  } finally {
    if (remoteInFlight === created) remoteInFlight = null
  }
}
async function persistBundledRuntimeSnapshot(cache, snapshot) {
  await cache.set(BUNDLED_RUNTIME_SNAPSHOT_KEY, snapshot, {
    ttl: BUNDLED_RUNTIME_SNAPSHOT_TTL_SECONDS,
    tags: ['medicalchannelai-verified-snapshot'],
  })
  const readBack = await cache.get(BUNDLED_RUNTIME_SNAPSHOT_KEY)
  if (!readBack) throw new Error('RUNTIME_SNAPSHOT_READBACK_FAILED')
  return validateVerifiedSnapshot(readBack)
}
async function loadRuntimeCachedSnapshot() {
  if (!process.env.VERCEL_REGION) return null
  const cache = getCache()

  const publishedValue = await cache.get(PUBLISHED_RUNTIME_SNAPSHOT_KEY)
  const publishedSnapshot = selectPublishedRuntimeSnapshot(publishedValue)
  if (publishedSnapshot) return { snapshot: publishedSnapshot, origin: 'PUBLISHED' }

  const value = await cache.get(BUNDLED_RUNTIME_SNAPSHOT_KEY)
  if (value) {
    try {
      return { snapshot: validateVerifiedSnapshot(value), origin: 'BUNDLED' }
    } catch {
      // Invalid state is never served. Seed this exact bundled data revision below.
    }
  }

  // The Vercel-native collector's legacy "latest:v1" key is intentionally not
  // consumed here: that collector currently covers Tianjin only, while the public
  // product snapshot covers Tianjin plus verified regional markets.
  return {
    snapshot: await persistBundledRuntimeSnapshot(cache, bundledVerifiedSnapshot()),
    origin: 'BUNDLED',
  }
}
async function loadDurableSnapshotMemoized(nowMs = Date.now()) {
  if (durableMemo && nowMs - durableMemo.checkedAt < DURABLE_RECHECK_MS) {
    return { snapshot: durableMemo.snapshot, degraded: false, reason: null }
  }
  if (durableInFlight) return durableInFlight
  durableInFlight = (async () => {
    let latest
    try {
      latest = await durableSource(durableMemo?.hash ?? null)
    } catch {
      if (durableMemo?.snapshot) {
        return { snapshot: durableMemo.snapshot, degraded: true, reason: 'DURABLE_READ_FAILED' }
      }
      return { snapshot: null, degraded: true, reason: 'DURABLE_READ_FAILED' }
    }
    if (!latest?.snapshot_hash) {
      if (durableMemo?.snapshot) {
        return { snapshot: durableMemo.snapshot, degraded: true, reason: 'DURABLE_SNAPSHOT_MISSING' }
      }
      durableMemo = null
      return { snapshot: null, degraded: false, reason: null }
    }
    if (latest.payload === null || latest.payload === undefined) {
      if (durableMemo?.hash === latest.snapshot_hash) {
        durableMemo = { ...durableMemo, checkedAt: nowMs }
        return { snapshot: durableMemo.snapshot, degraded: false, reason: null }
      }
      return { snapshot: null, degraded: true, reason: 'DURABLE_SNAPSHOT_MISSING' }
    }
    const durableValue = latest.payload
    const selected = selectDurableVerifiedSnapshot(durableValue)
    const snapshot = selected ? scopedVerifiedSnapshot(selected) : null
    if (!snapshot) return { snapshot: durableMemo?.snapshot ?? null, degraded: true, reason: 'DURABLE_SNAPSHOT_INVALID' }
    durableMemo = { hash: latest.snapshot_hash, snapshot, checkedAt: Date.now() }
    return { snapshot, degraded: false, reason: null }
  })().finally(() => {
    durableInFlight = null
  })
  return durableInFlight
}

function bundledScopedSnapshot() {
  if (!bundledScopedMemo) bundledScopedMemo = scopedVerifiedSnapshot(bundledVerifiedSnapshot())
  return structuredClone(bundledScopedMemo)
}

function coverageStatus(snapshot) {
  const coverage = asObject(snapshot?.collection_coverage)
  if (!coverage || typeof coverage.complete !== 'boolean') {
    return { degraded: true, reason: 'COLLECTION_COVERAGE_UNKNOWN' }
  }
  if (coverage.complete === false) return { degraded: true, reason: 'COLLECTION_COVERAGE_PARTIAL' }
  return { degraded: false, reason: null }
}

export async function loadVerifiedSnapshotWithMetadata() {
  const remoteUrl = configuredRemoteUrl()
  if (remoteUrl) {
    const result = await loadRemoteSnapshot(remoteUrl)
    const coverage = coverageStatus(result.snapshot)
    return {
      snapshot: scopedVerifiedSnapshot(result.snapshot), sourceMode: 'REMOTE', runtimeOrigin: null,
      degraded: result.degraded || coverage.degraded, reason: result.reason || coverage.reason,
    }
  }

  const durableResult = await loadDurableSnapshotMemoized()
  if (durableResult.snapshot) {
    const coverage = coverageStatus(durableResult.snapshot)
    return {
      snapshot: structuredClone(durableResult.snapshot), sourceMode: 'DATABASE', runtimeOrigin: null,
      degraded: durableResult.degraded || coverage.degraded, reason: durableResult.reason || coverage.reason,
    }
  }

  try {
    const runtimeResult = await loadRuntimeCachedSnapshot()
    if (runtimeResult) {
      const coverage = coverageStatus(runtimeResult.snapshot)
      return {
        snapshot: scopedVerifiedSnapshot(runtimeResult.snapshot), sourceMode: 'RUNTIME_CACHE',
        runtimeOrigin: runtimeResult.origin, degraded: durableResult.degraded || coverage.degraded,
        reason: durableResult.reason || coverage.reason,
      }
    }
  } catch {
    return {
      snapshot: bundledScopedSnapshot(), sourceMode: 'BUNDLED_FALLBACK', runtimeOrigin: null,
      degraded: true, reason: durableResult.reason || 'RUNTIME_CACHE_READ_FAILED',
    }
  }
  const bundled = bundledScopedSnapshot()
  const coverage = coverageStatus(bundled)
  return {
    snapshot: bundled, sourceMode: durableResult.degraded ? 'BUNDLED_FALLBACK' : 'BUNDLED',
    runtimeOrigin: null, degraded: durableResult.degraded || coverage.degraded,
    reason: durableResult.reason || coverage.reason,
  }
}

/** Compatibility adapter for existing API callers. Prefer the request-local result. */
export async function loadVerifiedSnapshot() {
  const result = await loadVerifiedSnapshotWithMetadata()
  lastSourceMode = result.sourceMode
  lastRuntimeOrigin = result.runtimeOrigin
  return result.snapshot
}
export function verifiedSnapshotSourceMode() {
  return lastSourceMode
}
export function verifiedSnapshotRuntimeOrigin() {
  return lastRuntimeOrigin
}

function safePublicTimestamp(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null
}

function publicCollectorFailure(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const sourceId = typeof value.source_id === 'string' && SAFE_SOURCE_ID.test(value.source_id)
    ? value.source_id
    : null
  const marketCode = value.market_code === null || value.market_code === undefined
    ? null
    : typeof value.market_code === 'string' && /^[A-Z0-9-]{2,24}$/.test(value.market_code)
      ? value.market_code
      : null
  const stage = typeof value.stage === 'string' && /^[a-zA-Z0-9_-]{1,48}$/.test(value.stage)
    ? value.stage
    : null
  const category = typeof value.category === 'string' && /^[A-Z0-9_]{2,64}$/.test(value.category)
    ? value.category
    : null
  const errorCode = typeof value.error_code === 'string' && /^[A-Z0-9_]{2,80}$/.test(value.error_code)
    ? value.error_code
    : null
  if (!sourceId || !stage || !category || !errorCode) return null
  return { source_id: sourceId, market_code: marketCode, stage, category, error_code: errorCode }
}

/** Returns only bounded, non-sensitive collection status fields from the runtime state cache. */
export async function loadCollectorCollectionStatus(readState = null) {
  try {
    let state
    if (readState) state = await readState()
    else {
      if (!process.env.VERCEL_REGION) throw new Error('RUNTIME_CACHE_UNAVAILABLE')
      state = await getCache().get(COLLECTOR_RUNTIME_STATE_KEY)
    }
    if (!state || typeof state !== 'object' || Array.isArray(state) || !state.stages || typeof state.stages !== 'object') {
      throw new Error('COLLECTOR_STATE_UNAVAILABLE')
    }
    const stages = Object.values(state.stages).filter((stage) => stage && typeof stage === 'object' && !Array.isArray(stage))
    const statuses = stages.map((stage) => stage.status)
    const failedStages = stages.filter((stage) => stage.terminal === true && ['FAILED', 'BLOCKED'].includes(stage.status))
    const warningStages = stages.filter((stage) => stage.status === 'COMPLETED')
    const publish = state.stages.publish
    const outcome = statuses.length === 0
      ? 'NOT_STARTED'
      : statuses.includes('RUNNING') || statuses.some((status) => !['COMPLETED', 'FAILED', 'BLOCKED'].includes(status))
        ? 'RUNNING'
        : failedStages.some((stage) => stage.terminal === true && stage.status === 'FAILED')
          ? 'FAILED'
          : failedStages.length > 0
            ? 'BLOCKED'
            : publish?.status === 'COMPLETED' && publish?.terminal === true
              ? 'COMPLETED'
              : 'RUNNING'
    const failures = failedStages.flatMap((stage) => Array.isArray(stage.diagnostics) ? stage.diagnostics : [])
      .map(publicCollectorFailure).filter(Boolean).slice(0, 20)
    const warnings = warningStages.flatMap((stage) => Array.isArray(stage.diagnostics) ? stage.diagnostics : [])
      .map(publicCollectorFailure).filter(Boolean).slice(0, 20)
    const attempted = stages.map((stage) => safePublicTimestamp(stage.started_at)).filter(Boolean).sort()
    return {
      available: true,
      outcome,
      attempted_at: attempted.at(-1) ?? null,
      completed_at: outcome === 'COMPLETED' ? safePublicTimestamp(publish?.completed_at) : null,
      failures,
      warnings,
    }
  } catch {
    return { available: false, outcome: 'UNKNOWN', attempted_at: null, completed_at: null, failures: [], warnings: [] }
  }
}
export function setDurableSnapshotSourceForTests(source) {
  durableSource = typeof source === 'function' ? source : latestPublicVerifiedSnapshotIfChanged
  durableMemo = null
  durableInFlight = null
}
export function clearVerifiedSnapshotCacheForTests() {
  remoteCache = null
  remoteInFlight = null
  durableMemo = null
  durableInFlight = null
  lastSourceMode = 'BUNDLED'
  lastRuntimeOrigin = null
}
