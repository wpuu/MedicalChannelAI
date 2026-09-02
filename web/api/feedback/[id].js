import { authenticatedUser, readJsonBody, sendJson } from '../_auth.js'
import { privateDatabaseConfigured, privateDb } from '../_privateDb.js'
import { findVerifiedSnapshotCard } from '../_pilotOpportunity.js'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

const FEEDBACK_VALUES = new Set([
  'ALREADY_KNOWN',
  'NEW_NOT_VALUABLE',
  'NEW_WORTH_FOLLOWING',
])

function routeId(request) {
  const raw = Array.isArray(request.query?.id) ? request.query.id[0] : request.query?.id
  const value = typeof raw === 'string' ? raw.trim() : ''
  return value && value.length <= 200 ? value : null
}

async function currentFeedback(sql, userId, opportunityId) {
  const rows = await sql`
    SELECT value, updated_at
    FROM private_recommendation_feedback
    WHERE user_id = ${userId} AND opportunity_id = ${opportunityId}
    LIMIT 1
  `
  const row = rows[0] || null
  return {
    schema_version: '0.1',
    opportunity_id: opportunityId,
    value: row?.value ?? null,
    updated_at: row?.updated_at ? new Date(row.updated_at).toISOString() : null,
  }
}

export default async function handler(request, response) {
  if (!['GET', 'PUT', 'DELETE'].includes(request.method)) {
    response.setHeader('Allow', 'GET, PUT, DELETE')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }
  const opportunityId = routeId(request)
  if (!opportunityId) return sendJson(response, 400, { error: 'OPPORTUNITY_ID_INVALID' })

  try {
    const user = await authenticatedUser(request)
    if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    const sql = privateDb()

    if (request.method === 'GET') {
      return sendJson(response, 200, await currentFeedback(sql, user.id, opportunityId))
    }

    if (request.method === 'DELETE') {
      await sql`
        DELETE FROM private_recommendation_feedback
        WHERE user_id = ${user.id} AND opportunity_id = ${opportunityId}
      `
      return sendJson(response, 200, {
        schema_version: '0.1',
        opportunity_id: opportunityId,
        value: null,
        updated_at: null,
      })
    }

    const body = readJsonBody(request)
    const value = typeof body?.value === 'string' ? body.value : ''
    if (!FEEDBACK_VALUES.has(value)) {
      return sendJson(response, 400, { error: 'FEEDBACK_VALUE_INVALID' })
    }
    const snapshot = await loadVerifiedSnapshot()
    if (!findVerifiedSnapshotCard(snapshot, opportunityId)) {
      return sendJson(response, 404, { error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' })
    }

    await sql`
      INSERT INTO private_recommendation_feedback (
        user_id, opportunity_id, value, created_at, updated_at
      ) VALUES (
        ${user.id}, ${opportunityId}, ${value}, now(), now()
      )
      ON CONFLICT (user_id, opportunity_id) DO UPDATE SET
        value = EXCLUDED.value,
        updated_at = now()
    `
    return sendJson(response, 200, await currentFeedback(sql, user.id, opportunityId))
  } catch (error) {
    console.error('private recommendation feedback failed', {
      opportunity_id: opportunityId,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'FEEDBACK_REQUEST_FAILED' })
  }
}
