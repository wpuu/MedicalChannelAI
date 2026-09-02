import { randomUUID } from 'node:crypto'
import { authenticatedUser, readJsonBody, sendJson } from '../_auth.js'
import { privateDatabaseConfigured, privateDb } from '../_privateDb.js'
import { findVerifiedSnapshotCard } from '../_pilotOpportunity.js'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

const FOLLOWUP_STATUSES = new Set([
  'NEW',
  'REVIEWING',
  'CONTACTED',
  'RELATIONSHIP_VERIFIED',
  'PREPARING',
  'BID_SUBMITTED',
  'WON',
  'LOST',
  'NOT_FIT',
  'MONITOR',
  'ARCHIVED',
])
const NOT_FIT_REASONS = new Set([
  'NO_PRODUCT_CAPABILITY',
  'NO_MANUFACTURER_ACCESS',
  'RELATIONSHIP_TOO_WEAK',
  'AMOUNT_TOO_SMALL',
  'PROJECT_TOO_LATE',
  'COMPETITOR_LOCKED_CUSTOMER_JUDGMENT',
  'DEPARTMENT_OUT_OF_SCOPE',
  'REGION_OUT_OF_SCOPE',
  'RENTAL_NOT_SUPPORTED',
  'OTHER',
])

function routeId(request) {
  const raw = Array.isArray(request.query?.id) ? request.query.id[0] : request.query?.id
  const value = typeof raw === 'string' ? raw.trim() : ''
  return value && value.length <= 200 ? value : null
}

function normalizeBudget(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const number = Number(value.replace(/,/g, '').trim())
    return Number.isFinite(number) ? number : null
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const key of ['amount', 'amount_cny', 'budget_cny', 'value']) {
      const number = normalizeBudget(value[key])
      if (number !== null) return number
    }
  }
  return null
}

function publicSnapshotForFollowup(card) {
  const facts = card.facts || {}
  return {
    facts: {
      project_number: facts.project_number ?? null,
      project_name: facts.project_name ?? null,
      buyer_name: facts.buyer_name ?? null,
      hospital_name: facts.hospital_name ?? null,
      department: facts.department ?? null,
      lifecycle_state: facts.lifecycle_state ?? null,
      published_at: facts.published_at ?? null,
      bid_deadline: facts.bid_deadline ?? null,
      expected_procurement_at: facts.expected_procurement_at ?? null,
      budget_cny: normalizeBudget(facts.budget),
    },
    evidence_source_urls: Array.isArray(card.evidence_source_urls)
      ? card.evidence_source_urls.filter((value) => typeof value === 'string').slice(0, 50)
      : [],
  }
}

function cleanOptionalText(value, maxLength) {
  if (value === undefined || value === null) return null
  if (typeof value !== 'string') return undefined
  const text = value.trim()
  return text ? text.slice(0, maxLength) : null
}

function parseReminder(value) {
  if (value === undefined || value === null || value === '') return null
  if (typeof value !== 'string' || value.length > 64) return undefined
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? undefined : new Date(timestamp).toISOString()
}

function validateMutation(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null
  const status = typeof body.status === 'string' ? body.status : ''
  if (!FOLLOWUP_STATUSES.has(status)) return null
  const mutationId = typeof body.mutation_id === 'string' ? body.mutation_id.trim() : ''
  if (!/^followup:[0-9a-fA-F-]{36}$/.test(mutationId)) return null
  const note = cleanOptionalText(body.note, 2000)
  if (note === undefined) return null
  const remindAt = parseReminder(body.remind_at)
  if (remindAt === undefined) return null
  const reason = cleanOptionalText(body.reason, 100)
  if (reason === undefined) return null
  if (status === 'NOT_FIT' && (!reason || !NOT_FIT_REASONS.has(reason))) return null
  if (status !== 'NOT_FIT' && reason) return null
  return {
    status,
    mutation_id: mutationId,
    note,
    reason: status === 'NOT_FIT' ? reason : null,
    remind_at: remindAt,
    reminder_supplied: Object.prototype.hasOwnProperty.call(body, 'remind_at'),
  }
}

async function followupState(sql, user, opportunityId, mutationInserted) {
  const rows = await sql`
    SELECT id, status, remind_at
    FROM private_followups
    WHERE user_id = ${user.id}
      AND organization_id = ${user.organization_id}
      AND opportunity_id = ${opportunityId}
    LIMIT 1
  `
  const followup = rows[0] || null
  if (!followup) {
    return {
      schema_version: '0.1',
      opportunity_id: opportunityId,
      current_status: 'NEW',
      remind_at: null,
      history: [],
      profile_learning: null,
      ...(mutationInserted === undefined ? {} : { mutation_inserted: mutationInserted }),
    }
  }

  const history = await sql`
    SELECT id, status, note, reason, remind_at, created_at
    FROM private_followup_events
    WHERE followup_id = ${followup.id} AND user_id = ${user.id}
    ORDER BY created_at DESC, id DESC
    LIMIT 200
  `
  return {
    schema_version: '0.1',
    opportunity_id: opportunityId,
    current_status: followup.status,
    remind_at: followup.remind_at ? new Date(followup.remind_at).toISOString() : null,
    history: history.map((row) => ({
      id: row.id,
      status: row.status,
      note: row.note,
      reason: row.reason,
      remind_at: row.remind_at ? new Date(row.remind_at).toISOString() : null,
      at: new Date(row.created_at).toISOString(),
      actor: '当前用户',
    })),
    profile_learning: null,
    ...(mutationInserted === undefined ? {} : { mutation_inserted: mutationInserted }),
  }
}

export default async function handler(request, response) {
  if (!['GET', 'POST'].includes(request.method)) {
    response.setHeader('Allow', 'GET, POST')
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
      return sendJson(response, 200, await followupState(sql, user, opportunityId))
    }

    const mutation = validateMutation(readJsonBody(request))
    if (!mutation) return sendJson(response, 400, { error: 'FOLLOWUP_MUTATION_INVALID' })

    const snapshot = await loadVerifiedSnapshot()
    const card = findVerifiedSnapshotCard(snapshot, opportunityId)
    if (!card) return sendJson(response, 404, { error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' })
    const publicSnapshot = publicSnapshotForFollowup(card)
    let mutationInserted = false

    await sql.begin(async (tx) => {
      const existingMutation = await tx`
        SELECT id FROM private_followup_events
        WHERE user_id = ${user.id} AND mutation_id = ${mutation.mutation_id}
        LIMIT 1
      `
      if (existingMutation.length) return

      const followupId = randomUUID()
      await tx`
        INSERT INTO private_followups (
          id, organization_id, user_id, opportunity_id, status, public_snapshot
        ) VALUES (
          ${followupId}, ${user.organization_id}, ${user.id}, ${opportunityId}, 'NEW', ${tx.json(publicSnapshot)}
        )
        ON CONFLICT (user_id, opportunity_id) DO UPDATE SET
          public_snapshot = EXCLUDED.public_snapshot
      `
      const followupRows = await tx`
        SELECT id, remind_at FROM private_followups
        WHERE user_id = ${user.id} AND opportunity_id = ${opportunityId}
        FOR UPDATE
      `
      const followup = followupRows[0]
      if (!followup) throw new Error('FOLLOWUP_UPSERT_FAILED')

      let nextReminder = followup.remind_at ? new Date(followup.remind_at).toISOString() : null
      if (mutation.reminder_supplied) {
        nextReminder = mutation.remind_at
      } else if (mutation.status !== 'MONITOR') {
        nextReminder = null
      }

      const inserted = await tx`
        INSERT INTO private_followup_events (
          id, followup_id, user_id, mutation_id, status, note, reason, remind_at
        ) VALUES (
          ${randomUUID()}, ${followup.id}, ${user.id}, ${mutation.mutation_id},
          ${mutation.status}, ${mutation.note}, ${mutation.reason}, ${mutation.remind_at}
        )
        ON CONFLICT (user_id, mutation_id) WHERE mutation_id IS NOT NULL DO NOTHING
        RETURNING id
      `
      if (!inserted.length) return

      await tx`
        UPDATE private_followups
        SET status = ${mutation.status}, remind_at = ${nextReminder},
            public_snapshot = ${tx.json(publicSnapshot)}, updated_at = now()
        WHERE id = ${followup.id} AND user_id = ${user.id}
      `
      mutationInserted = true
    })

    return sendJson(
      response,
      200,
      await followupState(sql, user, opportunityId, mutationInserted),
    )
  } catch (error) {
    console.error('private followup request failed', {
      opportunity_id: opportunityId,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'FOLLOWUP_REQUEST_FAILED' })
  }
}
