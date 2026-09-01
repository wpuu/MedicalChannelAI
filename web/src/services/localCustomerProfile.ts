import type {
  CapabilityType,
  CustomerContext,
  HospitalRelationship,
  MatchingProductCapability,
  RelationshipStrength,
  TodayActionCard,
} from '@/types'

const STORAGE_KEY = 'medopp.customer-profile.v1'

export interface LocalProductCapability {
  keyword: string
  capability_type: CapabilityType
}

export interface LocalHospitalRelationship {
  hospital: string
  department: string | null
  relationship_strength: RelationshipStrength
}

export interface LocalCustomerProfile {
  product_capabilities: LocalProductCapability[]
  hospital_relationships: LocalHospitalRelationship[]
  can_find_manufacturer: boolean | null
  can_partner_channel: boolean | null
  can_handle_lease: boolean | null
  updated_at: string | null
}

const EMPTY_PROFILE: LocalCustomerProfile = {
  product_capabilities: [],
  hospital_relationships: [],
  can_find_manufacturer: null,
  can_partner_channel: null,
  can_handle_lease: null,
  updated_at: null,
}

const CAPABILITY_TYPES = new Set<CapabilityType>([
  'DIRECT',
  'NEED_MANUFACTURER',
  'PARTNER',
  'DIRECT_AUTHORIZED',
  'DIRECT_UNCONFIRMED',
  'RENTAL_CAPABLE',
  'CAN_SOURCE_PARTNER',
  'SERVICE_ONLY',
])

const RELATIONSHIP_STRENGTHS = new Set<RelationshipStrength>([
  'STRONG',
  'MEDIUM',
  'HISTORICAL',
  'WEAK',
  'UNKNOWN',
  'NONE',
])

const GENERIC_CAPABILITY_KEYWORDS = new Set([
  '医疗',
  '设备',
  '医疗设备',
  '耗材',
  '服务',
  '医院',
  '采购',
  '项目',
  '系统',
  '软件',
  '产品',
  '仪器',
])

const SHORT_MEDICAL_CAPABILITY_KEYWORDS = new Set([
  'dr',
  'ct',
  'mr',
  'cr',
  'ivd',
  'pcr',
  'lis',
  'his',
  'mri',
  'ecg',
  'icu',
  'gpu',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function cleanText(value: unknown, max = 160): string | null {
  if (typeof value !== 'string') return null
  const text = value.trim().replace(/\s+/g, ' ')
  return text ? text.slice(0, max) : null
}

function triState(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

export function emptyLocalCustomerProfile(): LocalCustomerProfile {
  return structuredClone(EMPTY_PROFILE)
}

export function loadLocalCustomerProfile(): LocalCustomerProfile {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return emptyLocalCustomerProfile()
    const root = asRecord(JSON.parse(raw))
    if (!root) return emptyLocalCustomerProfile()

    const product_capabilities: LocalProductCapability[] = []
    if (Array.isArray(root.product_capabilities)) {
      for (const item of root.product_capabilities.slice(0, 50)) {
        const row = asRecord(item)
        const keyword = cleanText(row?.keyword)
        const type = row?.capability_type
        if (!keyword || typeof type !== 'string' || !CAPABILITY_TYPES.has(type as CapabilityType)) continue
        product_capabilities.push({ keyword, capability_type: type as CapabilityType })
      }
    }

    const hospital_relationships: LocalHospitalRelationship[] = []
    if (Array.isArray(root.hospital_relationships)) {
      for (const item of root.hospital_relationships.slice(0, 100)) {
        const row = asRecord(item)
        const hospital = cleanText(row?.hospital, 240)
        const strength = row?.relationship_strength
        if (
          !hospital ||
          typeof strength !== 'string' ||
          !RELATIONSHIP_STRENGTHS.has(strength as RelationshipStrength)
        ) {
          continue
        }
        hospital_relationships.push({
          hospital,
          department: cleanText(row?.department, 160),
          relationship_strength: strength as RelationshipStrength,
        })
      }
    }

    const updatedAt = cleanText(root.updated_at, 80)
    return {
      product_capabilities,
      hospital_relationships,
      can_find_manufacturer: triState(root.can_find_manufacturer),
      can_partner_channel: triState(root.can_partner_channel),
      can_handle_lease: triState(root.can_handle_lease),
      updated_at: updatedAt && !Number.isNaN(Date.parse(updatedAt)) ? updatedAt : null,
    }
  } catch {
    return emptyLocalCustomerProfile()
  }
}

export function saveLocalCustomerProfile(profile: LocalCustomerProfile): void {
  const normalized: LocalCustomerProfile = {
    product_capabilities: profile.product_capabilities
      .map((item) => ({
        keyword: cleanText(item.keyword) ?? '',
        capability_type: item.capability_type,
      }))
      .filter((item) => item.keyword && CAPABILITY_TYPES.has(item.capability_type))
      .slice(0, 50),
    hospital_relationships: profile.hospital_relationships
      .map((item) => ({
        hospital: cleanText(item.hospital, 240) ?? '',
        department: cleanText(item.department, 160),
        relationship_strength: item.relationship_strength,
      }))
      .filter(
        (item) =>
          item.hospital && RELATIONSHIP_STRENGTHS.has(item.relationship_strength),
      )
      .slice(0, 100),
    can_find_manufacturer: triState(profile.can_find_manufacturer),
    can_partner_channel: triState(profile.can_partner_channel),
    can_handle_lease: triState(profile.can_handle_lease),
    updated_at: new Date().toISOString(),
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
}

export function clearLocalCustomerProfile(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Best effort only.
  }
}

function normalizeForMatch(value: string | null | undefined): string {
  return (value ?? '').toLowerCase().replace(/[\s（）()、，,·.\-_/]+/g, '')
}

export function isSpecificCapabilityKeyword(value: string): boolean {
  const normalized = normalizeForMatch(value)
  if (!normalized || GENERIC_CAPABILITY_KEYWORDS.has(normalized)) return false
  if (SHORT_MEDICAL_CAPABILITY_KEYWORDS.has(normalized)) return true
  const hasCjk = /[\u3400-\u9fff]/.test(normalized)
  return hasCjk ? normalized.length >= 2 : normalized.length >= 4
}

function cardSearchText(card: TodayActionCard): string {
  const values = [
    card.facts.project_name,
    card.facts.department,
    ...(card.facts.product_categories ?? []),
    ...(card.facts.products ?? []).flatMap((item) => [
      item.name,
      item.category,
      item.specification,
    ]),
  ]
  return normalizeForMatch(values.filter(Boolean).join('|'))
}

function capabilityPoints(type: CapabilityType): number {
  switch (type) {
    case 'DIRECT_AUTHORIZED':
    case 'DIRECT':
      return 25
    case 'RENTAL_CAPABLE':
      return 22
    case 'DIRECT_UNCONFIRMED':
      return 18
    case 'NEED_MANUFACTURER':
    case 'CAN_SOURCE_PARTNER':
      return 14
    case 'PARTNER':
      return 12
    case 'SERVICE_ONLY':
      return 8
    default:
      return 0
  }
}

function relationshipPoints(strength: RelationshipStrength): number {
  switch (strength) {
    case 'STRONG':
      return 10
    case 'MEDIUM':
      return 7
    case 'HISTORICAL':
      return 4
    case 'WEAK':
      return 2
    default:
      return 0
  }
}

function hospitalNamesMatch(buyer: string, hospital: string): boolean {
  if (buyer === hospital) return true
  if (hospital.length < 4) return false
  return buyer.includes(hospital) || hospital.includes(buyer)
}

function relationAppliesToCard(
  relation: LocalHospitalRelationship,
  card: TodayActionCard,
): boolean {
  const buyer = normalizeForMatch(card.facts.hospital ?? card.facts.buyer_name)
  const hospital = normalizeForMatch(relation.hospital)
  if (!buyer || !hospital || !hospitalNamesMatch(buyer, hospital)) return false

  const scopedDepartment = normalizeForMatch(relation.department)
  if (!scopedDepartment) return true

  const cardDepartment = normalizeForMatch(card.facts.department)
  if (!cardDepartment) return false
  return (
    cardDepartment === scopedDepartment ||
    cardDepartment.includes(scopedDepartment) ||
    scopedDepartment.includes(cardDepartment)
  )
}

function relationshipForCard(
  card: TodayActionCard,
  profile: LocalCustomerProfile,
): LocalHospitalRelationship | null {
  let best: LocalHospitalRelationship | null = null
  for (const relation of profile.hospital_relationships) {
    if (!relationAppliesToCard(relation, card)) continue
    if (!best || relationshipPoints(relation.relationship_strength) > relationshipPoints(best.relationship_strength)) {
      best = relation
    }
  }
  return best
}

function capabilitiesForCard(
  card: TodayActionCard,
  profile: LocalCustomerProfile,
): LocalProductCapability[] {
  const haystack = cardSearchText(card)
  if (!haystack) return []
  return profile.product_capabilities.filter((capability) => {
    if (!isSpecificCapabilityKeyword(capability.keyword)) return false
    const keyword = normalizeForMatch(capability.keyword)
    return haystack.includes(keyword)
  })
}

function cardLooksLikeLease(card: TodayActionCard): boolean {
  const text = normalizeForMatch(
    [
      card.facts.project_name,
      card.facts.procurement_method,
      ...(card.facts.product_categories ?? []),
    ]
      .filter(Boolean)
      .join('|'),
  )
  return text.includes('租赁') || text.includes('租用') || text.includes('租机')
}

function executionFlexibilityPoints(
  card: TodayActionCard,
  capabilities: LocalProductCapability[],
  profile: LocalCustomerProfile,
): number {
  let points = 0
  const types = new Set(capabilities.map((item) => item.capability_type))

  if (cardLooksLikeLease(card) && profile.can_handle_lease === true) {
    return 5
  }
  if (types.has('RENTAL_CAPABLE') && profile.can_handle_lease === true) {
    points = Math.max(points, 5)
  }
  if (
    (types.has('NEED_MANUFACTURER') || types.has('CAN_SOURCE_PARTNER')) &&
    profile.can_find_manufacturer === true
  ) {
    points = Math.max(points, 3)
  }
  if (
    (types.has('PARTNER') || types.has('CAN_SOURCE_PARTNER')) &&
    profile.can_partner_channel === true
  ) {
    points = Math.max(points, 3)
  }
  if (
    types.has('CAN_SOURCE_PARTNER') &&
    profile.can_find_manufacturer === true &&
    profile.can_partner_channel === true
  ) {
    points = 5
  }
  return Math.min(5, points)
}

function toCustomerContext(
  relation: LocalHospitalRelationship | null,
  capabilities: LocalProductCapability[],
  profile: LocalCustomerProfile,
): CustomerContext {
  const hospitalRelationship: HospitalRelationship | null = relation
    ? {
        hospital: relation.hospital,
        department: relation.department,
        relationship_strength: relation.relationship_strength,
        owner: null,
        last_confirmed_at: profile.updated_at,
      }
    : null

  const matching: MatchingProductCapability[] = capabilities.map((item) => ({
    category: item.keyword,
    subcategory: null,
    matched_taxonomy_ids: [],
    brands: [],
    capability_type: item.capability_type,
  }))

  return {
    hospital_relationship: hospitalRelationship,
    matching_product_capabilities: matching,
    partnering_policy: {
      can_find_manufacturer: profile.can_find_manufacturer,
      can_partner_channel: profile.can_partner_channel,
      can_handle_lease: profile.can_handle_lease,
    },
  }
}

export function personalizeTrialCards(cards: TodayActionCard[]): TodayActionCard[] {
  const profile = loadLocalCustomerProfile()
  if (
    profile.product_capabilities.length === 0 &&
    profile.hospital_relationships.length === 0 &&
    profile.can_find_manufacturer === null &&
    profile.can_partner_channel === null &&
    profile.can_handle_lease === null
  ) {
    return cards
  }

  const personalized = cards.map((card) => {
    const relation = relationshipForCard(card, profile)
    const capabilities = capabilitiesForCard(card, profile)
    const capabilityPoint = capabilities.reduce(
      (max, item) => Math.max(max, capabilityPoints(item.capability_type)),
      0,
    )
    const relationPoint = relation ? relationshipPoints(relation.relationship_strength) : 0
    const flexibilityPoint = executionFlexibilityPoints(card, capabilities, profile)
    const publicBase = Math.max(
      0,
      card.priority.score -
        Math.round((card.priority.components.PRODUCT_EXECUTION_CAPABILITY / 100) * 25) -
        Math.round((card.priority.components.RELATIONSHIP / 100) * 10) -
        Math.round((card.priority.components.EXECUTION_FLEXIBILITY / 100) * 5),
    )
    const privatePoints = capabilityPoint + relationPoint + flexibilityPoint

    return {
      ...card,
      match_status: privatePoints > 0 ? 'MATCHED_PERSONALIZED' : card.match_status,
      customer_context: toCustomerContext(relation, capabilities, profile),
      priority: {
        score: Math.min(100, publicBase + privatePoints),
        components: {
          ...card.priority.components,
          PRODUCT_EXECUTION_CAPABILITY: Math.round((capabilityPoint / 25) * 100),
          RELATIONSHIP: relationPoint * 10,
          EXECUTION_FLEXIBILITY: flexibilityPoint * 20,
        },
      },
    }
  })

  return personalized
    .sort((a, b) => b.priority.score - a.priority.score || a.rank - b.rank)
    .map((card, index) => ({ ...card, rank: index + 1 }))
}
