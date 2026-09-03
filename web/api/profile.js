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
  if (routeName(request) === 'public-history') return publicHistoryRoute(request, response)

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

      for (const item of profile.product_capabilities) {
        await tx`
          INSERT INTO private_product_capabilities (
            id, organization_id, user_id, keyword, capability_type
          ) VALUES (
            ${randomUUID()}, ${user.organization_id}, ${user.id}, ${item.keyword}, ${item.capability_type}
          )
        `
      }
      for (const item of profile.hospital_relationships) {
        await tx`
          INSERT INTO private_hospital_relationships (
            id, organization_id, user_id, hospital, department, relationship_strength
          ) VALUES (
            ${randomUUID()}, ${user.organization_id}, ${user.id}, ${item.hospital}, ${item.department}, ${item.relationship_strength}
          )
        `
      }

      if (profile.target_hospitals !== null) {
        await tx`DELETE FROM private_target_hospitals WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}`
        for (const item of profile.target_hospitals) {
          await tx`
            INSERT INTO private_target_hospitals (
              id, organization_id, user_id, hospital, department
            ) VALUES (
              ${randomUUID()}, ${user.organization_id}, ${user.id}, ${item.hospital}, ${item.department}
            )
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
