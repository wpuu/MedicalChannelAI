import bundledSnapshot from '../public/data/today-actions.public.json' with { type: 'json' }

const REMOTE_CACHE_TTL_MS = 60 * 1000
const REMOTE_TIMEOUT_MS = 6000
const MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
const MAX_TODAY_CARDS = 5
const MAX_OPPORTUNITY_POOL = 500

const FORBIDDEN_PUBLIC_KEYS = new Set([
  'model_requests',
  'model_input',
  'task_payloads',
  'agnes_dispatch_plan',
  'lease',
  'lease_id',
  'provider',
  'api_key',
  'upstream_model',
  'completion_nonce',
  'task_id',
  'private_key',
  'access_token',
  'refresh_token',
])

const FORBIDDEN_PUBLIC_PREFIXES = [
  'model_input_',
  'agnes_dispatch_',
  'provider_',
  'lease_',
  'api_key_',
  'upstream_model_',
  'private_key_',
  'access_token_',
  'refresh_token_',
]

let remoteCache = null

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
    if (
      FORBIDDEN_PUBLIC_KEYS.has(normalized) ||
      FORBIDDEN_PUBLIC_PREFIXES.some((prefix) => normalized.startsWith(prefix))
    ) {
      throw new Error(`VERIFIED_SNAPSHOT_INTERNAL_FIELD:${path}.${key}`)
    }
    assertPublicSnapshotBoundary(child, `${path}.${key}`)
  }
}

function assertHttpsUrl(value, code) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(code)
  let url
  try {
    url = new URL(value)
  } catch {
    throw new Error(code)
  }
  if (url.protocol !== 'https:') throw new Error(code)
}

function assertPublicCustomerContext(value, path) {
  const context = asObject(value)
  if (!context || context.context_type !== 'CUSTOMER_PRIVATE_FACTS') {
    throw new Error(`VERIFIED_SNAPSHOT_CUSTOMER_CONTEXT_INVALID:${path}`)
  }
  if (context.business_role !== null) {
    throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.business_role`)
  }
  if (context.hospital_relationship !== null) {
    throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.hospital_relationship`)
  }
  if (!Array.isArray(context.matching_product_capabilities) || context.matching_product_capabilities.length !== 0) {
    throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.matching_product_capabilities`)
  }
  const policy = asObject(context.partnering_policy)
  if (!policy) throw new Error(`VERIFIED_SNAPSHOT_CUSTOMER_CONTEXT_INVALID:${path}.partnering_policy`)
  for (const key of [
    'can_seek_temporary_manufacturer',
    'can_cooperate_with_channel_partner',
    'can_do_rental_projects',
  ]) {
    if (policy[key] !== null) {
      throw new Error(`VERIFIED_SNAPSHOT_PRIVATE_CONTEXT_PRESENT:${path}.partnering_policy.${key}`)
    }
  }
}

function assertPublicCard(value, path) {
  const card = asObject(value)
  if (!card || typeof card.opportunity_id !== 'string' || !card.opportunity_id.trim()) {
    throw new Error(`VERIFIED_SNAPSHOT_CARD_INVALID:${path}`)
  }
  const facts = asObject(card.facts)
  if (!facts || facts.verification_status !== 'VERIFIED') {
    throw new Error(`VERIFIED_SNAPSHOT_CARD_NOT_VERIFIED:${path}`)
  }
  if (!Array.isArray(card.evidence_source_urls) || card.evidence_source_urls.length === 0) {
    throw new Error(`VERIFIED_SNAPSHOT_EVIDENCE_INVALID:${path}`)
  }
  card.evidence_source_urls.forEach((url, index) =>
    assertHttpsUrl(url, `VERIFIED_SNAPSHOT_EVIDENCE_INVALID:${path}.evidence_source_urls[${index}]`),
  )
  assertPublicCustomerContext(card.customer_context, `${path}.customer_context`)
}

function assertUniqueOpportunityIds(items, code) {
  const seen = new Set()
  for (const item of items) {
    const id = item.opportunity_id
    if (seen.has(id)) throw new Error(code)
    seen.add(id)
  }
  return seen
}

function configuredRemoteUrl() {
  const raw = (
    process.env.VERIFIED_SNAPSHOT_URL ||
    process.env.VITE_VERIFIED_SNAPSHOT_URL ||
    ''
  ).trim()
  if (!raw) return null

  let url
  try {
    url = new URL(raw)
  } catch {
    throw new Error('VERIFIED_SNAPSHOT_URL_INVALID')
  }
  const localDevelopment =
    process.env.NODE_ENV !== 'production' &&
    (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
    (url.protocol === 'http:' || url.protocol === 'https:')
  if (url.protocol !== 'https:' && !localDevelopment) {
    throw new Error('VERIFIED_SNAPSHOT_URL_NOT_HTTPS')
  }
  return url.toString()
}

export function validateVerifiedSnapshot(value) {
  const snapshot = asObject(value)
  if (!snapshot) throw new Error('VERIFIED_SNAPSHOT_INVALID')
  assertPublicSnapshotBoundary(snapshot)
  if (snapshot.schema_version !== '0.1' || snapshot.mode !== 'TODAY_ACTIONS') {
    throw new Error('VERIFIED_SNAPSHOT_SCHEMA_INVALID')
  }
  if (
    typeof snapshot.snapshot_as_of !== 'string' ||
    Number.isNaN(Date.parse(snapshot.snapshot_as_of))
  ) {
    throw new Error('VERIFIED_SNAPSHOT_AS_OF_INVALID')
  }
  if (!Array.isArray(snapshot.cards) || snapshot.cards.length > MAX_TODAY_CARDS) {
    throw new Error('VERIFIED_SNAPSHOT_CARDS_INVALID')
  }
  if (snapshot.card_count !== snapshot.cards.length) {
    throw new Error('VERIFIED_SNAPSHOT_CARD_COUNT_MISMATCH')
  }
  snapshot.cards.forEach((card, index) => assertPublicCard(card, `$.cards[${index}]`))
  assertUniqueOpportunityIds(snapshot.cards, 'VERIFIED_SNAPSHOT_DUPLICATE_TOP5_ID')

  const pool = snapshot.opportunity_pool
  if (pool !== undefined) {
    if (!Array.isArray(pool) || pool.length > MAX_OPPORTUNITY_POOL) {
      throw new Error('VERIFIED_SNAPSHOT_POOL_INVALID')
    }
    pool.forEach((card, index) => assertPublicCard(card, `$.opportunity_pool[${index}]`))
    const poolIds = assertUniqueOpportunityIds(pool, 'VERIFIED_SNAPSHOT_DUPLICATE_POOL_ID')
    if (snapshot.opportunity_pool_count !== pool.length) {
      throw new Error('VERIFIED_SNAPSHOT_POOL_COUNT_MISMATCH')
    }
    if (snapshot.matched_count !== pool.length) {
      throw new Error('VERIFIED_SNAPSHOT_MATCHED_COUNT_MISMATCH')
    }
    if (snapshot.cards.some((item) => !poolIds.has(item.opportunity_id))) {
      throw new Error('VERIFIED_SNAPSHOT_TOP5_NOT_IN_POOL')
    }
  } else if (snapshot.matched_count !== snapshot.cards.length) {
    // One-way compatibility for the pre-pool bundled trial snapshot only.
    throw new Error('VERIFIED_SNAPSHOT_MATCHED_COUNT_MISMATCH')
  }
  return snapshot
}

export function bundledVerifiedSnapshot() {
  return validateVerifiedSnapshot(bundledSnapshot)
}

export async function loadVerifiedSnapshot() {
  const remoteUrl = configuredRemoteUrl()
  if (!remoteUrl) return bundledVerifiedSnapshot()

  const now = Date.now()
  if (remoteCache?.url === remoteUrl && remoteCache.expiresAt > now) {
    return remoteCache.snapshot
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REMOTE_TIMEOUT_MS)
  try {
    const response = await fetch(remoteUrl, {
      method: 'GET',
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!response.ok) throw new Error(`VERIFIED_SNAPSHOT_HTTP_${response.status}`)

    const declaredLength = Number(response.headers.get('content-length') || '0')
    if (declaredLength > MAX_SNAPSHOT_BYTES) {
      throw new Error('VERIFIED_SNAPSHOT_TOO_LARGE')
    }
    const text = await response.text()
    if (Buffer.byteLength(text, 'utf8') > MAX_SNAPSHOT_BYTES) {
      throw new Error('VERIFIED_SNAPSHOT_TOO_LARGE')
    }
    const snapshot = validateVerifiedSnapshot(JSON.parse(text))
    remoteCache = {
      url: remoteUrl,
      expiresAt: now + REMOTE_CACHE_TTL_MS,
      snapshot,
    }
    return snapshot
  } finally {
    clearTimeout(timeout)
  }
}

export function verifiedSnapshotSourceMode() {
  return configuredRemoteUrl() ? 'REMOTE' : 'BUNDLED'
}

export function clearVerifiedSnapshotCacheForTests() {
  remoteCache = null
}
