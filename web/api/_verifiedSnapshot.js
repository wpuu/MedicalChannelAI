import { getCache } from '@vercel/functions'
import bundledSnapshot from '../public/data/today-actions.public.json' with { type: 'json' }
import { filterSnapshotToMedicalChannel } from './_medicalChannelScope.js'

const REMOTE_CACHE_TTL_MS = 60 * 1000
const REMOTE_TIMEOUT_MS = 6000
const MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
const MAX_TODAY_CARDS = 5
const MAX_OPPORTUNITY_POOL = 500
const BUNDLED_SNAPSHOT_REVISION = String(bundledSnapshot?.snapshot_as_of || 'unknown')
  .replace(/[^0-9A-Za-z]/g, '')
  .slice(0, 40) || 'unknown'
// Runtime cache must be scoped to the bundled VERIFIED data revision. A data-refresh
// deployment must never inherit a stale "latest" cache entry from an older bundle.
// Pure code deployments that embed the same snapshot reuse the same cache key.
const LATEST_RUNTIME_SNAPSHOT_KEY =
  `medicalchannelai:verified-snapshot:${BUNDLED_SNAPSHOT_REVISION}:v3`
const RUNTIME_SNAPSHOT_TTL_SECONDS = 7 * 24 * 60 * 60
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
let lastSourceMode = 'BUNDLED'

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
async function loadRemoteSnapshot(remoteUrl) {
  const now = Date.now()
  if (remoteCache?.url === remoteUrl && remoteCache.expiresAt > now) return remoteCache.snapshot
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
    remoteCache = { url: remoteUrl, expiresAt: now + REMOTE_CACHE_TTL_MS, snapshot }
    return snapshot
  } finally {
    clearTimeout(timeout)
  }
}
async function persistRuntimeSnapshot(cache, snapshot) {
  await cache.set(LATEST_RUNTIME_SNAPSHOT_KEY, snapshot, {
    ttl: RUNTIME_SNAPSHOT_TTL_SECONDS,
    tags: ['medicalchannelai-verified-snapshot'],
  })
  const readBack = await cache.get(LATEST_RUNTIME_SNAPSHOT_KEY)
  if (!readBack) throw new Error('RUNTIME_SNAPSHOT_READBACK_FAILED')
  return validateVerifiedSnapshot(readBack)
}
async function loadRuntimeCachedSnapshot() {
  if (!process.env.VERCEL_REGION) return null
  const cache = getCache()
  const value = await cache.get(LATEST_RUNTIME_SNAPSHOT_KEY)
  if (value) {
    try {
      return validateVerifiedSnapshot(value)
    } catch {
      // Invalid state is never served. Seed this exact bundled data revision below.
    }
  }

  // Deliberately do not migrate old "latest:v1/v2" keys. Those keys are not
  // bound to the bundled snapshot revision and can contain an older data refresh.
  return persistRuntimeSnapshot(cache, bundledVerifiedSnapshot())
}
export async function loadVerifiedSnapshot() {
  const remoteUrl = configuredRemoteUrl()
  if (remoteUrl) {
    lastSourceMode = 'REMOTE'
    return scopedVerifiedSnapshot(await loadRemoteSnapshot(remoteUrl))
  }
  try {
    const runtimeSnapshot = await loadRuntimeCachedSnapshot()
    if (runtimeSnapshot) {
      lastSourceMode = 'RUNTIME_CACHE'
      return scopedVerifiedSnapshot(runtimeSnapshot)
    }
  } catch {
    lastSourceMode = 'BUNDLED_FALLBACK'
    return scopedVerifiedSnapshot(bundledVerifiedSnapshot())
  }
  lastSourceMode = 'BUNDLED'
  return scopedVerifiedSnapshot(bundledVerifiedSnapshot())
}
export function verifiedSnapshotSourceMode() {
  return lastSourceMode
}
export function clearVerifiedSnapshotCacheForTests() {
  remoteCache = null
  lastSourceMode = 'BUNDLED'
}
