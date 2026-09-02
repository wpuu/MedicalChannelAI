import { authenticatedUser, sendJson } from '../_auth.js'
import { privateDatabaseConfigured } from '../_privateDb.js'
import { personalizedOpportunityPoolForUser } from '../_pilotOpportunity.js'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

function opportunityId(request) {
  const raw = Array.isArray(request.query?.id) ? request.query.id[0] : request.query?.id
  const value = typeof raw === 'string' ? raw.trim() : ''
  return value && value.length <= 200 ? value : null
}

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }
  const id = opportunityId(request)
  if (!id) return sendJson(response, 400, { error: 'OPPORTUNITY_ID_INVALID' })

  try {
    const user = await authenticatedUser(request)
    if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    const snapshot = await loadVerifiedSnapshot()
    const pool = await personalizedOpportunityPoolForUser(user, snapshot)
    const card = pool.find((item) => item.opportunity_id === id)
    if (!card) return sendJson(response, 404, { error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' })
    return sendJson(response, 200, card)
  } catch (error) {
    console.error('pilot opportunity request failed', {
      opportunity_id: id,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 503, { error: 'OPPORTUNITY_DATA_UNAVAILABLE' })
  }
}
