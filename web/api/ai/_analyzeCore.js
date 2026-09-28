import {
  loadVerifiedSnapshot,
  verifiedSnapshotSourceMode,
} from '../_verifiedSnapshot.js'
import {
  getOrCreateSharedPublicAiBrief,
  getSharedPublicAiBrief,
  publicAiFactHash,
} from '../_publicIntelligenceDb.js'
import {
  buildDecisionMessages,
  parseDecisionContent,
} from './_decisionContract.js'

export const config = { maxDuration: 60 }

const DEFAULT_BASE_URL = 'https://apihub.agnes-ai.com/v1'
const DEFAULT_ALTERNATE_BASE_URL = 'https://apihub.agnes-ai.cn/v1'
const MODEL_ID = 'agnes-3.0-flash'
const PUBLIC_AI_PROMPT_VERSION = 'decision-action-selector-v3-public-v1'
const MAX_FACT_TEXT = 1200
const MAX_ARRAY_ITEMS = 30
const MAX_BATCH_OPPORTUNITIES = 10
const RESULT_CACHE_TTL_MS = 10 * 60 * 1000
const RESULT_CACHE_MAX = 50
const RATE_WINDOW_MS = 60 * 1000
const RATE_MAX_PER_CLIENT = 10
// Provider latency has a long tail: most answers arrive in 2-6s, a few take
// 10-20s. A hard 12s abort followed by a from-scratch retry (the previous
// design) turned those slow answers into AI_TIMEOUT and forced users to click
// several times. Instead we keep the first attempt alive, start one hedged
// attempt in parallel if it is still silent after PROVIDER_HEDGE_AFTER_MS, take
// whichever valid answer arrives first, and give the whole operation a single
// budget that stays well inside the function maxDuration so a finished answer
// can always be written to the shared cache.
export const PROVIDER_HEDGE_AFTER_MS = 8_000
export const PROVIDER_TOTAL_BUDGET_MS = 42_000
const PROVIDER_MAX_ATTEMPTS = 2
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

function rateLimitError() {
  const error = new Error('AI_RATE_LIMITED')
  error.status = 429
  return error
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
  return `decision-action-selector-v3:${snapshotAsOf || 'snapshot-unknown'}:${opportunityId}:window-${runtimeWindowStatus}:ctx-${fingerprint(customerContext)}`
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

function endOfShanghaiDayMs(dateKey) {
  return /^\d{4}-\d{2}-\d{2}$/.test(dateKey || '')
    ? Date.parse(`${dateKey}T23:59:59+08:00`)
    : null
}

function nextActionDeadlineMs(facts, windowStatus, nowMs) {
  if (windowStatus === 'LATE_WINDOW') return parsedTime(facts.bid_deadline)
  if (windowStatus === 'RELATIVE_WINDOW') {
    const relativeEnd = addDaysDateString(facts.publish_date, 7)
    return relativeEnd ? endOfShanghaiDayMs(relativeEnd) : null
  }
  const registration = parsedTime(facts.registration_deadline)
  if (registration !== null && registration > nowMs) return registration
  const registrationDate = /^\d{4}-\d{2}-\d{2}$/.test(facts.registration_deadline_date || '')
    ? endOfShanghaiDayMs(facts.registration_deadline_date)
    : null
  if (registrationDate !== null && registrationDate > nowMs) return registrationDate
  const bid = parsedTime(facts.bid_deadline)
  return bid !== null && bid > nowMs ? bid : null
}

function urgencyBucket(deadlineMs, nowMs) {
  if (deadlineMs === null) return 'NO_DEADLINE'
  const hours = Math.max(0, (deadlineMs - nowMs) / (60 * 60 * 1000))
  if (hours <= 24) return 'H24'
  if (hours <= 72) return 'H72'
  if (hours <= 7 * 24) return 'D7'
  if (hours <= 14 * 24) return 'D14'
  if (hours <= 30 * 24) return 'D30'
  return 'GT30D'
}

export function publicWindowCacheState(facts, windowStatus, nowMs = Date.now()) {
  return `${windowStatus}:${urgencyBucket(nextActionDeadlineMs(facts, windowStatus, nowMs), nowMs)}`
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
  // A slow model answer is not a routing problem. Our own abort (hedge loser or
  // total budget) must never switch the retry to the alternate region.
  if (error?.name === 'AbortError' || error?.code === 'AI_TIMEOUT') return false
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

async function callProvider({ apiKey, baseUrl, facts, evidenceUrls, customerContext, windowStatus, analysisAsOf, signal }) {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}/chat/completions`, {
    method: 'POST',
    signal,
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
    facts,
    evidenceUrls,
    customerContext,
    windowStatus,
  })
}

function providerTimeoutError() {
  const error = new Error('AI_TIMEOUT')
  error.code = 'AI_TIMEOUT'
  error.status = 408
  return error
}

function isFatalProviderError(error) {
  const status = Number(error?.status)
  return status === 401 || status === 403 || status === 429 || error?.code === 'AI_NOT_CONFIGURED'
}

/**
 * Decide the route for the single follow-up attempt after a failed attempt.
 * Returns null when the failure is not worth retrying.
 */
function retryBaseUrlFor(error, baseUrl) {
  if (isFatalProviderError(error)) return null
  if (isConnectivityError(error)) {
    return normalizeBaseUrl(baseUrl) === normalizeBaseUrl(DEFAULT_BASE_URL)
      ? DEFAULT_ALTERNATE_BASE_URL
      : baseUrl
  }
  // Model output occasionally fails the strict grounding contract; one fresh
  // sample usually passes. Transient upstream HTTP errors retry on the same route.
  if (error?.code === 'AI_RESPONSE_INVALID') return baseUrl
  if (isTransientHttpStatus(error?.status)) return baseUrl
  if (error?.message === 'UPSTREAM_CONTENT_EMPTY') return baseUrl
  return null
}

export async function callProviderWithTransientRetry(providerArgs, keys, opportunityId, timing = {}) {
  const apiKey = selectedKey(keys, opportunityId)
  const hedgeAfterMs = timing.hedgeAfterMs ?? PROVIDER_HEDGE_AFTER_MS
  const totalBudgetMs = timing.totalBudgetMs ?? PROVIDER_TOTAL_BUDGET_MS

  return new Promise((resolve, reject) => {
    const controllers = []
    let settled = false
    let running = 0
    let launched = 0
    let retryScheduled = false
    let lastError = null
    let hedgeTimer = null
    let retryTimer = null

    const finish = (callback, value) => {
      if (settled) return
      settled = true
      clearTimeout(hedgeTimer)
      clearTimeout(retryTimer)
      clearTimeout(budgetTimer)
      for (const controller of controllers) controller.abort()
      callback(value)
    }

    const budgetTimer = setTimeout(() => finish(reject, providerTimeoutError()), totalBudgetMs)

    const launch = (baseUrl) => {
      if (settled || launched >= PROVIDER_MAX_ATTEMPTS) return
      launched += 1
      running += 1
      const controller = new AbortController()
      controllers.push(controller)
      callProvider({ ...providerArgs, baseUrl, apiKey, signal: controller.signal }).then(
        (decision) => finish(resolve, decision),
        (error) => {
          running -= 1
          if (settled) return
          lastError = error
          if (isFatalProviderError(error)) return finish(reject, error)
          const retryBaseUrl = launched < PROVIDER_MAX_ATTEMPTS ? retryBaseUrlFor(error, baseUrl) : null
          if (retryBaseUrl) {
            clearTimeout(hedgeTimer)
            retryScheduled = true
            retryTimer = setTimeout(() => {
              retryScheduled = false
              launch(retryBaseUrl)
            }, PROVIDER_RETRY_DELAY_MS)
            return
          }
          if (running === 0 && !retryScheduled) finish(reject, lastError)
        },
      )
    }

    launch(providerArgs.baseUrl)
    // Hedge: the first attempt is still silent, so start a parallel attempt on
    // the same route. The first valid answer wins and the other is aborted.
    hedgeTimer = setTimeout(() => launch(providerArgs.baseUrl), hedgeAfterMs)
  })
}

async function getOrCreateWarmDecision(cacheKey, providerArgs, keys, opportunityId, request) {
  const cached = getWarmCachedDecision(cacheKey)
  if (cached) return cached
  const pending = inFlight.get(cacheKey)
  if (pending) return pending
  if (warmRateLimitExceeded(request)) throw rateLimitError()
  const promise = callProviderWithTransientRetry(providerArgs, keys, opportunityId)
    .then((decision) => {
      cacheWarmDecision(cacheKey, decision)
      return decision
    })
    .finally(() => inFlight.delete(cacheKey))
  inFlight.set(cacheKey, promise)
  return promise
}

async function getOrCreateDecision({
  cacheKey,
  providerArgs,
  keys,
  opportunityId,
  request,
  sharedPublic,
}) {
  let createPromise = null
  const createResult = () => {
    if (keys.length === 0) {
      const error = new Error('AI_NOT_CONFIGURED')
      error.code = 'AI_NOT_CONFIGURED'
      throw error
    }
    if (!createPromise) {
      createPromise = getOrCreateWarmDecision(cacheKey, providerArgs, keys, opportunityId, request)
    }
    return createPromise
  }
  if (!sharedPublic) {
    return {
      decision: await createResult(),
      cache: { cache_hit: false, durable: false, generated_at: providerArgs.analysisAsOf },
    }
  }
  const cached = await getOrCreateSharedPublicAiBrief({
    opportunityId,
    factHash: sharedPublic.factHash,
    windowState: sharedPublic.windowState,
    briefType: 'PUBLIC_ACTION_DECISION',
    promptVersion: PUBLIC_AI_PROMPT_VERSION,
    createResult,
  })
  return { decision: cached.result, cache: cached }
}


function batchErrorCode(error) {
  const status = Number(error?.status)
  if (error?.code === 'AI_NOT_CONFIGURED') return 'AI_NOT_CONFIGURED'
  if (error?.code === 'AI_RESPONSE_INVALID') return 'AI_RESPONSE_INVALID'
  if (status === 429) return 'AI_RATE_LIMITED'
  if (status === 401 || status === 403) return 'AI_PROVIDER_AUTH_UNAVAILABLE'
  if (error?.code === 'AI_TIMEOUT' || status === 408 || error?.name === 'AbortError') return 'AI_TIMEOUT'
  return 'AI_PROVIDER_UNAVAILABLE'
}

async function analyzeSharedPublicBatchItem({
  snapshot,
  opportunityId,
  request,
  cacheOnly,
}) {
  const grounded = findVerifiedOpportunity(snapshot, opportunityId)
  if (!grounded) {
    return { opportunity_id: opportunityId, status: 'ERROR', error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' }
  }

  const analysisAsOf = new Date().toISOString()
  const nowMs = Date.parse(analysisAsOf)
  const windowStatus = runtimeWindowStatus(grounded.facts, nowMs)
  if (windowStatus === 'CLOSED') {
    return {
      opportunity_id: opportunityId,
      status: 'NOT_ELIGIBLE',
      error: 'OPPORTUNITY_WINDOW_CLOSED',
      runtime_window_status: windowStatus,
    }
  }

  const snapshotAsOf = cleanString(snapshot.snapshot_as_of, 100)
  const windowCacheState = publicWindowCacheState(grounded.facts, windowStatus, nowMs)
  const factHash = publicAiFactHash(grounded.facts, grounded.evidenceUrls)

  if (cacheOnly) {
    const cached = await getSharedPublicAiBrief({
      opportunityId,
      factHash,
      windowState: windowCacheState,
      briefType: 'PUBLIC_ACTION_DECISION',
      promptVersion: PUBLIC_AI_PROMPT_VERSION,
    })
    if (!cached.result) {
      return {
        opportunity_id: opportunityId,
        status: 'MISS',
        runtime_window_status: windowStatus,
        public_cache_window_state: windowCacheState,
      }
    }
    return {
      opportunity_id: opportunityId,
      status: 'READY',
      decision: cached.result,
      decision_generated_at: cached.generated_at,
      runtime_window_status: windowStatus,
      public_cache_window_state: windowCacheState,
      shared_public_cache: {
        cache_hit: true,
        durable: cached.durable === true,
        prompt_version: PUBLIC_AI_PROMPT_VERSION,
      },
    }
  }

  try {
    const keys = getApiKeys()
    const baseUrl = (process.env.AGNES_BASE_URL || DEFAULT_BASE_URL).trim()
    const cacheKey = `shared-public:${PUBLIC_AI_PROMPT_VERSION}:${opportunityId}:${factHash}:${windowCacheState}`
    const result = await getOrCreateDecision({
      cacheKey,
      providerArgs: {
        baseUrl,
        facts: grounded.facts,
        evidenceUrls: grounded.evidenceUrls,
        customerContext: null,
        windowStatus,
        analysisAsOf,
      },
      keys,
      opportunityId,
      request,
      sharedPublic: { factHash, windowState: windowCacheState },
    })
    return {
      opportunity_id: opportunityId,
      status: 'READY',
      decision: result.decision,
      decision_generated_at: result.cache.generated_at,
      runtime_window_status: windowStatus,
      public_cache_window_state: windowCacheState,
      shared_public_cache: {
        cache_hit: result.cache.cache_hit === true,
        durable: result.cache.durable === true,
        prompt_version: PUBLIC_AI_PROMPT_VERSION,
      },
    }
  } catch (error) {
    return {
      opportunity_id: opportunityId,
      status: 'ERROR',
      error: batchErrorCode(error),
      runtime_window_status: windowStatus,
      public_cache_window_state: windowCacheState,
    }
  }
}

function relationshipStrengthLabel(value) {
  if (value === 'STRONG') return '较强'
  if (value === 'MEDIUM') return '中等'
  if (value === 'HISTORICAL') return '历史'
  if (value === 'WEAK') return '较弱'
  return '已确认'
}

function capabilityTypeLabel(value) {
  if (value === 'DIRECT_AUTHORIZED') return '已确认直接授权/供货能力'
  if (value === 'RENTAL_CAPABLE') return '可执行租赁项目'
  if (value === 'SERVICE_ONLY') return '可提供相关服务'
  if (value === 'PARTNER' || value === 'CAN_SOURCE_PARTNER') return '可组织合作渠道'
  if (value === 'NEED_MANUFACTURER') return '仍需匹配厂家'
  if (value === 'DIRECT' || value === 'DIRECT_UNCONFIRMED') return '直接供货条件仍需确认'
  return '已录入相关执行能力'
}

function appendUnique(items, values, max = 5) {
  const result = [...items]
  for (const value of values) {
    if (!value || result.includes(value)) continue
    result.push(value)
    if (result.length >= max) break
  }
  return result
}

export function applyPrivateDecisionOverlay(decision, customerContext) {
  if (!customerContext) return decision
  const reasons = []
  const risks = []
  const target = customerContext.target_hospital
  if (target?.hospital && target.watched_by_customer) {
    reasons.push(`当前账号已将${target.hospital}${target.department ? `${target.department}` : ''}列为重点关注对象；这只表示经营目标，不代表已有院内关系。`)
  }
  const relationship = customerContext.hospital_relationship
  if (relationship?.hospital) {
    reasons.push(`当前账号已确认与${relationship.hospital}${relationship.department ? `${relationship.department}` : ''}存在${relationshipStrengthLabel(relationship.relationship_strength)}关系，可优先通过已确认关系核实真实需求和执行窗口。`)
  }
  const capability = customerContext.matching_product_capabilities?.[0]
  if (capability?.category) {
    reasons.push(`当前账号在${capability.subcategory || capability.category}方向的执行条件为“${capabilityTypeLabel(capability.capability_type)}”，可据此决定是否继续投入。`)
    if (['NEED_MANUFACTURER', 'DIRECT', 'DIRECT_UNCONFIRMED'].includes(capability.capability_type)) {
      risks.push('当前账号的厂家、授权或最终供货条件仍需在投入投标或正式承诺前确认。')
    }
  }
  return {
    ...decision,
    reasons: appendUnique(decision.reasons || [], reasons),
    risks: appendUnique(decision.risks || [], risks),
    requires_human_confirmation: true,
  }
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!sameOriginAllowed(request)) return sendJson(response, 403, { error: 'SAME_ORIGIN_REQUIRED' })

  const body = asObject(request.body)
  if (!body) return sendJson(response, 400, { error: 'JSON_BODY_REQUIRED' })
  if (Object.keys(body).some((key) => ![
    'opportunity_id',
    'opportunity_ids',
    'customer_context',
    'cache_only',
  ].includes(key))) {
    return sendJson(response, 400, { error: 'UNEXPECTED_FIELDS' })
  }

  const batchRequested = Object.prototype.hasOwnProperty.call(body, 'opportunity_ids')
  if (batchRequested) {
    if (body.customer_context) {
      return sendJson(response, 400, { error: 'BATCH_CUSTOMER_CONTEXT_UNSUPPORTED' })
    }
    if (!Array.isArray(body.opportunity_ids)) {
      return sendJson(response, 400, { error: 'OPPORTUNITY_IDS_ARRAY_REQUIRED' })
    }
    const opportunityIds = [...new Set(
      body.opportunity_ids
        .map((value) => cleanString(value, 200))
        .filter(Boolean),
    )]
    if (opportunityIds.length === 0) {
      return sendJson(response, 400, { error: 'OPPORTUNITY_IDS_REQUIRED' })
    }
    if (opportunityIds.length > MAX_BATCH_OPPORTUNITIES) {
      return sendJson(response, 400, {
        error: 'OPPORTUNITY_BATCH_TOO_LARGE',
        max_batch_size: MAX_BATCH_OPPORTUNITIES,
      })
    }
    if (body.cache_only !== undefined && typeof body.cache_only !== 'boolean') {
      return sendJson(response, 400, { error: 'CACHE_ONLY_BOOLEAN_REQUIRED' })
    }

    let batchSnapshot
    try {
      batchSnapshot = await loadVerifiedSnapshot()
    } catch {
      return sendJson(response, 503, { error: 'VERIFIED_SNAPSHOT_UNAVAILABLE' })
    }

    const cacheOnly = body.cache_only === true
    const items = await Promise.all(
      opportunityIds.map((opportunityId) =>
        analyzeSharedPublicBatchItem({
          snapshot: batchSnapshot,
          opportunityId,
          request,
          cacheOnly,
        }),
      ),
    )
    return sendJson(response, 200, {
      schema_version: '0.1',
      mode: 'BATCH',
      cache_only: cacheOnly,
      snapshot_as_of: cleanString(batchSnapshot.snapshot_as_of, 100),
      snapshot_source_mode: verifiedSnapshotSourceMode(),
      requested_count: opportunityIds.length,
      ready_count: items.filter((item) => item.status === 'READY').length,
      cache_hit_count: items.filter((item) => item.shared_public_cache?.cache_hit === true).length,
      miss_count: items.filter((item) => item.status === 'MISS').length,
      error_count: items.filter((item) => item.status === 'ERROR').length,
      items,
    })
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

  const clientCustomerContext = sanitizeCustomerContext(body.customer_context)
  const privateOverlayContext = sanitizeCustomerContext(request.__medicalChannelPrivateDecisionOverlay)
  const modelCustomerContext = privateOverlayContext ? null : clientCustomerContext
  const analysisAsOf = new Date().toISOString()
  const nowMs = Date.parse(analysisAsOf)
  const windowStatus = runtimeWindowStatus(grounded.facts, nowMs)
  if (windowStatus === 'CLOSED') {
    return sendJson(response, 409, { error: 'OPPORTUNITY_WINDOW_CLOSED', analysis_as_of: analysisAsOf })
  }

  const keys = getApiKeys()

  const baseUrl = (process.env.AGNES_BASE_URL || DEFAULT_BASE_URL).trim()
  const snapshotAsOf = cleanString(snapshot.snapshot_as_of, 100)
  const windowCacheState = publicWindowCacheState(grounded.facts, windowStatus, nowMs)
  const factHash = publicAiFactHash(grounded.facts, grounded.evidenceUrls)
  const cacheKey = modelCustomerContext
    ? snapshotCacheKey(snapshotAsOf, opportunityId, modelCustomerContext, windowCacheState)
    : `shared-public:${PUBLIC_AI_PROMPT_VERSION}:${opportunityId}:${factHash}:${windowCacheState}`

  try {
    const result = await getOrCreateDecision({
      cacheKey,
      providerArgs: {
        baseUrl,
        facts: grounded.facts,
        evidenceUrls: grounded.evidenceUrls,
        customerContext: modelCustomerContext,
        windowStatus,
        analysisAsOf,
      },
      keys,
      opportunityId,
      request,
      sharedPublic: modelCustomerContext
        ? null
        : { factHash, windowState: windowCacheState },
    })
    const decision = applyPrivateDecisionOverlay(result.decision, privateOverlayContext)
    return sendJson(response, 200, {
      schema_version: '0.1',
      opportunity_id: opportunityId,
      snapshot_as_of: snapshotAsOf,
      snapshot_source_mode: verifiedSnapshotSourceMode(),
      generated_at: analysisAsOf,
      decision_generated_at: result.cache.generated_at,
      runtime_window_status: windowStatus,
      public_cache_window_state: windowCacheState,
      decision,
      decision_source: privateOverlayContext
        ? 'SHARED_PUBLIC_AI_PLUS_PRIVATE_RULE_OVERLAY'
        : modelCustomerContext
          ? 'GROUNDED_AI_PUBLIC_FACTS_PLUS_CUSTOMER_CONTEXT'
          : 'SHARED_GROUNDED_AI_PUBLIC_FACTS_ONLY',
      shared_public_cache: modelCustomerContext
        ? null
        : {
            cache_hit: result.cache.cache_hit === true,
            durable: result.cache.durable === true,
            prompt_version: PUBLIC_AI_PROMPT_VERSION,
          },
    })
  } catch (error) {
    const status = Number(error?.status)
    if (error?.code === 'AI_NOT_CONFIGURED') return sendJson(response, 503, { error: 'AI_NOT_CONFIGURED' })
    if (error?.code === 'AI_RESPONSE_INVALID') return sendJson(response, 502, { error: 'AI_RESPONSE_INVALID' })
    if (status === 429) return sendJson(response, 429, { error: 'AI_RATE_LIMITED' })
    if (status === 401 || status === 403) return sendJson(response, 503, { error: 'AI_PROVIDER_AUTH_UNAVAILABLE' })
    if (error?.code === 'AI_TIMEOUT' || status === 408 || error?.name === 'AbortError') return sendJson(response, 504, { error: 'AI_TIMEOUT' })
    return sendJson(response, 502, { error: 'AI_PROVIDER_UNAVAILABLE' })
  }
}
