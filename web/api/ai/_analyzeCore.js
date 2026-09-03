import {
  loadVerifiedSnapshot,
  verifiedSnapshotSourceMode,
} from '../_verifiedSnapshot.js'
import {
  buildDecisionMessages,
  parseDecisionContent,
} from './_decisionContract.js'

export const config = { maxDuration: 30 }

const DEFAULT_BASE_URL = 'https://apihub.agnes-ai.com/v1'
const DEFAULT_ALTERNATE_BASE_URL = 'https://apihub.agnes-ai.cn/v1'
const MODEL_ID = 'agnes-2.5-flash'
const MAX_FACT_TEXT = 1200
const MAX_ARRAY_ITEMS = 30
const RESULT_CACHE_TTL_MS = 10 * 60 * 1000
const RESULT_CACHE_MAX = 50
const RATE_WINDOW_MS = 60 * 1000
const RATE_MAX_PER_CLIENT = 10
const PROVIDER_ATTEMPT_TIMEOUT_MS = 12_000
const PROVIDER_RETRY_DELAY_MS = 250
const SHANGHAI_TIME_ZONE = 'Asia/Shanghai'
const SOURCE_CATEGORY_TITLE_CONFLICT = 'SOURCE_CATEGORY_TITLE_CONFLICT'
const RELATIVE_WINDOW_FLAG = 'RELATIVE_REGISTRATION_WINDOW_7_DAYS'

const resultCache = new Map()
const inFlight = new Map()
const rateBuckets = new Map()

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.status(status).json(payload)
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function cleanString(value, max = MAX_FACT_TEXT) {
  if (value === null || value === undefined) return null
  const text = String(value).trim()
  return text ? text.slice(0, max) : null
}

function cleanArray(value, mapper) {
  if (!Array.isArray(value)) return []
  return value.slice(0, MAX_ARRAY_ITEMS).map(mapper).filter(Boolean)
}

function headerValue(request, name) {
  const value = request.headers?.[name]
  if (Array.isArray(value)) return value[0] ?? null
  return typeof value === 'string' ? value : null
}

function sameOriginAllowed(request) {
  const origin = headerValue(request, 'origin')
  if (!origin) return false
  let originUrl
  try {
    originUrl = new URL(origin)
  } catch {
    return false
  }
  if (originUrl.protocol !== 'https:' && process.env.NODE_ENV === 'production') return false
  const hosts = [headerValue(request, 'x-forwarded-host'), headerValue(request, 'host')]
    .filter(Boolean)
    .map((value) => value.toLowerCase())
  return hosts.includes(originUrl.host.toLowerCase())
}

function clientKey(request) {
  const forwarded = headerValue(request, 'x-forwarded-for')
  const firstIp = forwarded?.split(',')[0]?.trim()
  return firstIp || headerValue(request, 'x-real-ip') || 'unknown-client'
}

function warmRateLimitExceeded(request) {
  const now = Date.now()
  const key = clientKey(request)
  const current = rateBuckets.get(key)
  if (!current || now - current.windowStartedAt >= RATE_WINDOW_MS) {
    rateBuckets.set(key, { windowStartedAt: now, count: 1 })
    return false
  }
  current.count += 1
  if (rateBuckets.size > 500) {
    for (const [bucketKey, bucket] of rateBuckets) {
      if (now - bucket.windowStartedAt >= RATE_WINDOW_MS) rateBuckets.delete(bucketKey)
    }
  }
  return current.count > RATE_MAX_PER_CLIENT
}

function fingerprint(value) {
  const text = JSON.stringify(value ?? null)
  let hash = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function snapshotCacheKey(snapshotAsOf, opportunityId, customerContext, runtimeWindowStatus) {
  return `decision-contract-v2:${snapshotAsOf || 'snapshot-unknown'}:${opportunityId}:window-${runtimeWindowStatus}:ctx-${fingerprint(customerContext)}`
}

function getWarmCachedDecision(cacheKey) {
  const entry = resultCache.get(cacheKey)
  if (!entry) return null
  if (Date.now() >= entry.expiresAt) {
    resultCache.delete(cacheKey)
    return null
  }
  return entry.decision
}

function cacheWarmDecision(cacheKey, decision) {
  if (resultCache.size >= RESULT_CACHE_MAX) {
    const oldestKey = resultCache.keys().next().value
    if (oldestKey) resultCache.delete(oldestKey)
  }
  resultCache.set(cacheKey, { expiresAt: Date.now() + RESULT_CACHE_TTL_MS, decision })
}

function normalizeSnapshotBudget(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const record = asObject(value)
  if (!record) return null
  const amount = record.amount_cny
  return typeof amount === 'number' && Number.isFinite(amount) ? amount : null
}

export function sanitizeSnapshotFacts(raw) {
  const facts = asObject(raw) ?? {}
  const contact = asObject(facts.public_contact)
  const qualityFlags = cleanArray(facts.quality_flags, (item) => cleanString(item, 120))
  const sourceCategoryConflict = qualityFlags.includes(SOURCE_CATEGORY_TITLE_CONFLICT)
  return {
    project_code: cleanString(facts.project_number, 120),
    project_name: cleanString(facts.project_name, 500),
    hospital: cleanString(facts.hospital_name, 300),
    buyer_name: cleanString(facts.buyer_name, 300),
    department: cleanString(facts.department, 200),
    region: cleanString(facts.region, 200),
    lifecycle_stage: cleanString(facts.lifecycle_state, 100),
    notice_type: cleanString(facts.notice_type, 100),
    publish_date: cleanString(facts.published_at, 80),
    registration_deadline: cleanString(facts.registration_deadline, 80),
    registration_deadline_date: cleanString(facts.registration_deadline_date, 10),
    registration_deadline_precision: cleanString(facts.registration_deadline_precision, 20),
    bid_deadline: cleanString(facts.bid_deadline, 80),
    expected_purchase_date: cleanString(facts.expected_procurement_at, 80),
    budget: normalizeSnapshotBudget(facts.budget),
    procurement_method: cleanString(facts.procurement_method, 100),
    product_categories: sourceCategoryConflict
      ? []
      : cleanArray(facts.product_categories, (item) => cleanString(item, 200)),
    products: cleanArray(facts.product_items, (item) => {
      const product = asObject(item)
      if (!product) return null
      const name = cleanString(product.raw_name ?? product.name, 300)
      if (!name) return null
      return {
        name,
        category: sourceCategoryConflict ? null : cleanString(product.category, 200),
        quantity: cleanString(product.quantity, 100),
        specification: cleanString(product.specification, 500),
      }
    }),
    quality_flags: qualityFlags,
    official_contact: contact
      ? {
          name: cleanString(contact.name, 150),
          title: cleanString(contact.title, 150),
          phone: cleanString(contact.phone, 100),
          email: cleanString(contact.email, 200),
        }
      : null,
    verification_status: cleanString(facts.verification_status, 30),
    coverage_status: cleanString(facts.coverage_status, 30),
  }
}

function sanitizeEvidenceUrls(value) {
  return cleanArray(value, (item) => {
    const text = cleanString(item, 1000)
    if (!text) return null
    try {
      const url = new URL(text)
      return url.protocol === 'https:' ? url.toString() : null
    } catch {
      return null
    }
  })
}

function sanitizeCustomerContext(raw) {
  const root = asObject(raw)
  if (!root) return null
  const target = asObject(root.target_hospital)
  const sanitizedTarget = target
    ? {
        hospital: cleanString(target.hospital, 300),
        department: cleanString(target.department, 200),
        watched_by_customer: target.watched_by_customer === true,
        updated_at: cleanString(target.updated_at, 100),
      }
    : null
  const relationship = asObject(root.hospital_relationship)
  const sanitizedRelationship = relationship
    ? {
        hospital: cleanString(relationship.hospital, 300),
        department: cleanString(relationship.department, 200),
        relationship_strength: cleanString(relationship.relationship_strength, 60),
        last_confirmed_at: cleanString(relationship.last_confirmed_at, 100),
      }
    : null
  const capabilities = cleanArray(root.matching_product_capabilities, (item) => {
    const row = asObject(item)
    if (!row) return null
    const category = cleanString(row.category, 240)
    if (!category) return null
    return {
      category,
      subcategory: cleanString(row.subcategory, 240),
      capability_type: cleanString(row.capability_type, 80),
      brands: cleanArray(row.brands, (brand) => cleanString(brand, 120)).slice(0, 10),
    }
  }).slice(0, 20)
  const policy = asObject(root.partnering_policy)
  const partneringPolicy = {
    can_find_manufacturer: typeof policy?.can_find_manufacturer === 'boolean' ? policy.can_find_manufacturer : null,
    can_partner_channel: typeof policy?.can_partner_channel === 'boolean' ? policy.can_partner_channel : null,
    can_handle_lease: typeof policy?.can_handle_lease === 'boolean' ? policy.can_handle_lease : null,
  }
  const hasTarget = Boolean(sanitizedTarget?.hospital && sanitizedTarget.watched_by_customer)
  const hasRelationship = Boolean(
    sanitizedRelationship?.hospital || sanitizedRelationship?.department || sanitizedRelationship?.relationship_strength,
  )
  const hasPolicy = Object.values(partneringPolicy).some((value) => value !== null)
  if (!hasTarget && !hasRelationship && capabilities.length === 0 && !hasPolicy) return null
  return {
    context_type: 'CUSTOMER_SELF_REPORTED_CONTEXT',
    target_hospital: hasTarget ? sanitizedTarget : null,
    hospital_relationship: hasRelationship ? sanitizedRelationship : null,
    matching_product_capabilities: capabilities,
    partnering_policy: partneringPolicy,
  }
}

function findVerifiedOpportunity(snapshot, opportunityId) {
  const pool = Array.isArray(snapshot?.opportunity_pool) ? snapshot.opportunity_pool : []
  const cards = Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const candidates = pool.length ? pool : cards
  const card = candidates.find((item) => item?.opportunity_id === opportunityId)
  const factsRecord = asObject(card?.facts)
  if (!card || !factsRecord || factsRecord.verification_status !== 'VERIFIED') return null
  const evidenceUrls = sanitizeEvidenceUrls(card.evidence_source_urls)
  const facts = sanitizeSnapshotFacts(factsRecord)
  if (!facts.project_name || evidenceUrls.length === 0) return null
  return { facts, evidenceUrls }
}

function parsedTime(value) {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

function shanghaiDateString(nowMs) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: SHANGHAI_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(nowMs))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function hasRelativeRegistrationWindow(facts) {
  return Array.isArray(facts?.quality_flags) && facts.quality_flags.includes(RELATIVE_WINDOW_FLAG)
}

function addDaysDateString(value, days) {
  const match = typeof value === 'string' ? value.match(/^(20\d{2})-(\d{2})-(\d{2})/) : null
  if (!match) return null
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  if (Number.isNaN(date.getTime())) return null
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function runtimeWindowStatus(facts, nowMs = Date.now()) {
  const registrationDeadline = parsedTime(facts.registration_deadline)
  const registrationDate = /^\d{4}-\d{2}-\d{2}$/.test(facts.registration_deadline_date || '')
    ? facts.registration_deadline_date
    : null
  const bidDeadline = parsedTime(facts.bid_deadline)
  const currentShanghaiDate = shanghaiDateString(nowMs)
  const dateOnlyRegistrationClosed = registrationDate
    ? currentShanghaiDate > registrationDate
    : false
  const exactRegistrationClosed = registrationDeadline !== null && registrationDeadline <= nowMs

  if (bidDeadline !== null && bidDeadline <= nowMs) return 'CLOSED'
  if (bidDeadline === null && (exactRegistrationClosed || dateOnlyRegistrationClosed)) return 'CLOSED'
  if (
    bidDeadline !== null &&
    bidDeadline > nowMs &&
    (exactRegistrationClosed || dateOnlyRegistrationClosed)
  ) {
    return 'LATE_WINDOW'
  }

  if (
    registrationDeadline === null &&
    registrationDate === null &&
    bidDeadline === null &&
    hasRelativeRegistrationWindow(facts)
  ) {
    const relativeEndDate = addDaysDateString(facts.publish_date, 7)
    if (!relativeEndDate) return 'CLOSED'
    return currentShanghaiDate > relativeEndDate ? 'CLOSED' : 'RELATIVE_WINDOW'
  }

  return 'OPEN'
}

function getApiKeys() {
  const raw = process.env.AGNES_API_KEYS || process.env.AGNES_API_KEY || ''
  return raw.split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean)
}

function stableIndex(text, length) {
  let hash = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return Math.abs(hash >>> 0) % length
}

function selectedKey(keys, opportunityId) {
  return keys[stableIndex(opportunityId, keys.length)]
}

function normalizeBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function isTransientHttpStatus(status) {
  return [408, 500, 502, 503, 504, 520, 522, 524].includes(Number(status))
}

function isConnectivityError(error) {
  if (error?.name === 'AbortError') return true
  if (error instanceof TypeError) return true
  const code = String(error?.cause?.code || error?.code || '').toUpperCase()
  return [
    'ENOTFOUND',
    'EAI_AGAIN',
    'ECONNRESET',
    'ECONNREFUSED',
    'ETIMEDOUT',
    'UND_ERR_CONNECT_TIMEOUT',
    'UND_ERR_HEADERS_TIMEOUT',
    'CERT_HAS_EXPIRED',
    'UNABLE_TO_VERIFY_LEAF_SIGNATURE',
  ].includes(code)
}

function retryDelay() {
  return new Promise((resolve) => setTimeout(resolve, PROVIDER_RETRY_DELAY_MS))
}

async function callProvider({ apiKey, baseUrl, facts, evidenceUrls, customerContext, windowStatus, analysisAsOf }) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), PROVIDER_ATTEMPT_TIMEOUT_MS)
  try {
    const response = await fetch(`${normalizeBaseUrl(baseUrl)}/chat/completions`, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        model: MODEL_ID,
        messages: buildDecisionMessages(facts, evidenceUrls, customerContext, windowStatus, analysisAsOf),
        temperature: 0.1,
        max_tokens: 900,
        stream: false,
      }),
    })
    if (!response.ok) {
      const error = new Error(`UPSTREAM_HTTP_${response.status}`)
      error.status = response.status
      throw error
    }
    const payload = await response.json()
    const content = payload?.choices?.[0]?.message?.content
    if (typeof content !== 'string' || !content.trim()) throw new Error('UPSTREAM_CONTENT_EMPTY')
    return parseDecisionContent(content, {
      relativeRegistrationWindow: windowStatus === 'RELATIVE_WINDOW',
    })
  } finally {
    clearTimeout(timeout)
  }
}

async function callProviderWithTransientRetry(providerArgs, keys, opportunityId) {
  const apiKey = selectedKey(keys, opportunityId)
  try {
    return await callProvider({ ...providerArgs, apiKey })
  } catch (error) {
    const status = Number(error?.status)
    if (status === 401 || status === 403 || status === 429) throw error

    let retryBaseUrl = providerArgs.baseUrl
    if (isConnectivityError(error)) {
      if (normalizeBaseUrl(providerArgs.baseUrl) === normalizeBaseUrl(DEFAULT_BASE_URL)) {
        retryBaseUrl = DEFAULT_ALTERNATE_BASE_URL
      }
    } else if (!isTransientHttpStatus(status)) {
      throw error
    }

    await retryDelay()
    return callProvider({ ...providerArgs, baseUrl: retryBaseUrl, apiKey })
  }
}

async function getOrCreateDecision(cacheKey, providerArgs, keys, opportunityId) {
  const cached = getWarmCachedDecision(cacheKey)
  if (cached) return cached
  const pending = inFlight.get(cacheKey)
  if (pending) return pending
  const promise = callProviderWithTransientRetry(providerArgs, keys, opportunityId)
    .then((decision) => {
      cacheWarmDecision(cacheKey, decision)
      return decision
    })
    .finally(() => inFlight.delete(cacheKey))
  inFlight.set(cacheKey, promise)
  return promise
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!sameOriginAllowed(request)) return sendJson(response, 403, { error: 'SAME_ORIGIN_REQUIRED' })
  if (warmRateLimitExceeded(request)) return sendJson(response, 429, { error: 'AI_RATE_LIMITED' })

  const body = asObject(request.body)
  if (!body) return sendJson(response, 400, { error: 'JSON_BODY_REQUIRED' })
  if (Object.keys(body).some((key) => !['opportunity_id', 'customer_context'].includes(key))) {
    return sendJson(response, 400, { error: 'UNEXPECTED_FIELDS' })
  }
  const opportunityId = cleanString(body.opportunity_id, 200)
  if (!opportunityId) return sendJson(response, 400, { error: 'OPPORTUNITY_ID_REQUIRED' })

  let snapshot
  try {
    snapshot = await loadVerifiedSnapshot()
  } catch {
    return sendJson(response, 503, { error: 'VERIFIED_SNAPSHOT_UNAVAILABLE' })
  }
  const grounded = findVerifiedOpportunity(snapshot, opportunityId)
  if (!grounded) return sendJson(response, 404, { error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' })

  const customerContext = sanitizeCustomerContext(body.customer_context)
  const analysisAsOf = new Date().toISOString()
  const windowStatus = runtimeWindowStatus(grounded.facts, Date.parse(analysisAsOf))
  if (windowStatus === 'CLOSED') {
    return sendJson(response, 409, { error: 'OPPORTUNITY_WINDOW_CLOSED', analysis_as_of: analysisAsOf })
  }

  const keys = getApiKeys()
  if (keys.length === 0) return sendJson(response, 503, { error: 'AI_NOT_CONFIGURED' })

  const baseUrl = (process.env.AGNES_BASE_URL || DEFAULT_BASE_URL).trim()
  const snapshotAsOf = cleanString(snapshot.snapshot_as_of, 100)
  const cacheKey = snapshotCacheKey(snapshotAsOf, opportunityId, customerContext, windowStatus)

  try {
    const decision = await getOrCreateDecision(cacheKey, {
      baseUrl,
      facts: grounded.facts,
      evidenceUrls: grounded.evidenceUrls,
      customerContext,
      windowStatus,
      analysisAsOf,
    }, keys, opportunityId)
    return sendJson(response, 200, {
      schema_version: '0.1',
      opportunity_id: opportunityId,
      snapshot_as_of: snapshotAsOf,
      snapshot_source_mode: verifiedSnapshotSourceMode(),
      generated_at: analysisAsOf,
      runtime_window_status: windowStatus,
      decision,
      decision_source: customerContext
        ? 'GROUNDED_AI_PUBLIC_FACTS_PLUS_CUSTOMER_CONTEXT'
        : 'GROUNDED_AI_PUBLIC_FACTS_ONLY',
    })
  } catch (error) {
    const status = Number(error?.status)
    if (error?.code === 'AI_RESPONSE_INVALID') return sendJson(response, 502, { error: 'AI_RESPONSE_INVALID' })
    if (status === 429) return sendJson(response, 429, { error: 'AI_RATE_LIMITED' })
    if (status === 401 || status === 403) return sendJson(response, 503, { error: 'AI_PROVIDER_AUTH_UNAVAILABLE' })
    if (status === 408 || error?.name === 'AbortError') return sendJson(response, 504, { error: 'AI_TIMEOUT' })
    return sendJson(response, 502, { error: 'AI_PROVIDER_UNAVAILABLE' })
  }
}
