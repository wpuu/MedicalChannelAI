import coreHandler, { config } from './_analyzeCore.js'
import { authenticatedUser } from '../_auth.js'
import { privateDatabaseConfigured } from '../_privateDb.js'
import { minimalPrivateContextForOpportunity } from '../_privateProfileContext.js'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

export { config }

const PUBLIC_FIRST_PARTY_ORIGIN = 'https://medicalai.qd.je'
const MAX_VERIFIED_SNAPSHOT_AGE_MS = 30 * 60 * 60 * 1000
const MAX_VERIFIED_SNAPSHOT_FUTURE_SKEW_MS = 10 * 60 * 1000
const RELATIVE_WINDOW_FLAG = 'RELATIVE_REGISTRATION_WINDOW_7_DAYS'

function firstHeaderValue(value) {
  if (Array.isArray(value)) return value[0] ?? null
  return typeof value === 'string' ? value : null
}

function firstQuery(request, key) {
  const value = request.query?.[key]
  return Array.isArray(value) ? value[0] ?? null : value
}

function routeName(request) {
  const value = firstQuery(request, 'route')
  return typeof value === 'string' ? value.trim() : ''
}

function privatePilotEnabled() {
  return ['1', 'true', 'yes', 'on'].includes(
    String(process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED || '').trim().toLowerCase(),
  )
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.setHeader('Referrer-Policy', 'no-referrer')
  response.status(status).json(payload)
}

function pilotSameOriginAllowed(request) {
  const origin = firstHeaderValue(request.headers?.origin)
  if (!origin) return false
  let originUrl
  try {
    originUrl = new URL(origin)
  } catch {
    return false
  }
  if (originUrl.protocol !== 'https:' && process.env.NODE_ENV === 'production') return false
  const hosts = [
    firstHeaderValue(request.headers?.['x-forwarded-host']),
    firstHeaderValue(request.headers?.host),
  ]
    .filter(Boolean)
    .map((value) => value.toLowerCase())
  return hosts.includes(originUrl.host.toLowerCase())
}

function verifiedSnapshotAutomationError(snapshot, now = Date.now()) {
  const raw = typeof snapshot?.snapshot_as_of === 'string'
    ? snapshot.snapshot_as_of.trim()
    : ''
  const parsed = raw ? Date.parse(raw) : Number.NaN
  if (!raw || Number.isNaN(parsed)) return 'VERIFIED_SNAPSHOT_NOT_FRESH'
  const age = now - parsed
  if (age > MAX_VERIFIED_SNAPSHOT_AGE_MS || age < -MAX_VERIFIED_SNAPSHOT_FUTURE_SKEW_MS) {
    return 'VERIFIED_SNAPSHOT_NOT_FRESH'
  }
  return null
}

function rawVerifiedCard(snapshot, opportunityId) {
  const pool = Array.isArray(snapshot?.opportunity_pool) ? snapshot.opportunity_pool : []
  const cards = Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const candidates = pool.length ? pool : cards
  const card = candidates.find((item) => item?.opportunity_id === opportunityId)
  const facts = asObject(card?.facts)
  return card && facts?.verification_status === 'VERIFIED' ? card : null
}

function rawVerifiedFacts(snapshot, opportunityId) {
  return asObject(rawVerifiedCard(snapshot, opportunityId)?.facts)
}

function normalizeProxyOrigin(request) {
  const origin = firstHeaderValue(request.headers?.origin)
  if (origin !== PUBLIC_FIRST_PARTY_ORIGIN) return request
  return {
    ...request,
    method: request.method,
    body: request.body,
    headers: {
      ...request.headers,
      host: 'medicalai.qd.je',
      'x-forwarded-host': 'medicalai.qd.je',
    },
  }
}

function cleanText(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function publicContactName(facts) {
  const contact = facts?.public_contact ?? facts?.official_contact ?? null
  if (typeof contact === 'string') return cleanText(contact)
  if (!contact || typeof contact !== 'object' || Array.isArray(contact)) return null
  return cleanText(contact.name) || cleanText(contact.contact_name)
}

function splitContactNames(value) {
  if (!value) return []
  return value
    .split(/[、，,；;／/]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function outreachGreeting(facts) {
  const names = splitContactNames(publicContactName(facts))
  if (names.length !== 1) return '您好：'
  const name = names[0]
  const addressedName = /(老师|主任|院长|教授|医生|医师|经理|先生|女士)$/.test(name)
    ? name
    : `${name}老师`
  return `${addressedName}，您好：`
}

function dateTimeText(value) {
  if (!value || typeof value !== 'string') return null
  const match = value.match(/^(20\d{2})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (!match) return value
  return `${match[1]}年${Number(match[2])}月${Number(match[3])}日 ${match[4]}:${match[5]}`
}

function dateOnlyText(value) {
  if (!value || typeof value !== 'string') return null
  const match = value.match(/^(20\d{2})-(\d{2})-(\d{2})$/)
  if (!match) return value
  return `${match[1]}年${Number(match[2])}月${Number(match[3])}日`
}

function parsedTime(value) {
  if (!value || typeof value !== 'string') return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

function chinaDateKey(now = Date.now()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(now))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function hasRelativeRegistrationWindow(facts) {
  return Array.isArray(facts?.quality_flags) && facts.quality_flags.includes(RELATIVE_WINDOW_FLAG)
}

function addDaysDateKey(value, days) {
  const match = typeof value === 'string' ? value.match(/^(20\d{2})-(\d{2})-(\d{2})/) : null
  if (!match) return null
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  if (Number.isNaN(date.getTime())) return null
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function outreachWindow(facts, now = Date.now()) {
  const bid = parsedTime(facts?.bid_deadline)
  const registration = parsedTime(facts?.registration_deadline)
  const registrationDate = typeof facts?.registration_deadline_date === 'string'
    ? facts.registration_deadline_date
    : null
  const currentDate = chinaDateKey(now)
  const registrationDateClosed = Boolean(
    registrationDate && /^\d{4}-\d{2}-\d{2}$/.test(registrationDate) && registrationDate < currentDate,
  )
  if (bid !== null && bid <= now) return { open: false, late: false }
  if (bid === null && ((registration !== null && registration <= now) || registrationDateClosed)) {
    return { open: false, late: false }
  }
  const late = Boolean(
    bid !== null && bid > now &&
    ((registration !== null && registration <= now) || registrationDateClosed),
  )
  if (late) return { open: true, late: true }

  if (
    bid === null &&
    registration === null &&
    !registrationDate &&
    hasRelativeRegistrationWindow(facts)
  ) {
    const relativeEndDate = addDaysDateKey(facts?.published_at, 7)
    if (!relativeEndDate) return { open: false, late: false, relative: true }
    return { open: currentDate <= relativeEndDate, late: false, relative: true }
  }

  return { open: true, late: false }
}

function normalizeBudget(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/,/g, '').trim())
    return Number.isFinite(parsed) ? parsed : null
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const key of ['amount', 'amount_cny', 'budget_cny', 'value']) {
      const parsed = normalizeBudget(value[key])
      if (parsed !== null) return parsed
    }
  }
  return null
}

function budgetFactText(value) {
  const budget = normalizeBudget(value)
  if (budget === null || budget <= 0) return null
  if (budget < 10_000) return `项目预算约${Math.round(budget)}元`
  const wan = budget / 10_000
  const decimals = wan < 10 ? 2 : wan < 100 ? 1 : 0
  return `项目预算约${Number(wan.toFixed(decimals))}万元`
}

function isMarketResearch(facts) {
  const text = `${facts?.lifecycle_state ?? facts?.lifecycle_stage ?? ''}|${facts?.notice_type ?? ''}|${facts?.project_name ?? ''}`
  return /MARKET_RESEARCH|调研|需求调查|需求征集|意向征集/.test(text)
}

function capabilitySentence(context) {
  const capability = Array.isArray(context?.matching_product_capabilities)
    ? context.matching_product_capabilities[0]
    : null
  const category = cleanText(capability?.category)
  const type = capability?.capability_type
  if (!category || !type) return null

  if (type === 'DIRECT_AUTHORIZED') {
    return `我们目前有${category}相关产品/方案资源，可按公开要求进一步准备资质和技术资料。`
  }
  if (type === 'DIRECT' || type === 'DIRECT_UNCONFIRMED') {
    return `我们正在确认${category}相关供货条件，如项目仍有公开对接窗口，可先按要求准备技术资料。`
  }
  if (type === 'RENTAL_CAPABLE') {
    return `我们可评估${category}相关租赁/服务方案，并按公开要求准备资料。`
  }
  if (type === 'SERVICE_ONLY') {
    return `我们可提供${category}相关服务支持，并按公开要求准备资料。`
  }
  if (type === 'PARTNER' || type === 'CAN_SOURCE_PARTNER' || type === 'NEED_MANUFACTURER') {
    return `我们正在组织${category}相关合作资源，如项目仍有公开对接窗口，可进一步核对执行条件。`
  }
  return null
}

export function buildGroundedOutreachDraft(card, privateContext, now = Date.now()) {
  const facts = asObject(card?.facts) || {}
  const marketResearch = isMarketResearch(facts)
  const window = outreachWindow(facts, now)
  const project = cleanText(facts.project_name) || '相关项目'
  const registration = dateTimeText(facts.registration_deadline)
  const registrationDate = dateOnlyText(facts.registration_deadline_date)
  const bid = dateTimeText(facts.bid_deadline)
  const relativeWindowFact = window.relative
    ? '官方公告写明测试企业报名期为“自公告发布之日起7天”，未公布精确截止时刻'
    : null
  const factLines = [
    budgetFactText(facts.budget),
    relativeWindowFact,
    registration
      ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截至${registration}`
      : registrationDate
        ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截止日期为${registrationDate}（官方未公布具体时间）`
        : null,
    bid ? `投标/响应截止${bid}` : null,
  ].filter(Boolean)

  const closing = window.relative
    ? '想确认目前测试企业报名是否仍开放；如仍开放，我们可以按公开要求准备产品资料和技术说明。'
    : window.late
      ? '注意到前期报名或文件获取时间已过，想确认后续是否还有公开答疑或公告允许的资料对接窗口；如无，我们将按公告安排关注后续进展。'
      : marketResearch
        ? '想确认目前是否仍接受产品资料、技术交流或需求反馈；如方便，我们可以按公开要求准备相关资料。'
        : '想确认目前是否还有公开答疑或公告允许的资料对接窗口；如方便，我们可以按项目要求准备相关资料。'
  const capability = capabilitySentence(privateContext?.context)

  return [
    outreachGreeting(facts),
    '',
    `关注到「${project}」的公开${marketResearch ? '调研' : '采购'}信息。`,
    factLines.length ? `公开信息显示，${factLines.join('，')}。` : '目前可核验的公开信息有限。',
    capability,
    '',
    closing,
  ].filter((line) => line !== null).join('\n')
}

function outreachResponse(card, privateContext) {
  const facts = asObject(card?.facts)
  const evidence = Array.isArray(card?.evidence_source_urls)
    ? card.evidence_source_urls.filter((value) => typeof value === 'string' && /^https:\/\//i.test(value))
    : []
  if (!facts || evidence.length === 0) return { status: 409, error: 'OUTREACH_GROUNDING_INSUFFICIENT' }
  const window = outreachWindow(facts)
  if (!window.open) return { status: 409, error: 'OPPORTUNITY_WINDOW_CLOSED' }
  return {
    status: 200,
    payload: {
      opportunity_id: card.opportunity_id,
      generated_at: new Date().toISOString(),
      draft: buildGroundedOutreachDraft(card, privateContext),
      disclaimer: [
        '发送前请核对公开信息与实际情况；院内关系仅用于内部判断，不会写入外发话术，也不会推断厂家授权或中标概率。',
        window.relative ? '公告若仅给相对报名窗口，系统不会把内部推算日期作为官方截止日期。' : null,
      ].filter(Boolean).join(''),
    },
  }
}

/**
 * medicalai.qd.je is reverse-proxied through Caddy to Vercel. The browser keeps
 * Origin=https://medicalai.qd.je while the upstream Host becomes a Vercel
 * hostname, so the core same-origin guard would otherwise reject our own UI.
 * Only the exact public first-party Origin is normalized; every other origin
 * continues through the strict core validation unchanged.
 *
 * Private Pilot adds a second boundary: the browser may submit only the
 * opportunity id. Customer-private context is resolved from the authenticated
 * user session and reduced to facts relevant to that opportunity before the
 * grounded AI core sees it. The same authenticated wrapper also serves a
 * deterministic, evidence-grounded outreach draft through route=outreach so the
 * Pilot does not need another Serverless Function.
 */
export default async function handler(request, response) {
  const normalizedRequest = normalizeProxyOrigin(request)
  if (!privatePilotEnabled()) return coreHandler(normalizedRequest, response)
  if (request.method !== 'POST') return coreHandler(normalizedRequest, response)
  if (!pilotSameOriginAllowed(normalizedRequest)) {
    return sendJson(response, 403, { error: 'SAME_ORIGIN_REQUIRED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }

  const body = asObject(request.body)
  if (!body) return coreHandler(normalizedRequest, response)
  if (Object.prototype.hasOwnProperty.call(body, 'customer_context')) {
    return sendJson(response, 400, { error: 'PILOT_CUSTOMER_CONTEXT_SERVER_ONLY' })
  }

  let user
  try {
    user = await authenticatedUser(normalizedRequest)
  } catch (error) {
    console.error('pilot AI session lookup failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 503, { error: 'PRIVATE_PROFILE_UNAVAILABLE' })
  }
  if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })

  const opportunityId = typeof body.opportunity_id === 'string'
    ? body.opportunity_id.trim().slice(0, 200)
    : ''
  if (!opportunityId) return coreHandler(normalizedRequest, response)

  try {
    const snapshot = await loadVerifiedSnapshot()
    const snapshotError = verifiedSnapshotAutomationError(snapshot)
    if (snapshotError) return sendJson(response, 409, { error: snapshotError })

    const card = rawVerifiedCard(snapshot, opportunityId)
    const facts = asObject(card?.facts) || rawVerifiedFacts(snapshot, opportunityId)

    if (routeName(request) === 'outreach') {
      if (!card || !facts) return sendJson(response, 404, { error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' })
      const privateContext = await minimalPrivateContextForOpportunity(user, facts)
      const result = outreachResponse(card, privateContext)
      if (result.status !== 200) return sendJson(response, result.status, { error: result.error })
      return sendJson(response, 200, result.payload)
    }

    if (!facts) return coreHandler(normalizedRequest, response)
    const privateContext = await minimalPrivateContextForOpportunity(user, facts)
    const serverBody = {
      opportunity_id: opportunityId,
      ...(privateContext.has_context ? { customer_context: privateContext.context } : {}),
    }
    return coreHandler({ ...normalizedRequest, body: serverBody }, response)
  } catch (error) {
    console.error('pilot private AI context resolution failed', {
      opportunity_id: opportunityId,
      route: routeName(request) || 'analyze',
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 503, { error: 'PRIVATE_PROFILE_UNAVAILABLE' })
  }
}
