import coreHandler, { config } from './_analyzeCore.js'
import { authenticatedUser } from '../_auth.js'
import { privateDatabaseConfigured } from '../_privateDb.js'
import { minimalPrivateContextForOpportunity } from '../_privateProfileContext.js'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

export { config }

const PUBLIC_FIRST_PARTY_ORIGIN = 'https://medicalai.qd.je'

function firstHeaderValue(value) {
  if (Array.isArray(value)) return value[0] ?? null
  return typeof value === 'string' ? value : null
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

function rawVerifiedFacts(snapshot, opportunityId) {
  const pool = Array.isArray(snapshot?.opportunity_pool) ? snapshot.opportunity_pool : []
  const cards = Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const candidates = pool.length ? pool : cards
  const card = candidates.find((item) => item?.opportunity_id === opportunityId)
  const facts = asObject(card?.facts)
  return card && facts?.verification_status === 'VERIFIED' ? facts : null
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
 * grounded AI core sees it. Public/demo mode keeps the older local-context
 * contract because there is no server-side user profile in that mode.
 */
export default async function handler(request, response) {
  const normalizedRequest = normalizeProxyOrigin(request)
  if (!privatePilotEnabled()) return coreHandler(normalizedRequest, response)
  if (request.method !== 'POST') return coreHandler(normalizedRequest, response)
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
    const facts = rawVerifiedFacts(snapshot, opportunityId)
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
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 503, { error: 'PRIVATE_PROFILE_UNAVAILABLE' })
  }
}
