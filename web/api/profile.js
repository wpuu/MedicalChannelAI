import { randomUUID } from 'node:crypto'
import { authenticatedUser, readJsonBody, sendJson } from './_auth.js'
import { privateDatabaseConfigured, privateDb } from './_privateDb.js'
import { publicOpportunityHistory } from './_publicIntelligenceHistory.js'

const CAPABILITY_TYPES = new Set([
  'DIRECT',
  'NEED_MANUFACTURER',
  'PARTNER',
  'DIRECT_AUTHORIZED',
  'DIRECT_UNCONFIRMED',
  'RENTAL_CAPABLE',
  'CAN_SOURCE_PARTNER',
  'SERVICE_ONLY',
])
const RELATIONSHIP_STRENGTHS = new Set([
  'STRONG', 'MEDIUM', 'HISTORICAL', 'WEAK', 'UNKNOWN', 'NONE',
])
const NOT_FIT_REASON_CODES = new Set([
  'NO_PRODUCT_CAPABILITY', 'NO_MANUFACTURER_ACCESS', 'RELATIONSHIP_TOO_WEAK',
  'AMOUNT_TOO_SMALL', 'PROJECT_TOO_LATE', 'COMPETITOR_LOCKED_CUSTOMER_JUDGMENT',
  'DEPARTMENT_OUT_OF_SCOPE', 'REGION_OUT_OF_SCOPE', 'RENTAL_NOT_SUPPORTED', 'OTHER',
])
const WON_REASON_LABEL_TO_CODE = new Map([
  ['产品或参数匹配', 'PRODUCT_OR_SPEC_MATCH'],
  ['厂家/授权资源有优势', 'MANUFACTURER_OR_AUTHORIZATION_ADVANTAGE'],
  ['医院关系或沟通推进有效', 'RELATIONSHIP_OR_COMMUNICATION_EFFECTIVE'],
  ['价格或商务条件有优势', 'PRICE_OR_COMMERCIAL_ADVANTAGE'],
  ['介入时机合适', 'INTERVENTION_TIMING_GOOD'],
  ['投标/响应执行到位', 'BID_OR_RESPONSE_EXECUTION_STRONG'],
  ['方案与客户需求匹配', 'SOLUTION_DEMAND_MATCH'],
  ['其他', 'OTHER'],
])
const WON_REASON_CODES = new Set(WON_REASON_LABEL_TO_CODE.values())
const WON_REASON_NOTE_PREFIX = '成交复盘（当前用户判断）：'
const LOST_REASON_LABEL_TO_CODE = new Map([
  ['价格/报价竞争失败', 'PRICE_OR_QUOTE_LOST'],
  ['产品或参数不匹配', 'PRODUCT_OR_SPEC_MISMATCH'],
  ['厂家/授权资源不足', 'MANUFACTURER_OR_AUTHORIZATION_GAP'],
  ['医院关系不足', 'HOSPITAL_RELATIONSHIP_GAP'],
  ['介入时间太晚', 'INTERVENTION_TOO_LATE'],
  ['竞争对手优势明显', 'COMPETITOR_ADVANTAGE'],
  ['投标/响应执行失败', 'BID_OR_RESPONSE_EXECUTION_FAILED'],
  ['客户需求或项目变化', 'CUSTOMER_OR_PROJECT_CHANGED'],
  ['主动放弃', 'WITHDRAWN_BY_USER'],
  ['其他', 'OTHER'],
])
const LOST_REASON_CODES = new Set(LOST_REASON_LABEL_TO_CODE.values())
const LOST_REASON_NOTE_PREFIX = '未成交原因（当前用户判断）：'

function cleanText(value, max) {
  if (typeof value !== 'string') return null
  const text = value.trim().replace(/\s+/g, ' ')
  return text ? text.slice(0, max) : null
}

function firstQuery(request, key) {
  const raw = request.query?.[key]
  return Array.isArray(raw) ? raw[0] : raw
}

function routeName(request) {
  const value = firstQuery(request, 'route')
  return typeof value === 'string' ? value.trim() : ''
}

function historyOpportunityId(request) {
  const value = firstQuery(request, 'id')
  const id = typeof value === 'string' ? value.trim() : ''
  return id && id.length <= 200 ? id : null
}

function triState(value) {
  return value === true || value === false || value === null ? value : undefined
}

function targetKey(item) {
  return `${item.hospital.toLowerCase()}|${String(item.department || '').toLowerCase()}`
}

function normalizeCapabilityType(value) {
  if (typeof value !== 'string' || !CAPABILITY_TYPES.has(value)) return null
  return value === 'DIRECT' ? 'DIRECT_UNCONFIRMED' : value
}

function validateProfile(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null
  if (!Array.isArray(body.product_capabilities) || body.product_capabilities.length > 50) return null
  if (!Array.isArray(body.hospital_relationships) || body.hospital_relationships.length > 100) return null
  const targetHospitalsProvided = Object.prototype.hasOwnProperty.call(body, 'target_hospitals')
  if (targetHospitalsProvided && (!Array.isArray(body.target_hospitals) || body.target_hospitals.length > 100)) return null

  const productCapabilities = []
  for (const value of body.product_capabilities) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    const keyword = cleanText(value.keyword, 160)
    const capabilityType = normalizeCapabilityType(value.capability_type)
    if (!keyword || !capabilityType) return null
    productCapabilities.push({ keyword, capability_type: capabilityType })
  }

  const hospitalRelationships = []
  for (const value of body.hospital_relationships) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    const hospital = cleanText(value.hospital, 240)
    const department = value.department === null ? null : cleanText(value.department, 160)
    const strength = value.relationship_strength
    if (!hospital || typeof strength !== 'string' || !RELATIONSHIP_STRENGTHS.has(strength)) return null
    hospitalRelationships.push({ hospital, department, relationship_strength: strength })
  }

  const targetHospitals = []
  const targetKeys = new Set()
  if (targetHospitalsProvided) {
    for (const value of body.target_hospitals) {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return null
      const hospital = cleanText(value.hospital, 240)
      const department = value.department === null ? null : cleanText(value.department, 160)
      if (!hospital) return null
      const item = { hospital, department }
      const key = targetKey(item)
      if (targetKeys.has(key)) continue
      targetKeys.add(key)
      targetHospitals.push(item)
    }
  }

  const productCapabilityMap = new Map()
  for (const item of productCapabilities) {
    productCapabilityMap.set(item.keyword.toLowerCase(), item)
  }
  const relationshipMap = new Map()
  for (const item of hospitalRelationships) {
    relationshipMap.set(targetKey(item), item)
  }

  const canFindManufacturer = triState(body.can_find_manufacturer)
  const canPartnerChannel = triState(body.can_partner_channel)
  const canHandleLease = triState(body.can_handle_lease)
  if (
    canFindManufacturer === undefined ||
    canPartnerChannel === undefined ||
    canHandleLease === undefined
  ) return null

  return {
    product_capabilities: [...productCapabilityMap.values()],
    hospital_relationships: [...relationshipMap.values()],
    target_hospitals: targetHospitalsProvided ? targetHospitals : null,
    can_find_manufacturer: canFindManufacturer,
    can_partner_channel: canPartnerChannel,
    can_handle_lease: canHandleLease,
  }
}

async function requireUser(request, response) {
  if (!privateDatabaseConfigured()) {
    sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
    return null
  }
  const user = await authenticatedUser(request)
  if (!user) {
    sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    return null
  }
  return user
}

async function getProfile(user) {
  const sql = privateDb()
  const [capabilities, relationships, targets, preferences] = await Promise.all([
    sql`
      SELECT keyword,
             CASE WHEN capability_type = 'DIRECT' THEN 'DIRECT_UNCONFIRMED' ELSE capability_type END AS capability_type,
             updated_at
      FROM private_product_capabilities
      WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
      ORDER BY created_at ASC
    `,
    sql`
      SELECT hospital, department, relationship_strength, updated_at
      FROM private_hospital_relationships
      WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
      ORDER BY created_at ASC
    `,
    sql`
      SELECT hospital, department, updated_at
      FROM private_target_hospitals
      WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
      ORDER BY created_at ASC
    `,
    sql`
      SELECT can_find_manufacturer, can_partner_channel, can_handle_lease, updated_at
      FROM private_user_preferences
      WHERE user_id = ${user.id}
      LIMIT 1
    `,
  ])
  const preference = preferences[0] || null
  const timestamps = [
    ...capabilities.map((row) => row.updated_at),
    ...relationships.map((row) => row.updated_at),
    ...targets.map((row) => row.updated_at),
    preference?.updated_at,
  ].filter(Boolean).map((value) => new Date(value).getTime()).filter(Number.isFinite)
  const updatedAt = timestamps.length ? new Date(Math.max(...timestamps)).toISOString() : null
  return {
    product_capabilities: capabilities.map((row) => ({
      keyword: row.keyword,
      capability_type: row.capability_type,
    })),
    hospital_relationships: relationships.map((row) => ({
      hospital: row.hospital,
      department: row.department,
      relationship_strength: row.relationship_strength,
    })),
    target_hospitals: targets.map((row) => ({
      hospital: row.hospital,
      department: row.department,
    })),
    can_find_manufacturer: preference?.can_find_manufacturer ?? null,
    can_partner_channel: preference?.can_partner_channel ?? null,
    can_handle_lease: preference?.can_handle_lease ?? null,
    updated_at: updatedAt,
  }
}

function recognizedOutcomeReason(status, reason, note) {
  const structured = cleanText(reason, 100)
  if (status === 'NOT_FIT') {
    return structured && NOT_FIT_REASON_CODES.has(structured) ? structured : null
  }
  if (status === 'WON') {
    if (structured && WON_REASON_CODES.has(structured)) return structured
    const winNote = cleanText(note, 2000)
    if (!winNote || !winNote.startsWith(WON_REASON_NOTE_PREFIX)) return null
    const label = winNote.slice(WON_REASON_NOTE_PREFIX.length).trim()
    return WON_REASON_LABEL_TO_CODE.get(label) ?? null
  }
  if (status !== 'LOST') return null
  if (structured && LOST_REASON_CODES.has(structured)) return structured

  const legacyNote = cleanText(note, 2000)
  if (!legacyNote || !legacyNote.startsWith(LOST_REASON_NOTE_PREFIX)) return null
  const label = legacyNote.slice(LOST_REASON_NOTE_PREFIX.length).trim()
  return LOST_REASON_LABEL_TO_CODE.get(label) ?? null
}

function incrementReason(counter, code) {
  counter.set(code, (counter.get(code) ?? 0) + 1)
}

function sortedReasonCounts(counter) {
  return [...counter.entries()]
    .map(([code, count]) => ({ code, count }))
    .sort((left, right) => right.count - left.count || left.code.localeCompare(right.code))
}

async function outcomeSummaryRoute(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  const user = await requireUser(request, response)
  if (!user) return

  try {
    const sql = privateDb()
    const wonNotePattern = `${WON_REASON_NOTE_PREFIX}%`
    const lostNotePattern = `${LOST_REASON_NOTE_PREFIX}%`
    const rows = await sql`
      SELECT
        f.status,
        (
          SELECT e.reason FROM private_followup_events e
          WHERE e.followup_id = f.id AND e.user_id = ${user.id} AND e.status = f.status
            AND e.reason IS NOT NULL AND length(trim(e.reason)) > 0
          ORDER BY e.created_at DESC, e.id DESC LIMIT 1
        ) AS latest_reason,
        (
          SELECT e.note FROM private_followup_events e
          WHERE e.followup_id = f.id AND e.user_id = ${user.id} AND e.status = f.status
            AND (
              (f.status = 'WON' AND e.note LIKE ${wonNotePattern}) OR
              (f.status = 'LOST' AND e.note LIKE ${lostNotePattern})
            )
          ORDER BY e.created_at DESC, e.id DESC LIMIT 1
        ) AS latest_note
      FROM private_followups f
      WHERE f.user_id = ${user.id}
        AND f.organization_id = ${user.organization_id}
        AND f.status IN ('WON', 'LOST', 'NOT_FIT')
      ORDER BY f.updated_at DESC, f.id DESC
      LIMIT 5001
    `
    if (rows.length > 5000) {
      return sendJson(response, 409, { error: 'OUTCOME_SUMMARY_TRUNCATED' })
    }

    let won = 0
    let lost = 0
    let notFit = 0
    let unclassifiedWon = 0
    let unclassifiedLost = 0
    let unclassifiedNotFit = 0
    const wonReasons = new Map()
    const lostReasons = new Map()
    const notFitReasons = new Map()

    for (const row of rows) {
      if (row.status === 'WON') {
        won += 1
        const reason = recognizedOutcomeReason('WON', row.latest_reason, row.latest_note)
        if (reason) incrementReason(wonReasons, reason)
        else unclassifiedWon += 1
        continue
      }
      if (row.status === 'LOST') {
        lost += 1
        const reason = recognizedOutcomeReason('LOST', row.latest_reason, row.latest_note)
        if (reason) incrementReason(lostReasons, reason)
        else unclassifiedLost += 1
        continue
      }
      if (row.status === 'NOT_FIT') {
        notFit += 1
        const reason = recognizedOutcomeReason('NOT_FIT', row.latest_reason, row.latest_note)
        if (reason) incrementReason(notFitReasons, reason)
        else unclassifiedNotFit += 1
      }
    }

    const decidedCount = won + lost
    return sendJson(response, 200, {
      schema_version: '0.1',
      mode: 'PRIVATE_OUTCOME_SUMMARY',
      total_terminal: won + lost + notFit,
      won,
      lost,
      not_fit: notFit,
      decided_count: decidedCount,
      win_rate_percent: decidedCount ? Math.round((won / decidedCount) * 100) : null,
      won_reason_counts: sortedReasonCounts(wonReasons),
      lost_reason_counts: sortedReasonCounts(lostReasons),
      not_fit_reason_counts: sortedReasonCounts(notFitReasons),
      unclassified_won: unclassifiedWon,
      unclassified_lost: unclassifiedLost,
      unclassified_not_fit: unclassifiedNotFit,
    })
  } catch (error) {
    console.error('private outcome summary request failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'OUTCOME_SUMMARY_REQUEST_FAILED' })
  }
}

async function publicHistoryRoute(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  const user = await requireUser(request, response)
  if (!user) return
  const id = historyOpportunityId(request)
  if (!id) return sendJson(response, 400, { error: 'OPPORTUNITY_ID_INVALID' })
  try {
    return sendJson(response, 200, await publicOpportunityHistory(id))
  } catch (error) {
    console.error('public opportunity history request failed', {
      opportunity_id: id,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'PUBLIC_HISTORY_REQUEST_FAILED' })
  }
}

export default async function handler(request, response) {
  const route = routeName(request)
  if (route === 'public-history') return publicHistoryRoute(request, response)
  if (route === 'outcome-summary') return outcomeSummaryRoute(request, response)

  if (!['GET', 'PUT', 'DELETE'].includes(request.method)) {
    response.setHeader('Allow', 'GET, PUT, DELETE')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }

  try {
    const user = await requireUser(request, response)
    if (!user) return
    const sql = privateDb()

    if (request.method === 'GET') {
      return sendJson(response, 200, {
        schema_version: '0.1',
        mode: 'PRIVATE_CUSTOMER_PROFILE',
        profile: await getProfile(user),
      })
    }

    if (request.method === 'DELETE') {
      await sql.begin(async (tx) => {
        await tx`DELETE FROM private_product_capabilities WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}`
        await tx`DELETE FROM private_hospital_relationships WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}`
        await tx`DELETE FROM private_target_hospitals WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}`
        await tx`DELETE FROM private_user_preferences WHERE user_id = ${user.id}`
      })
      return sendJson(response, 200, {
        schema_version: '0.1',
        cleared: true,
      })
    }

    const profile = validateProfile(readJsonBody(request))
    if (!profile) return sendJson(response, 400, { error: 'PROFILE_INVALID' })

    await sql.begin(async (tx) => {
      await tx`DELETE FROM private_product_capabilities WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}`
      await tx`DELETE FROM private_hospital_relationships WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}`

      const capabilityRows = profile.product_capabilities.map((item) => ({
        id: randomUUID(),
        organization_id: user.organization_id,
        user_id: user.id,
        keyword: item.keyword,
        capability_type: item.capability_type,
      }))
      if (capabilityRows.length) {
        await tx`
          INSERT INTO private_product_capabilities
          ${tx(capabilityRows, 'id', 'organization_id', 'user_id', 'keyword', 'capability_type')}
        `
      }

      const relationshipRows = profile.hospital_relationships.map((item) => ({
        id: randomUUID(),
        organization_id: user.organization_id,
        user_id: user.id,
        hospital: item.hospital,
        department: item.department,
        relationship_strength: item.relationship_strength,
      }))
      if (relationshipRows.length) {
        await tx`
          INSERT INTO private_hospital_relationships
          ${tx(relationshipRows, 'id', 'organization_id', 'user_id', 'hospital', 'department', 'relationship_strength')}
        `
      }

      if (profile.target_hospitals !== null) {
        await tx`DELETE FROM private_target_hospitals WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}`
        const targetRows = profile.target_hospitals.map((item) => ({
          id: randomUUID(),
          organization_id: user.organization_id,
          user_id: user.id,
          hospital: item.hospital,
          department: item.department,
        }))
        if (targetRows.length) {
          await tx`
            INSERT INTO private_target_hospitals
            ${tx(targetRows, 'id', 'organization_id', 'user_id', 'hospital', 'department')}
          `
        }
      }

      await tx`
        INSERT INTO private_user_preferences (
          user_id, can_find_manufacturer, can_partner_channel, can_handle_lease, updated_at
        ) VALUES (
          ${user.id}, ${profile.can_find_manufacturer}, ${profile.can_partner_channel}, ${profile.can_handle_lease}, now()
        )
        ON CONFLICT (user_id) DO UPDATE SET
          can_find_manufacturer = EXCLUDED.can_find_manufacturer,
          can_partner_channel = EXCLUDED.can_partner_channel,
          can_handle_lease = EXCLUDED.can_handle_lease,
          updated_at = now()
      `
    })

    return sendJson(response, 200, {
      schema_version: '0.1',
      mode: 'PRIVATE_CUSTOMER_PROFILE',
      profile: await getProfile(user),
    })
  } catch (error) {
    console.error('private profile request failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'PROFILE_REQUEST_FAILED' })
  }
}