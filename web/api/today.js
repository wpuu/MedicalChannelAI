import { authenticatedUser, sendJson } from './_auth.js'
import { privateDatabaseConfigured } from './_privateDb.js'
import { personalizedOpportunityPoolForUser } from './_pilotOpportunity.js'
import { loadVerifiedSnapshot } from './_verifiedSnapshot.js'

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }

  try {
    const user = await authenticatedUser(request)
    if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })

    const snapshot = await loadVerifiedSnapshot()
    const pool = await personalizedOpportunityPoolForUser(user, snapshot)
    const cards = pool.slice(0, 5)
    return sendJson(response, 200, {
      schema_version: '0.1',
      mode: 'TODAY_ACTIONS',
      snapshot_as_of: snapshot.snapshot_as_of,
      input_candidate_count: Number(snapshot.input_candidate_count || pool.length),
      matched_count: pool.length,
      card_count: cards.length,
      opportunity_pool_count: pool.length,
      model_request_count: 0,
      coverage_warning: 'PARTIAL_OR_SOURCE_SPECIFIC_COVERAGE_MAY_APPLY',
      cards,
      opportunity_pool: pool,
    })
  } catch (error) {
    console.error('pilot today request failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 503, { error: 'TODAY_DATA_UNAVAILABLE' })
  }
}
