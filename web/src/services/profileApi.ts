import { apiBaseUrl } from './apiConfig'

export type BusinessRole =
  | 'LOCAL_DISTRIBUTOR'
  | 'REGIONAL_DISTRIBUTOR'
  | 'MANUFACTURER_SALES'
  | 'MANUFACTURER_CHANNEL_MANAGER'
  | 'OTHER'

export type CapabilityType =
  | 'DIRECT_AUTHORIZED'
  | 'DIRECT_UNCONFIRMED'
  | 'CAN_SOURCE_PARTNER'
  | 'SERVICE_ONLY'
  | 'RENTAL_CAPABLE'
  | 'UNKNOWN'

export type RelationshipStrength = 'STRONG' | 'MEDIUM' | 'WEAK' | 'HISTORICAL' | 'UNKNOWN'

export interface CustomerProfileEditable {
  company_name: string
  business_role: BusinessRole
  operating_regions: Array<{
    province: string
    city: string
    scope_mode: 'ENTIRE_CITY' | 'SELECTED_DISTRICTS'
    districts: string[]
  }>
  customer_types: string[]
  product_capabilities: Array<{
    category: string
    subcategory: string | null
    taxonomy_ids: string[]
    brands: string[]
    capability_type: CapabilityType
    notes: string | null
  }>
  partnering_policy: {
    can_seek_temporary_manufacturer: boolean
    can_cooperate_with_channel_partner: boolean
    can_do_rental_projects: boolean
  }
  opportunity_thresholds: {
    minimum_project_amount_cny: string
    owner_attention_amount_cny?: string | null
    preferred_stages: string[]
  }
  exclusion_rules: Array<{ kind: string; value: string; reason?: string | null }>
  hospital_relationships: Array<{
    hospital_name: string
    department: string | null
    relationship_strength: RelationshipStrength
    owner: string | null
    confirmed_by_customer: boolean
    last_confirmed_at: string | null
  }>
  confirmation_flags: {
    region_scope_confirmed: boolean
    customer_types_confirmed: boolean
    product_capabilities_confirmed: boolean
    partnering_policy_confirmed: boolean
    opportunity_preferences_confirmed: boolean
    exclusion_rules_confirmed: boolean
  }
}

export interface ProfileReadiness {
  schema_version: '0.1'
  computed_status: string
  profile_completeness: number
  recommendation_mode: string
  personalized_recommendation_allowed: boolean
  candidate_opportunity_allowed: boolean
  missing_required_conditions: Array<{
    code: string
    field_path: string
    severity: string
    question: string
    reason: string
  }>
  next_question: string | null
  warnings: string[]
}

export interface ProfileEnvelope {
  profile: CustomerProfileEditable & {
    schema_version: '0.1'
    profile_status: string
    profile_completeness: number
    missing_required_conditions: string[]
    updated_at: string | null
  }
  readiness: ProfileReadiness
}

async function request<T>(init?: RequestInit): Promise<T> {
  if (!apiBaseUrl) throw new Error('PROFILE_API_REQUIRES_PILOT_MODE')
  const response = await fetch(`${apiBaseUrl}/profile`, {
    ...init,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  if (response.status === 401) throw new Error('AUTH_REQUIRED')
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
  return (await response.json()) as T
}

export async function getCustomerProfile(): Promise<ProfileEnvelope> {
  return request<ProfileEnvelope>()
}

export async function updateCustomerProfile(
  profile: CustomerProfileEditable,
): Promise<ProfileEnvelope> {
  return request<ProfileEnvelope>({
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })
}
