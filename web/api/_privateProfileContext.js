import { privateDb } from './_privateDb.js'

const GENERIC_KEYWORDS = new Set([
  '医疗', '设备', '医疗设备', '耗材', '服务', '医院', '采购', '项目', '系统', '软件', '产品', '仪器',
])

function normalize(value) {
  return String(value || '').trim().toLowerCase().replace(/[\s\-_—–·,，。；;：:（）()【】\[\]]+/g, '')
}

function specificKeyword(value) {
  const keyword = String(value || '').trim()
  const normalized = normalize(keyword)
  if (!normalized || GENERIC_KEYWORDS.has(normalized)) return false
  if (/^[a-z0-9]+$/.test(normalized)) return normalized.length >= 2
  return normalized.length >= 2
}

function productTextItems(facts) {
  const items = Array.isArray(facts?.products)
    ? facts.products
    : Array.isArray(facts?.product_items)
      ? facts.product_items
      : []
  return items.flatMap((item) => [
    item?.name,
    item?.raw_name,
    item?.category,
    item?.specification,
  ])
}

function searchableOpportunityText(facts) {
  const values = [
    facts?.project_name,
    facts?.hospital,
    facts?.hospital_name,
    facts?.buyer_name,
    facts?.department,
    ...(Array.isArray(facts?.product_categories) ? facts.product_categories : []),
    ...productTextItems(facts),
  ]
  return normalize(values.filter(Boolean).join(' '))
}

function hospitalMatches(relation, facts) {
  const relationHospital = normalize(relation.hospital)
  const factHospital = normalize(facts?.hospital || facts?.hospital_name || facts?.buyer_name)
  if (!relationHospital || !factHospital) return false
  if (!(relationHospital === factHospital || relationHospital.includes(factHospital) || factHospital.includes(relationHospital))) {
    return false
  }
  const relationDepartment = normalize(relation.department)
  if (!relationDepartment) return true
  const factDepartment = normalize(facts?.department)
  return Boolean(
    factDepartment &&
    (relationDepartment === factDepartment || relationDepartment.includes(factDepartment) || factDepartment.includes(relationDepartment)),
  )
}

export async function minimalPrivateContextForOpportunity(user, facts) {
  const sql = privateDb()
  const [capabilities, relationships, preferences] = await Promise.all([
    sql`
      SELECT keyword, capability_type, updated_at
      FROM private_product_capabilities
      WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
      ORDER BY updated_at DESC, created_at ASC
      LIMIT 50
    `,
    sql`
      SELECT hospital, department, relationship_strength, updated_at
      FROM private_hospital_relationships
      WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
      ORDER BY updated_at DESC, created_at ASC
      LIMIT 100
    `,
    sql`
      SELECT can_find_manufacturer, can_partner_channel, can_handle_lease, updated_at
      FROM private_user_preferences
      WHERE user_id = ${user.id}
      LIMIT 1
    `,
  ])

  const searchText = searchableOpportunityText(facts)
  const matchingCapabilityRows = capabilities
    .filter((row) => specificKeyword(row.keyword) && searchText.includes(normalize(row.keyword)))
    .slice(0, 12)
  const matchingCapabilities = matchingCapabilityRows.map((row) => ({
    category: row.keyword,
    subcategory: null,
    capability_type: row.capability_type,
    brands: [],
  }))

  const matchingRelationship = relationships.find((row) => hospitalMatches(row, facts)) || null
  const preference = preferences[0] || null
  const partneringPolicy = {
    can_find_manufacturer: preference?.can_find_manufacturer ?? null,
    can_partner_channel: preference?.can_partner_channel ?? null,
    can_handle_lease: preference?.can_handle_lease ?? null,
  }

  const context = {
    context_type: 'CUSTOMER_SELF_REPORTED_CONTEXT',
    hospital_relationship: matchingRelationship
      ? {
          hospital: matchingRelationship.hospital,
          department: matchingRelationship.department,
          relationship_strength: matchingRelationship.relationship_strength,
          last_confirmed_at: matchingRelationship.updated_at
            ? new Date(matchingRelationship.updated_at).toISOString()
            : null,
        }
      : null,
    matching_product_capabilities: matchingCapabilities,
    partnering_policy: partneringPolicy,
  }

  const timestamps = [
    ...matchingCapabilityRows.map((row) => row.updated_at ? new Date(row.updated_at).getTime() : null),
    matchingRelationship?.updated_at ? new Date(matchingRelationship.updated_at).getTime() : null,
    preference?.updated_at ? new Date(preference.updated_at).getTime() : null,
  ].filter((value) => typeof value === 'number' && Number.isFinite(value))

  return {
    context,
    has_context: Boolean(
      context.hospital_relationship ||
      context.matching_product_capabilities.length ||
      Object.values(context.partnering_policy).some((value) => value !== null),
    ),
    profile_version: timestamps.length ? String(Math.max(...timestamps)) : 'empty',
  }
}
