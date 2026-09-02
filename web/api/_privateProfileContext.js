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
  if (/^[a-z0-9]+$/.test(normalized)) return normalized.length >= 4
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

function hospitalScopeMatches(item, facts) {
  const itemHospital = normalize(item.hospital)
  const factHospital = normalize(facts?.hospital || facts?.hospital_name || facts?.buyer_name)
  if (!itemHospital || !factHospital) return false
  if (!(itemHospital === factHospital || itemHospital.includes(factHospital) || factHospital.includes(itemHospital))) {
    return false
  }
  const itemDepartment = normalize(item.department)
  if (!itemDepartment) return true
  const factDepartment = normalize(facts?.department)
  return Boolean(
    factDepartment &&
    (itemDepartment === factDepartment || itemDepartment.includes(factDepartment) || factDepartment.includes(itemDepartment)),
  )
}

function relationshipPoints(strength) {
  switch (strength) {
    case 'STRONG': return 10
    case 'MEDIUM': return 7
    case 'HISTORICAL': return 4
    case 'WEAK': return 2
    default: return 0
  }
}

function capabilityPoints(type) {
  switch (type) {
    case 'DIRECT_AUTHORIZED':
    case 'DIRECT': return 25
    case 'RENTAL_CAPABLE': return 22
    case 'DIRECT_UNCONFIRMED': return 18
    case 'NEED_MANUFACTURER':
    case 'CAN_SOURCE_PARTNER': return 14
    case 'PARTNER': return 12
    case 'SERVICE_ONLY': return 8
    default: return 0
  }
}

function cardLooksLikeLease(facts) {
  const text = normalize([
    facts?.project_name,
    facts?.procurement_method,
    ...(Array.isArray(facts?.product_categories) ? facts.product_categories : []),
  ].filter(Boolean).join(' '))
  return text.includes('租赁') || text.includes('租用') || text.includes('租机')
}

export async function loadPrivateProfileForUser(user) {
  const sql = privateDb()
  const [capabilities, relationships, targets, preferences] = await Promise.all([
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
      SELECT hospital, department, updated_at
      FROM private_target_hospitals
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
  return {
    capabilities: [...capabilities],
    relationships: [...relationships],
    targets: [...targets],
    preferences: preferences[0] || null,
  }
}

export function minimalPrivateContextFromProfile(profile, facts) {
  const searchText = searchableOpportunityText(facts)
  const matchingCapabilityRows = profile.capabilities
    .filter((row) => specificKeyword(row.keyword) && searchText.includes(normalize(row.keyword)))
    .slice(0, 12)
  const matchingCapabilities = matchingCapabilityRows.map((row) => ({
    category: row.keyword,
    subcategory: null,
    capability_type: row.capability_type,
    brands: [],
  }))

  let matchingRelationship = null
  for (const relation of profile.relationships) {
    if (!hospitalScopeMatches(relation, facts)) continue
    if (!matchingRelationship || relationshipPoints(relation.relationship_strength) > relationshipPoints(matchingRelationship.relationship_strength)) {
      matchingRelationship = relation
    }
  }

  const matchingTarget = profile.targets.find((target) => hospitalScopeMatches(target, facts)) || null

  const preference = profile.preferences
  const partneringPolicy = {
    can_find_manufacturer: preference?.can_find_manufacturer ?? null,
    can_partner_channel: preference?.can_partner_channel ?? null,
    can_handle_lease: preference?.can_handle_lease ?? null,
  }

  const context = {
    context_type: 'CUSTOMER_SELF_REPORTED_CONTEXT',
    target_hospital: matchingTarget
      ? {
          hospital: matchingTarget.hospital,
          department: matchingTarget.department,
          watched_by_customer: true,
          updated_at: matchingTarget.updated_at
            ? new Date(matchingTarget.updated_at).toISOString()
            : null,
        }
      : null,
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
    matchingTarget?.updated_at ? new Date(matchingTarget.updated_at).getTime() : null,
    preference?.updated_at ? new Date(preference.updated_at).getTime() : null,
  ].filter((value) => typeof value === 'number' && Number.isFinite(value))

  return {
    context,
    has_context: Boolean(
      context.target_hospital ||
      context.hospital_relationship ||
      context.matching_product_capabilities.length ||
      Object.values(context.partnering_policy).some((value) => value !== null),
    ),
    profile_version: timestamps.length ? String(Math.max(...timestamps)) : 'empty',
  }
}

export function privatePriorityPoints(context, facts) {
  const capabilityPoint = (context.matching_product_capabilities || []).reduce(
    (max, item) => Math.max(max, capabilityPoints(item.capability_type)),
    0,
  )
  // Target-hospital interest is deliberately NOT relationship evidence and therefore
  // contributes zero relationship points. Only a confirmed hospital_relationship scores.
  const relationshipPoint = context.hospital_relationship
    ? relationshipPoints(context.hospital_relationship.relationship_strength)
    : 0

  const types = new Set((context.matching_product_capabilities || []).map((item) => item.capability_type))
  const policy = context.partnering_policy || {}
  let flexibilityPoint = 0
  if (cardLooksLikeLease(facts) && policy.can_handle_lease === true) {
    flexibilityPoint = 5
  }
  if (types.has('RENTAL_CAPABLE') && policy.can_handle_lease === true) {
    flexibilityPoint = Math.max(flexibilityPoint, 5)
  }
  if (
    (types.has('NEED_MANUFACTURER') || types.has('CAN_SOURCE_PARTNER')) &&
    policy.can_find_manufacturer === true
  ) {
    flexibilityPoint = Math.max(flexibilityPoint, 3)
  }
  if (
    (types.has('PARTNER') || types.has('CAN_SOURCE_PARTNER')) &&
    policy.can_partner_channel === true
  ) {
    flexibilityPoint = Math.max(flexibilityPoint, 3)
  }
  if (
    types.has('CAN_SOURCE_PARTNER') &&
    policy.can_find_manufacturer === true &&
    policy.can_partner_channel === true
  ) {
    flexibilityPoint = 5
  }

  return {
    capability: capabilityPoint,
    relationship: relationshipPoint,
    flexibility: Math.min(5, flexibilityPoint),
  }
}

export async function minimalPrivateContextForOpportunity(user, facts) {
  const profile = await loadPrivateProfileForUser(user)
  return minimalPrivateContextFromProfile(profile, facts)
}
