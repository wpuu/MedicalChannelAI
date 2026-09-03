import type {
  CapabilityType,
  CustomerContext,
  HospitalRelationship,
  MatchingProductCapability,
  RelationshipStrength,
  TargetHospitalInterest,
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

export interface LocalTargetHospital {
  hospital: string
  department: string | null
}

export interface LocalCustomerProfile {
  product_capabilities: LocalProductCapability[]
  hospital_relationships: LocalHospitalRelationship[]
  target_hospitals: LocalTargetHospital[]
  can_find_manufacturer: boolean | null
  can_partner_channel: boolean | null
  can_handle_lease: boolean | null
  updated_at: string | null
}

const EMPTY_PROFILE: LocalCustomerProfile = {
  product_capabilities: [],
  hospital_relationships: [],
  target_hospitals: [],
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
  'dsa',
  'ivd',
  'pcr',
  'lis',
  'his',
  'mri',
  'ecg',
  'icu',
  'gpu',
])

const CAPABILITY_ALIAS_GROUPS = [
  ['dsa', '数字减影血管造影', '数字减影血管造影机', '血管造影机'],
  ['dr', '数字x光机', '数字x线摄影', '数字化x线摄影', '数字化x射线摄影'],
  ['ct', 'ct机', 'ct影像', '计算机断层扫描', '电子计算机断层扫描'],
  ['mr', 'mri', '磁共振', '磁共振成像'],
  ['cr', '计算机x线摄影'],
  ['ivd', '体外诊断', '体外诊断试剂', '检测试剂', '质控品', '校准品'],
  ['pcr', '聚合酶链式反应', '核酸扩增'],
  ['lis', '检验信息系统', '实验室信息系统'],
  ['his', '医院信息系统'],
  ['ecg', '心电图', '心电图机'],
]

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

    const target_hospitals: LocalTargetHospital[] = []
    if (Array.isArray(root.target_hospitals)) {
      const keys = new Set<string>()
      for (const item of root.target_hospitals.slice(0, 100)) {
        const row = asRecord(item)
        const hospital = cleanText(row?.hospital, 240)
        if (!hospital) continue
        const department = cleanText(row?.department, 160)
        const key = `${hospital.toLowerCase()}|${(department ?? '').toLowerCase()}`
        if (keys.has(key)) continue
        keys.add(key)
        target_hospitals.push({ hospital, department })
      }
    }

    const updatedAt = cleanText(root.updated_at, 80)
    return {
      product_capabilities,
      hospital_relationships,
      target_hospitals,
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
  const targetKeys = new Set<string>()
  const normalizedTargets: LocalTargetHospital[] = []
  for (const item of profile.target_hospitals) {
    const hospital = cleanText(item.hospital, 240) ?? ''
    const department = cleanText(item.department, 160)
    if (!hospital) continue
    const key = `${hospital.toLowerCase()}|${(department ?? '').toLowerCase()}`
    if (targetKeys.has(key)) continue
    targetKeys.add(key)
    normalizedTargets.push({ hospital, department })
    if (normalizedTargets.length >= 100) break
  }

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
    target_hospitals: normalizedTargets,
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

const NORMALIZED_CAPABILITY_ALIAS_GROUPS = CAPABILITY_ALIAS_GROUPS.map((group) =>
  group.map((item) => normalizeForMatch(item)).filter(Boolean),
)

export function isSpecificCapabilityKeyword(value: string): boolean {
  const normalized = normalizeForMatch(value)
  if (!normalized || GENERIC_CAPABILITY_KEYWORDS.has(normalized)) return false
  if (SHORT_MEDICAL_CAPABILITY_KEYWORDS.has(normalized)) return true
  const hasCjk = /[\u3400-\u9fff]/.test(normalized)
  return hasCjk ? normalized.length >= 2 : normalized.length >= 4
}

function capabilityMatchTerms(value: string): string[] {
  const keyword = normalizeForMatch(value)
  if (!keyword) return []
  const group = NORMALIZED_CAPABILITY_ALIAS_GROUPS.find((items) => items.includes(keyword))
  return group ?? [keyword]
}

function shortAsciiTokenMatches(rawText: string, term: string): boolean {
  if (!/^[a-z0-9]{2,3}$/.test(term)) return false
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`, 'i').test(rawText)
}

function cardSearchText(card: TodayActionCard): { raw: string; normalized: string } {
  const values = [
    card.facts.project_name,
    card.facts.department,
    ...(card.facts.product_categories ?? []),
    ...(card.facts.products ?? []).flatMap((item) => [
      item.name,
      item.category,
      item.specification,
    ]),
  ].filter(Boolean)
  const raw = values.join(' | ').toLowerCase()
  return { raw, normalized: normalizeForMatch(raw) }
}

function capabilityPoints(type: CapabilityType): number {
  switch (type) {
    case 'DIRECT_AUTHORIZED':
      return 25
    case 'RENTAL_CAPABLE':
      return 22
    case 'DIRECT':
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

function hospitalScopeAppliesToCard(
  item: Pick<LocalHospitalRelationship, 'hospital' | 'department'> | LocalTargetHospital,
  card: TodayActionCard,
): boolean {
  const buyer = normalizeForMatch(card.facts.hospital ?? card.facts.buyer_name)
  const hospital = normalizeForMatch(item.hospital)
  if (!buyer || !hospital || !hospitalNamesMatch(buyer, hospital)) return false

  const scopedDepartment = normalizeForMatch(item.department)
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
    if (!hospitalScopeAppliesToCard(relation, card)) continue
    if (!best || relationshipPoints(relation.relationship_strength) > relationshipPoints(best.relationship_strength)) {
      best = relation
    }
  }
  return best
}

function targetForCard(
  card: TodayActionCard,
  profile: LocalCustomerProfile,
): LocalTargetHospital | null {
  return profile.target_hospitals.find((target) => hospitalScopeAppliesToCard(target, card)) ?? null
}

function capabilityForCard(
  card: TodayActionCard,
  profile: LocalCustomerProfile,
): LocalProductCapability | null {
  const searchText = cardSearchText(card)
  let best: LocalProductCapability | null = null
  for (const capability of profile.product_capabilities) {
    if (!isSpecificCapabilityKeyword(capability.keyword)) continue
    const matches = capabilityMatchTerms(capability.keyword).some((term) =>
      /^[a-z0-9]{2,3}$/.test(term)
        ? shortAsciiTokenMatches(searchText.raw, term)
        : searchText.normalized.includes(term),
    )
    if (!matches) continue
    if (!best || capabilityPoints(capability.capability_type) > capabilityPoints(best.capability_type)) {
      best = capability
    }
  }
  return best
}

function flexibilityPoints(
  card: TodayActionCard,
  capability: LocalProductCapability | null,
  profile: LocalCustomerProfile,
): number {
  if (!capability) return 0
  const projectText = normalizeForMatch(
    [card.facts.project_name, card.facts.procurement_method].filter(Boolean).join(' '),
  )
  let score = 0
  if (projectText.includes('租赁') && profile.can_handle_lease) score = 5
  if (capability.capability_type === 'RENTAL_CAPABLE' && profile.can_handle_lease) score = 5
  if (
    (capability.capability_type === 'NEED_MANUFACTURER' || capability.capability_type === 'CAN_SOURCE_PARTNER') &&
    profile.can_find_manufacturer
  ) {
    score = Math.max(score, 3)
  }
  if (
    (capability.capability_type === 'PARTNER' || capability.capability_type === 'CAN_SOURCE_PARTNER') &&
    profile.can_partner_channel
  ) {
    score = Math.max(score, 3)
  }
  if (
    capability.capability_type === 'CAN_SOURCE_PARTNER' &&
    profile.can_find_manufacturer &&
    profile.can_partner_channel
  ) {
    score = 5
  }
  return score
}

function priorityBaseScore(card: TodayActionCard): number {
  const privateComponentCodes = new Set([
    'PRODUCT_EXECUTION_CAPABILITY',
    'RELATIONSHIP',
    'EXECUTION_FLEXIBILITY',
  ])
  const components = card.priority.raw_components ?? []
  if (components.length) {
    return components.reduce(
      (sum, component) => privateComponentCodes.has(component.code) ? sum : sum + component.points,
      0,
    )
  }
  // The public ranking contract is 60 points; never reuse a previously personalized
  // score as the base for another personalization pass.
  return Math.min(60, card.priority.score)
}

export function applyLocalCustomerProfile(
  card: TodayActionCard,
  profile: LocalCustomerProfile,
): TodayActionCard {
  const relationship = relationshipForCard(card, profile)
  const target = targetForCard(card, profile)
  const capability = capabilityForCard(card, profile)
  const relationshipScore = relationship ? relationshipPoints(relationship.relationship_strength) : 0
  const capabilityScore = capability ? capabilityPoints(capability.capability_type) : 0
  const flexibilityScore = flexibilityPoints(card, capability, profile)
  const baseScore = priorityBaseScore(card)

  const hospitalRelationship: HospitalRelationship | null = relationship
    ? {
        hospital: relationship.hospital,
        department: relationship.department,
        relationship_strength: relationship.relationship_strength,
        owner: '当前用户',
        last_confirmed_at: profile.updated_at,
      }
    : null

  const targetHospital: TargetHospitalInterest | null = target
    ? {
        hospital: target.hospital,
        department: target.department,
        watched_by_customer: true,
        updated_at: profile.updated_at,
      }
    : null

  const matchingCapability: MatchingProductCapability | null = capability
    ? {
        category: capability.keyword,
        subcategory: null,
        matched_taxonomy_ids: [],
        brands: [],
        capability_type: capability.capability_type,
      }
    : null

  const customerContext: CustomerContext = {
    target_hospital: targetHospital,
    hospital_relationship: hospitalRelationship,
    matching_product_capabilities: matchingCapability ? [matchingCapability] : [],
    partnering_policy: {
      can_find_manufacturer: profile.can_find_manufacturer,
      can_partner_channel: profile.can_partner_channel,
      can_handle_lease: profile.can_handle_lease,
    },
  }

  return {
    ...card,
    customer_context: customerContext,
    priority: {
      ...card.priority,
      score: Math.min(100, baseScore + relationshipScore + capabilityScore + flexibilityScore),
      score_scope: 'PERSONALIZED',
      components: {
        ...card.priority.components,
        PRODUCT_EXECUTION_CAPABILITY: Math.round((capabilityScore / 25) * 100),
        RELATIONSHIP: Math.round((relationshipScore / 10) * 100),
        EXECUTION_FLEXIBILITY: Math.round((flexibilityScore / 5) * 100),
      },
    },
  }
}
