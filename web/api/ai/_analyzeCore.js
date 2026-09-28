import { consumeRateLimit } from '../_sharedRateLimit.js'
import {
  loadVerifiedSnapshot,
  verifiedSnapshotSourceMode,
} from '../_verifiedSnapshot.js'
import {
  getOrCreateSharedPublicAiBrief,
  getSharedPublicAiBrief,
  publicAiFactHash,
  publicIntelligenceDatabaseConfigured,
} from '../_publicIntelligenceDb.js'
import {
  PUBLIC_RULE_VERSION,
  buildRuleDecision,
} from './_decisionContract.js'
import {
  MAX_PAGE_BRIEF_ITEMS,
  PAGE_BRIEF_PROMPT_VERSION,
  PAGE_BRIEF_TYPE,
  annotateBriefItems,
  buildPageBriefMessages,
  buildRuleBrief,
  parsePageBriefContent,
} from './_pageBrief.js'

export const config = { maxDuration: 60 }

const DEFAULT_BASE_URL = 'https://apihub.agnes-ai.com/v1'
const DEFAULT_ALTERNATE_BASE_URL = 'https://apihub.agnes-ai.cn/v1'
const MODEL_ID = 'agnes-3.0-flash'
const MAX_FACT_TEXT = 1200
const MAX_ARRAY_ITEMS = 30
const MAX_BATCH_OPPORTUNITIES = 10
const PAGE_BRIEF_MAX_TOKENS = 700
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

const inFlight = new Map()

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

async function warmRateLimitExceeded(request) {
  const { limited } = await consumeRateLimit(request, {
    scope: 'ai-analyze',
    limit: RATE_MAX_PER_CLIENT,
    windowMs: RATE_WINDOW_MS,
  })
  return limited
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

async function callProvider({ apiKey, baseUrl, messages, parse, maxTokens, signal }) {
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
      messages,
      temperature: 0.1,
      max_tokens: maxTokens,
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
  return parse(content)
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

export async function callProviderWithTransientRetry(providerArgs, keys, keySeed, timing = {}) {
  const apiKey = selectedKey(keys, keySeed)
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

function aiErrorCode(error) {
  const status = Number(error?.status)
  if (error?.code === 'AI_NOT_CONFIGURED') return 'AI_NOT_CONFIGURED'
  if (error?.code === 'AI_RESPONSE_INVALID') return 'AI_RESPONSE_INVALID'
  if (status === 429) return 'AI_RATE_LIMITED'
  if (status === 401 || status === 403) return 'AI_PROVIDER_AUTH_UNAVAILABLE'
  if (error?.code === 'AI_TIMEOUT' || status === 408 || error?.name === 'AbortError') return 'AI_TIMEOUT'
  return 'AI_PROVIDER_UNAVAILABLE'
}

/**
 * Per-card next step. Deterministic rules over verified facts: instant, the
 * same for every visitor, and independent of AI keys or rate limits.
 */
function ruleDecisionItem({ snapshot, opportunityId, customerContext = null, nowMs = Date.now() }) {
  const grounded = findVerifiedOpportunity(snapshot, opportunityId)
  if (!grounded) {
    return { opportunity_id: opportunityId, status: 'ERROR', error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' }
  }
  const windowStatus = runtimeWindowStatus(grounded.facts, nowMs)
  if (windowStatus === 'CLOSED') {
    return {
      opportunity_id: opportunityId,
      status: 'NOT_ELIGIBLE',
      error: 'OPPORTUNITY_WINDOW_CLOSED',
      runtime_window_status: windowStatus,
    }
  }
  return {
    opportunity_id: opportunityId,
    status: 'READY',
    decision: buildRuleDecision(grounded.facts, grounded.evidenceUrls, customerContext, windowStatus),
    decision_source: 'PUBLIC_FACT_RULES',
    rule_version: PUBLIC_RULE_VERSION,
    runtime_window_status: windowStatus,
  }
}

// ---- Page brief -----------------------------------------------------------

export const PAGE_BRIEF_MARKETS = Object.freeze(['TJ', 'BJ', 'HE', 'LN', 'JL', 'HL'])
const PAGE_BRIEF_MARKET_SET = new Set(PAGE_BRIEF_MARKETS)

export function marketCodeForSnapshotCard(card) {
  const explicit = String(card?.facts?.market_code ?? '').trim().toUpperCase()
  if (PAGE_BRIEF_MARKET_SET.has(explicit)) return explicit
  // Same compatibility rule as the frontend: legacy Tianjin ids carry no prefix.
  const match = String(card?.opportunity_id || '').match(/^ccgp_(bj|he|ln|jl|hl)_/i)
  return match ? match[1].toUpperCase() : 'TJ'
}

export function normalizePageBriefMarkets(value) {
  if (!Array.isArray(value)) return null
  const markets = [...new Set(value.map((item) => String(item || '').trim().toUpperCase()))]
    .filter((item) => PAGE_BRIEF_MARKET_SET.has(item))
    .sort()
  return markets.length > 0 && markets.length === value.length ? markets : null
}

/** Open, verified opportunities of the given markets, best public signal first. */
export function pageBriefCandidates(snapshot, markets, nowMs = Date.now()) {
  const wanted = new Set(markets)
  const pool = Array.isArray(snapshot?.opportunity_pool) && snapshot.opportunity_pool.length
    ? snapshot.opportunity_pool
    : Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const items = []
  const seen = new Set()
  const ordered = [...pool].sort(
    (left, right) => (Number(right?.priority?.score) || 0) - (Number(left?.priority?.score) || 0),
  )
  for (const card of ordered) {
    const opportunityId = cleanString(card?.opportunity_id, 200)
    if (!opportunityId || seen.has(opportunityId)) continue
    if (!wanted.has(marketCodeForSnapshotCard(card))) continue
    const grounded = findVerifiedOpportunity(snapshot, opportunityId)
    if (!grounded) continue
    const windowStatus = runtimeWindowStatus(grounded.facts, nowMs)
    if (windowStatus === 'CLOSED') continue
    seen.add(opportunityId)
    items.push({
      opportunity_id: opportunityId,
      facts: grounded.facts,
      evidenceUrls: grounded.evidenceUrls,
      windowStatus,
    })
    if (items.length >= MAX_PAGE_BRIEF_ITEMS) break
  }
  return items
}

function pageBriefCacheKeys(items, markets, nowMs) {
  return {
    opportunityId: `page-brief:${markets.join('+')}`,
    factHash: publicAiFactHash({
      items: items.map((item) => ({
        id: item.opportunity_id,
        fact_hash: publicAiFactHash(item.facts, item.evidenceUrls),
        window: item.windowStatus,
      })),
    }, []),
    // Days-left wording changes daily, so a brief is valid for one Shanghai day.
    windowState: `day:${shanghaiDateString(nowMs)}`,
    briefType: PAGE_BRIEF_TYPE,
    promptVersion: PAGE_BRIEF_PROMPT_VERSION,
  }
}

function pageBriefResponse(brief, { markets, snapshot, items, nowMs, cache, aiError }) {
  return {
    schema_version: '0.1',
    mode: 'PAGE_BRIEF',
    markets,
    snapshot_as_of: cleanString(snapshot?.snapshot_as_of, 100),
    snapshot_source_mode: verifiedSnapshotSourceMode(),
    generated_for_date: shanghaiDateString(nowMs),
    prompt_version: PAGE_BRIEF_PROMPT_VERSION,
    opportunity_ids: items.map((item) => item.opportunity_id),
    brief,
    brief_generated_at: cache?.generated_at ?? null,
    shared_public_cache: cache
      ? { cache_hit: cache.cache_hit === true, durable: cache.durable === true }
      : null,
    ai_error: aiError ?? null,
  }
}

/**
 * One combined model call over the whole regional list. cacheOnly never calls
 * the model: it returns the shared AI brief if someone already generated it
 * today, otherwise the deterministic rule brief.
 */
export async function analyzePageBrief({ snapshot, markets, request, cacheOnly, nowMs = Date.now() }) {
  const items = annotateBriefItems(pageBriefCandidates(snapshot, markets, nowMs), nowMs)
  const context = { markets, snapshot, items, nowMs }
  if (items.length === 0) {
    return pageBriefResponse(buildRuleBrief(items), { ...context, cache: null, aiError: 'NO_OPEN_OPPORTUNITIES' })
  }
  const cacheKeys = pageBriefCacheKeys(items, markets, nowMs)
  const cached = await getSharedPublicAiBrief(cacheKeys)
  if (cached.result) return pageBriefResponse(cached.result, { ...context, cache: cached })
  if (cacheOnly) return pageBriefResponse(buildRuleBrief(items), { ...context, cache: null })

  const keys = getApiKeys()
  if (keys.length === 0) {
    return pageBriefResponse(buildRuleBrief(items), { ...context, cache: null, aiError: 'AI_NOT_CONFIGURED' })
  }
  const inFlightKey = `${cacheKeys.opportunityId}:${cacheKeys.factHash}:${cacheKeys.windowState}`
  try {
    const created = await getOrCreateSharedPublicAiBrief({
      ...cacheKeys,
      createResult: async () => {
        const pending = inFlight.get(inFlightKey)
        if (pending) return pending
        if (!request?.__mcaiInternalPrewarm && await warmRateLimitExceeded(request)) throw rateLimitError()
        const analysisAsOf = new Date(nowMs).toISOString()
        const promise = callProviderWithTransientRetry({
          baseUrl: (process.env.AGNES_BASE_URL || DEFAULT_BASE_URL).trim(),
          messages: buildPageBriefMessages(items, analysisAsOf),
          parse: (content) => parsePageBriefContent(content, items),
          maxTokens: PAGE_BRIEF_MAX_TOKENS,
        }, keys, cacheKeys.opportunityId).finally(() => inFlight.delete(inFlightKey))
        inFlight.set(inFlightKey, promise)
        return promise
      },
    })
    return pageBriefResponse(created.result, { ...context, cache: created })
  } catch (error) {
    // The page must always have a usable ordering: fall back to rules.
    return pageBriefResponse(buildRuleBrief(items), { ...context, cache: null, aiError: aiErrorCode(error) })
  }
}

export const PREWARM_MAX_GENERATE_PER_CALL = PAGE_BRIEF_MARKETS.length
export const PREWARM_MAX_CANDIDATES = PAGE_BRIEF_MARKETS.length

/**
 * Pre-generate today's shared page brief for every single business region so
 * the first visitor of the day sees the AI brief without waiting. Per-card
 * next steps are rule-based and need no prewarm. Response shape is kept for
 * the existing refresh workflow script (loops until remaining_miss_count = 0).
 */
export async function prewarmSharedPublicDecisions({ snapshot, request, limit }) {
  if (!publicIntelligenceDatabaseConfigured()) {
    const error = new Error('PREWARM_REQUIRES_DURABLE_CACHE')
    error.code = 'PREWARM_REQUIRES_DURABLE_CACHE'
    throw error
  }
  if (getApiKeys().length === 0) {
    const error = new Error('AI_NOT_CONFIGURED')
    error.code = 'AI_NOT_CONFIGURED'
    throw error
  }
  const generateLimit = Math.max(1, Math.min(PREWARM_MAX_GENERATE_PER_CALL, Number(limit) || PREWARM_MAX_GENERATE_PER_CALL))
  const internalRequest = { ...request, __mcaiInternalPrewarm: true }
  const nowMs = Date.now()
  const probes = await Promise.all(PAGE_BRIEF_MARKETS.map(async (market) => {
    const items = pageBriefCandidates(snapshot, [market], nowMs)
    if (items.length === 0) return { market, status: 'EMPTY' }
    const cached = await getSharedPublicAiBrief(pageBriefCacheKeys(items, [market], nowMs))
    return { market, status: cached.result ? 'CACHED' : 'MISS' }
  }))
  const missMarkets = probes.filter((item) => item.status === 'MISS').map((item) => item.market)
  const toGenerate = missMarkets.slice(0, generateLimit)
  const generated = await Promise.all(toGenerate.map(async (market) => {
    const result = await analyzePageBrief({ snapshot, markets: [market], request: internalRequest, cacheOnly: false, nowMs })
    return { market, ok: result.brief?.brief_source === 'AI', error: result.ai_error }
  }))
  const errors = generated.filter((item) => !item.ok).map((item) => ({ market: item.market, error: item.error || 'PAGE_BRIEF_NOT_GENERATED' }))
  return {
    schema_version: '0.2',
    mode: 'PREWARM',
    target: 'PAGE_BRIEF',
    snapshot_as_of: cleanString(snapshot?.snapshot_as_of, 100),
    prompt_version: PAGE_BRIEF_PROMPT_VERSION,
    candidate_count: PAGE_BRIEF_MARKETS.length,
    already_cached_count: probes.filter((item) => item.status === 'CACHED').length,
    not_eligible_count: probes.filter((item) => item.status === 'EMPTY').length,
    attempted_count: toGenerate.length,
    generated_count: generated.filter((item) => item.ok).length,
    error_count: errors.length,
    errors,
    remaining_miss_count: Math.max(0, missMarkets.length - toGenerate.length) + errors.length,
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
    'page_brief',
  ].includes(key))) {
    return sendJson(response, 400, { error: 'UNEXPECTED_FIELDS' })
  }
  if (body.cache_only !== undefined && typeof body.cache_only !== 'boolean') {
    return sendJson(response, 400, { error: 'CACHE_ONLY_BOOLEAN_REQUIRED' })
  }

  if (Object.prototype.hasOwnProperty.call(body, 'page_brief')) {
    if (body.customer_context || body.opportunity_id || body.opportunity_ids) {
      return sendJson(response, 400, { error: 'PAGE_BRIEF_FIELDS_EXCLUSIVE' })
    }
    const markets = normalizePageBriefMarkets(asObject(body.page_brief)?.markets)
    if (!markets) return sendJson(response, 400, { error: 'PAGE_BRIEF_MARKETS_INVALID' })
    let briefSnapshot
    try {
      briefSnapshot = await loadVerifiedSnapshot()
    } catch {
      return sendJson(response, 503, { error: 'VERIFIED_SNAPSHOT_UNAVAILABLE' })
    }
    const result = await analyzePageBrief({
      snapshot: briefSnapshot,
      markets,
      request,
      cacheOnly: body.cache_only === true,
    })
    return sendJson(response, 200, result)
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

    let batchSnapshot
    try {
      batchSnapshot = await loadVerifiedSnapshot()
    } catch {
      return sendJson(response, 503, { error: 'VERIFIED_SNAPSHOT_UNAVAILABLE' })
    }

    // cache_only is accepted for compatibility; rule decisions need no cache.
    const nowMs = Date.now()
    const items = opportunityIds.map((opportunityId) =>
      ruleDecisionItem({ snapshot: batchSnapshot, opportunityId, nowMs }),
    )
    return sendJson(response, 200, {
      schema_version: '0.2',
      mode: 'BATCH',
      cache_only: body.cache_only === true,
      decision_source: 'PUBLIC_FACT_RULES',
      rule_version: PUBLIC_RULE_VERSION,
      snapshot_as_of: cleanString(batchSnapshot.snapshot_as_of, 100),
      snapshot_source_mode: verifiedSnapshotSourceMode(),
      requested_count: opportunityIds.length,
      ready_count: items.filter((item) => item.status === 'READY').length,
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

  const clientCustomerContext = sanitizeCustomerContext(body.customer_context)
  const privateOverlayContext = sanitizeCustomerContext(request.__medicalChannelPrivateDecisionOverlay)
  const ruleCustomerContext = privateOverlayContext ? null : clientCustomerContext
  const analysisAsOf = new Date().toISOString()
  const item = ruleDecisionItem({
    snapshot,
    opportunityId,
    customerContext: ruleCustomerContext,
    nowMs: Date.parse(analysisAsOf),
  })
  if (item.status === 'ERROR') return sendJson(response, 404, { error: item.error })
  if (item.status === 'NOT_ELIGIBLE') {
    return sendJson(response, 409, { error: 'OPPORTUNITY_WINDOW_CLOSED', analysis_as_of: analysisAsOf })
  }
  const decision = applyPrivateDecisionOverlay(item.decision, privateOverlayContext)
  return sendJson(response, 200, {
    schema_version: '0.2',
    opportunity_id: opportunityId,
    snapshot_as_of: cleanString(snapshot.snapshot_as_of, 100),
    snapshot_source_mode: verifiedSnapshotSourceMode(),
    generated_at: analysisAsOf,
    runtime_window_status: item.runtime_window_status,
    decision,
    decision_source: privateOverlayContext
      ? 'PUBLIC_FACT_RULES_PLUS_PRIVATE_RULE_OVERLAY'
      : ruleCustomerContext
        ? 'PUBLIC_FACT_RULES_PLUS_CUSTOMER_CONTEXT'
        : 'PUBLIC_FACT_RULES',
    rule_version: PUBLIC_RULE_VERSION,
  })
}
