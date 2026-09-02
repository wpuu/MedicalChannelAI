import { createHash, randomUUID } from 'node:crypto'
import { authenticatedUser, readJsonBody, sendJson } from './_auth.js'
import { privateDatabaseConfigured, privateDb } from './_privateDb.js'
import {
  findVerifiedSnapshotCard,
  personalizedOpportunityPoolForUser,
} from './_pilotOpportunity.js'
import { loadVerifiedSnapshot } from './_verifiedSnapshot.js'

const FOLLOWUP_STATUSES = new Set([
  'NEW', 'REVIEWING', 'CONTACTED', 'RELATIONSHIP_VERIFIED', 'PREPARING',
  'BID_SUBMITTED', 'WON', 'LOST', 'NOT_FIT', 'MONITOR', 'ARCHIVED',
])
const DONE_FOR_TODAY = new Set([
  'CONTACTED', 'NOT_FIT', 'BID_SUBMITTED', 'WON', 'LOST', 'ARCHIVED',
])
const NOT_FIT_REASONS = new Set([
  'NO_PRODUCT_CAPABILITY', 'NO_MANUFACTURER_ACCESS', 'RELATIONSHIP_TOO_WEAK',
  'AMOUNT_TOO_SMALL', 'PROJECT_TOO_LATE', 'COMPETITOR_LOCKED_CUSTOMER_JUDGMENT',
  'DEPARTMENT_OUT_OF_SCOPE', 'REGION_OUT_OF_SCOPE', 'RENTAL_NOT_SUPPORTED', 'OTHER',
])
const FEEDBACK_VALUES = new Set([
  'ALREADY_KNOWN', 'NEW_NOT_VALUABLE', 'NEW_WORTH_FOLLOWING',
])

function firstQuery(request, key) {
  const raw = request.query?.[key]
  return Array.isArray(raw) ? raw[0] : raw
}

function routeName(request) {
  const value = firstQuery(request, 'route')
  return typeof value === 'string' ? value.trim() : ''
}

function opportunityId(request) {
  const raw = firstQuery(request, 'id')
  const value = typeof raw === 'string' ? raw.trim() : ''
  return value && value.length <= 200 ? value : null
}

function reminderId(request) {
  const raw = firstQuery(request, 'id')
  const value = typeof raw === 'string' ? raw.trim() : ''
  return /^mrem_[0-9a-f]{64}$/.test(value) ? value : null
}

function allow(request, response, methods) {
  if (methods.includes(request.method)) return true
  response.setHeader('Allow', methods.join(', '))
  sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  return false
}

function shouldAppearToday(followup) {
  if (!followup) return true
  if (DONE_FOR_TODAY.has(followup.status)) return false
  if (followup.status !== 'MONITOR' || !followup.remind_at) return true
  const remindAt = new Date(followup.remind_at).getTime()
  return Number.isNaN(remindAt) || remindAt <= Date.now()
}

async function todayFollowupMap(sql, user) {
  const rows = await sql`
    SELECT opportunity_id, status, remind_at
    FROM private_followups
    WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
    LIMIT 500
  `
  return new Map(rows.map((row) => [row.opportunity_id, row]))
}

async function todayFeedbackMap(sql, user) {
  const rows = await sql`
    SELECT opportunity_id, value
    FROM private_recommendation_feedback
    WHERE user_id = ${user.id}
    LIMIT 500
  `
  return new Map(rows.map((row) => [row.opportunity_id, row.value]))
}

function hasActiveFollowup(followup) {
  return Boolean(followup?.status && followup.status !== 'NEW')
}

function feedbackAttentionTier(followup, feedback) {
  if (hasActiveFollowup(followup)) return 0
  if (feedback === 'NEW_NOT_VALUABLE') return 2
  if (feedback === 'ALREADY_KNOWN') return 1
  return 0
}

function applyTodayAttention(pool, followups, feedback) {
  return pool
    .filter((card) => shouldAppearToday(followups.get(card.opportunity_id)))
    .map((card, index) => ({
      card,
      index,
      tier: feedbackAttentionTier(
        followups.get(card.opportunity_id),
        feedback.get(card.opportunity_id),
      ),
    }))
    .filter((item) => item.tier < 2)
    .sort((left, right) => left.tier - right.tier || left.index - right.index)
    .map((item) => item.card)
}

async function todayRoute(request, response, user) {
  if (!allow(request, response, ['GET'])) return
  try {
    const snapshot = await loadVerifiedSnapshot()
    const pool = await personalizedOpportunityPoolForUser(user, snapshot)
    const sql = privateDb()
    const [followups, feedback] = await Promise.all([
      todayFollowupMap(sql, user),
      todayFeedbackMap(sql, user),
    ])
    const todayPool = applyTodayAttention(pool, followups, feedback)
    const cards = todayPool.slice(0, 5)
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
    console.error('pilot today request failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 503, { error: 'TODAY_DATA_UNAVAILABLE' })
  }
}

async function opportunityRoute(request, response, user) {
  if (!allow(request, response, ['GET'])) return
  const id = opportunityId(request)
  if (!id) return sendJson(response, 400, { error: 'OPPORTUNITY_ID_INVALID' })
  try {
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

function snapshotText(value, maxLength = 1000) {
  if (typeof value !== 'string') return null
  const text = value.trim().replace(/\s+/g, ' ')
  return text ? text.slice(0, maxLength) : null
}

function snapshotStringArray(value, maxItems = 50, maxLength = 300) {
  if (!Array.isArray(value)) return []
  const result = []
  for (const item of value) {
    const text = snapshotText(item, maxLength)
    if (!text) continue
    result.push(text)
    if (result.length >= maxItems) break
  }
  return result
}

function snapshotProducts(value) {
  if (!Array.isArray(value)) return []
  const result = []
  for (const item of value) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    const name = snapshotText(item.raw_name ?? item.product_name ?? item.name ?? item.item_name, 500)
    if (!name) continue
    result.push({
      name,
      category: snapshotText(item.category ?? item.product_category, 300),
      quantity: snapshotText(item.quantity ?? item.qty, 160),
      specification: snapshotText(item.specification ?? item.spec ?? item.model, 1000),
    })
    if (result.length >= 50) break
  }
  return result
}

function snapshotContact(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const contact = {
    name: snapshotText(value.name ?? value.contact_name, 300),
    title: snapshotText(value.title ?? value.role, 300),
    phone: snapshotText(value.phone ?? value.telephone ?? value.mobile, 200),
    email: snapshotText(value.email, 320),
  }
  return Object.values(contact).some(Boolean) ? contact : null
}

function publicSnapshotForFollowup(card) {
  const facts = card.facts || {}
  return {
    facts: {
      project_number: snapshotText(facts.project_number, 300),
      project_name: snapshotText(facts.project_name, 1000),
      buyer_name: snapshotText(facts.buyer_name, 500),
      hospital_name: snapshotText(facts.hospital_name, 500),
      department: snapshotText(facts.department, 300),
      region: snapshotText(facts.region, 300),
      lifecycle_state: snapshotText(facts.lifecycle_state, 160),
      notice_type: snapshotText(facts.notice_type, 300),
      published_at: snapshotText(facts.published_at, 80),
      registration_deadline: snapshotText(facts.registration_deadline, 80),
      registration_deadline_date: snapshotText(facts.registration_deadline_date, 40),
      bid_deadline: snapshotText(facts.bid_deadline, 80),
      expected_procurement_at: snapshotText(facts.expected_procurement_at, 80),
      budget_cny: normalizeBudget(facts.budget),
      procurement_method: snapshotText(facts.procurement_method, 300),
      product_categories: snapshotStringArray(facts.product_categories),
      product_items: snapshotProducts(facts.product_items),
      public_contact: snapshotContact(facts.public_contact),
      verification_status: snapshotText(facts.verification_status, 40),
      coverage_status: snapshotText(facts.coverage_status, 40),
    },
    evidence_source_urls: Array.isArray(card.evidence_source_urls)
      ? card.evidence_source_urls.filter((value) => typeof value === 'string' && /^https:\/\//i.test(value)).slice(0, 50)
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

async function followupState(sql, user, id, mutationInserted) {
  const rows = await sql`
    SELECT id, status, remind_at
    FROM private_followups
    WHERE user_id = ${user.id}
      AND organization_id = ${user.organization_id}
      AND opportunity_id = ${id}
    LIMIT 1
  `
  const followup = rows[0] || null
  if (!followup) {
    return {
      schema_version: '0.1',
      opportunity_id: id,
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
    opportunity_id: id,
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

async function existingFollowupSnapshot(sql, user, id) {
  const rows = await sql`
    SELECT public_snapshot
    FROM private_followups
    WHERE user_id = ${user.id}
      AND organization_id = ${user.organization_id}
      AND opportunity_id = ${id}
    LIMIT 1
  `
  return rows[0]?.public_snapshot ?? null
}

async function followupRoute(request, response, user) {
  if (!allow(request, response, ['GET', 'POST'])) return
  const id = opportunityId(request)
  if (!id) return sendJson(response, 400, { error: 'OPPORTUNITY_ID_INVALID' })
  const sql = privateDb()
  try {
    if (request.method === 'GET') {
      return sendJson(response, 200, await followupState(sql, user, id))
    }

    const mutation = validateMutation(readJsonBody(request))
    if (!mutation) return sendJson(response, 400, { error: 'FOLLOWUP_MUTATION_INVALID' })

    let card = null
    let snapshotUnavailable = false
    try {
      const snapshot = await loadVerifiedSnapshot()
      card = findVerifiedSnapshotCard(snapshot, id)
    } catch (error) {
      snapshotUnavailable = true
      console.warn('verified snapshot unavailable during private followup mutation', {
        opportunity_id: id,
        error: error instanceof Error ? error.message : 'UNKNOWN',
      })
    }

    const storedSnapshot = card ? null : await existingFollowupSnapshot(sql, user, id)
    if (!card && !storedSnapshot) {
      return sendJson(
        response,
        snapshotUnavailable ? 503 : 404,
        { error: snapshotUnavailable ? 'VERIFIED_SNAPSHOT_UNAVAILABLE' : 'VERIFIED_OPPORTUNITY_NOT_FOUND' },
      )
    }
    const publicSnapshot = card ? publicSnapshotForFollowup(card) : storedSnapshot
    let mutationInserted = false

    await sql.begin(async (tx) => {
      const existingMutation = await tx`
        SELECT id FROM private_followup_events
        WHERE user_id = ${user.id} AND mutation_id = ${mutation.mutation_id}
        LIMIT 1
      `
      if (existingMutation.length) return

      const newFollowupId = randomUUID()
      await tx`
        INSERT INTO private_followups (
          id, organization_id, user_id, opportunity_id, status, public_snapshot
        ) VALUES (
          ${newFollowupId}, ${user.organization_id}, ${user.id}, ${id}, 'NEW', ${tx.json(publicSnapshot)}
        )
        ON CONFLICT (user_id, opportunity_id) DO UPDATE SET
          public_snapshot = EXCLUDED.public_snapshot
      `
      const followupRows = await tx`
        SELECT id, remind_at FROM private_followups
        WHERE user_id = ${user.id}
          AND organization_id = ${user.organization_id}
          AND opportunity_id = ${id}
        FOR UPDATE
      `
      const followup = followupRows[0]
      if (!followup) throw new Error('FOLLOWUP_UPSERT_FAILED')

      let nextReminder = followup.remind_at ? new Date(followup.remind_at).toISOString() : null
      if (mutation.reminder_supplied) nextReminder = mutation.remind_at
      else if (mutation.status !== 'MONITOR') nextReminder = null

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
        WHERE id = ${followup.id}
          AND user_id = ${user.id}
          AND organization_id = ${user.organization_id}
      `
      mutationInserted = true
    })

    return sendJson(response, 200, await followupState(sql, user, id, mutationInserted))
  } catch (error) {
    console.error('private followup request failed', {
      opportunity_id: id,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'FOLLOWUP_REQUEST_FAILED' })
  }
}

function nullableText(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function nullableNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function sanitizeStoredProducts(value) {
  if (!Array.isArray(value)) return []
  const result = []
  for (const item of value) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    const name = nullableText(item.name ?? item.raw_name ?? item.product_name)
    if (!name) continue
    result.push({
      name,
      category: nullableText(item.category),
      quantity: nullableText(item.quantity),
      specification: nullableText(item.specification),
    })
    if (result.length >= 50) break
  }
  return result
}

function sanitizeStoredContact(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const contact = {
    name: nullableText(value.name),
    title: nullableText(value.title),
    phone: nullableText(value.phone),
    email: nullableText(value.email),
  }
  return Object.values(contact).some(Boolean) ? contact : null
}

function sanitizeStoredSnapshot(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const rawFacts = value.facts
  if (!rawFacts || typeof rawFacts !== 'object' || Array.isArray(rawFacts)) return null
  const facts = {
    project_number: nullableText(rawFacts.project_number),
    project_name: nullableText(rawFacts.project_name),
    buyer_name: nullableText(rawFacts.buyer_name),
    hospital_name: nullableText(rawFacts.hospital_name),
    department: nullableText(rawFacts.department),
    region: nullableText(rawFacts.region),
    lifecycle_state: nullableText(rawFacts.lifecycle_state),
    notice_type: nullableText(rawFacts.notice_type),
    published_at: nullableText(rawFacts.published_at),
    registration_deadline: nullableText(rawFacts.registration_deadline),
    registration_deadline_date: nullableText(rawFacts.registration_deadline_date),
    bid_deadline: nullableText(rawFacts.bid_deadline),
    expected_procurement_at: nullableText(rawFacts.expected_procurement_at),
    budget_cny: nullableNumber(rawFacts.budget_cny),
    procurement_method: nullableText(rawFacts.procurement_method),
    product_categories: snapshotStringArray(rawFacts.product_categories),
    product_items: sanitizeStoredProducts(rawFacts.product_items),
    public_contact: sanitizeStoredContact(rawFacts.public_contact),
    verification_status: nullableText(rawFacts.verification_status),
    coverage_status: nullableText(rawFacts.coverage_status),
  }
  const evidenceSourceUrls = Array.isArray(value.evidence_source_urls)
    ? value.evidence_source_urls
        .filter((item) => typeof item === 'string' && /^https:\/\//i.test(item))
        .slice(0, 50)
    : []
  return { facts, evidence_source_urls: evidenceSourceUrls }
}

async function followedRoute(request, response, user) {
  if (!allow(request, response, ['GET'])) return
  const sql = privateDb()
  try {
    const rows = await sql`
      SELECT
        f.opportunity_id, f.status, f.remind_at, f.public_snapshot, f.updated_at,
        (
          SELECT e.note FROM private_followup_events e
          WHERE e.followup_id = f.id AND e.user_id = ${user.id}
            AND e.note IS NOT NULL AND length(trim(e.note)) > 0
          ORDER BY e.created_at DESC, e.id DESC LIMIT 1
        ) AS latest_note
      FROM private_followups f
      WHERE f.user_id = ${user.id} AND f.organization_id = ${user.organization_id}
      ORDER BY f.updated_at DESC, f.id DESC
      LIMIT 100
    `
    const items = []
    for (const row of rows) {
      if (!FOLLOWUP_STATUSES.has(row.status)) continue
      const snapshot = sanitizeStoredSnapshot(row.public_snapshot)
      if (!snapshot) continue
      items.push({
        opportunity_id: row.opportunity_id,
        followup_status: row.status,
        remind_at: row.remind_at ? new Date(row.remind_at).toISOString() : null,
        latest_note: nullableText(row.latest_note),
        followup_updated_at: new Date(row.updated_at).toISOString(),
        facts: snapshot.facts,
        evidence_source_urls: snapshot.evidence_source_urls,
      })
    }
    return sendJson(response, 200, {
      schema_version: '0.1', mode: 'FOLLOWED_OPPORTUNITIES', count: items.length, items,
    })
  } catch (error) {
    console.error('private followed list failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'FOLLOWED_REQUEST_FAILED' })
  }
}

function reminderPublicFacts(snapshot) {
  return {
    buyer_name: snapshot?.facts?.buyer_name ?? null,
    hospital_name: snapshot?.facts?.hospital_name ?? null,
    project_name: snapshot?.facts?.project_name ?? null,
  }
}

function reminderKey(userId, opportunity, remindAt) {
  const digest = createHash('sha256')
    .update(`${userId}\n${opportunity}\n${new Date(remindAt).toISOString()}`)
    .digest('hex')
  return `mrem_${digest}`
}

async function dueReminderRows(sql, user, limit = 20) {
  return sql`
    SELECT
      f.opportunity_id, f.status, f.remind_at, f.public_snapshot,
      (
        SELECT e.note FROM private_followup_events e
        WHERE e.followup_id = f.id AND e.user_id = ${user.id}
          AND e.note IS NOT NULL AND length(trim(e.note)) > 0
        ORDER BY e.created_at DESC, e.id DESC LIMIT 1
      ) AS latest_note
    FROM private_followups f
    WHERE f.user_id = ${user.id}
      AND f.organization_id = ${user.organization_id}
      AND f.remind_at IS NOT NULL
      AND f.remind_at <= now()
    ORDER BY f.remind_at ASC, f.updated_at ASC
    LIMIT ${limit}
  `
}

async function remindersRoute(request, response, user) {
  if (!allow(request, response, ['GET'])) return
  const sql = privateDb()
  try {
    const rows = await dueReminderRows(sql, user, 20)
    const reminders = []
    for (const row of rows) {
      if (!FOLLOWUP_STATUSES.has(row.status) || !row.remind_at) continue
      const snapshot = sanitizeStoredSnapshot(row.public_snapshot)
      if (!snapshot) continue
      const remindAt = new Date(row.remind_at).toISOString()
      reminders.push({
        reminder_id: reminderKey(user.id, row.opportunity_id, remindAt),
        opportunity_id: row.opportunity_id,
        followup_status: row.status,
        remind_at: remindAt,
        note: nullableText(row.latest_note),
        facts: reminderPublicFacts(snapshot),
      })
    }
    return sendJson(response, 200, {
      schema_version: '0.1', mode: 'FOLLOWUP_REMINDER_INBOX', count: reminders.length, reminders,
    })
  } catch (error) {
    console.error('private reminder inbox failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'REMINDER_REQUEST_FAILED' })
  }
}

async function reminderAckRoute(request, response, user) {
  if (!allow(request, response, ['POST'])) return
  const id = reminderId(request)
  if (!id) return sendJson(response, 400, { error: 'REMINDER_ID_INVALID' })
  const sql = privateDb()
  try {
    const rows = await dueReminderRows(sql, user, 100)
    const row = rows.find((item) =>
      item.remind_at && reminderKey(user.id, item.opportunity_id, item.remind_at) === id,
    )
    if (!row) return sendJson(response, 404, { error: 'REMINDER_NOT_FOUND' })

    await sql`
      UPDATE private_followups
      SET remind_at = NULL, updated_at = now()
      WHERE user_id = ${user.id}
        AND organization_id = ${user.organization_id}
        AND opportunity_id = ${row.opportunity_id}
        AND remind_at = ${row.remind_at}
    `
    return sendJson(response, 200, {
      schema_version: '0.1', reminder_id: id, acknowledged: true,
    })
  } catch (error) {
    console.error('private reminder acknowledge failed', {
      reminder_id: id,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'REMINDER_ACK_FAILED' })
  }
}

async function currentFeedback(sql, userId, id) {
  const rows = await sql`
    SELECT value, updated_at FROM private_recommendation_feedback
    WHERE user_id = ${userId} AND opportunity_id = ${id}
    LIMIT 1
  `
  const row = rows[0] || null
  return {
    schema_version: '0.1',
    opportunity_id: id,
    value: row?.value ?? null,
    updated_at: row?.updated_at ? new Date(row.updated_at).toISOString() : null,
  }
}

async function feedbackRoute(request, response, user) {
  if (!allow(request, response, ['GET', 'PUT', 'DELETE'])) return
  const id = opportunityId(request)
  if (!id) return sendJson(response, 400, { error: 'OPPORTUNITY_ID_INVALID' })
  const sql = privateDb()
  try {
    if (request.method === 'GET') {
      return sendJson(response, 200, await currentFeedback(sql, user.id, id))
    }
    if (request.method === 'DELETE') {
      await sql`DELETE FROM private_recommendation_feedback WHERE user_id = ${user.id} AND opportunity_id = ${id}`
      return sendJson(response, 200, {
        schema_version: '0.1', opportunity_id: id, value: null, updated_at: null,
      })
    }

    const body = readJsonBody(request)
    const value = typeof body?.value === 'string' ? body.value : ''
    if (!FEEDBACK_VALUES.has(value)) return sendJson(response, 400, { error: 'FEEDBACK_VALUE_INVALID' })
    const snapshot = await loadVerifiedSnapshot()
    if (!findVerifiedSnapshotCard(snapshot, id)) {
      return sendJson(response, 404, { error: 'VERIFIED_OPPORTUNITY_NOT_FOUND' })
    }
    await sql`
      INSERT INTO private_recommendation_feedback (
        user_id, opportunity_id, value, created_at, updated_at
      ) VALUES (${user.id}, ${id}, ${value}, now(), now())
      ON CONFLICT (user_id, opportunity_id) DO UPDATE SET
        value = EXCLUDED.value, updated_at = now()
    `
    return sendJson(response, 200, await currentFeedback(sql, user.id, id))
  } catch (error) {
    console.error('private recommendation feedback failed', {
      opportunity_id: id,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'FEEDBACK_REQUEST_FAILED' })
  }
}

export default async function handler(request, response) {
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }
  let user
  try {
    user = await authenticatedUser(request)
  } catch (error) {
    console.error('private session lookup failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'SESSION_LOOKUP_FAILED' })
  }
  if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })

  const route = routeName(request)
  if (route === 'today') return todayRoute(request, response, user)
  if (route === 'opportunity') return opportunityRoute(request, response, user)
  if (route === 'followup') return followupRoute(request, response, user)
  if (route === 'followed') return followedRoute(request, response, user)
  if (route === 'reminders') return remindersRoute(request, response, user)
  if (route === 'reminder-ack') return reminderAckRoute(request, response, user)
  if (route === 'feedback') return feedbackRoute(request, response, user)
  return sendJson(response, 404, { error: 'PRIVATE_ROUTE_NOT_FOUND' })
}
