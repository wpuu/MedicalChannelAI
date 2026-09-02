import type { CapabilityType, RelationshipStrength } from '@/types'
import { apiBaseUrl, isApiMode } from './apiConfig'
import {
  clearLocalCustomerProfile,
  emptyLocalCustomerProfile,
  loadLocalCustomerProfile,
  saveLocalCustomerProfile,
  type LocalCustomerProfile,
} from './localCustomerProfile'

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
  'STRONG', 'MEDIUM', 'HISTORICAL', 'WEAK', 'UNKNOWN', 'NONE',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function triState(value: unknown): boolean | null | undefined {
  return value === true || value === false || value === null ? value : undefined
}

function parseProfile(value: unknown): LocalCustomerProfile {
  const root = asRecord(value)
  if (!root || !Array.isArray(root.product_capabilities) || !Array.isArray(root.hospital_relationships)) {
    throw new Error('PROFILE_RESPONSE_INVALID')
  }

  const product_capabilities = root.product_capabilities.map((value) => {
    const row = asRecord(value)
    if (
      !row || typeof row.keyword !== 'string' ||
      typeof row.capability_type !== 'string' ||
      !CAPABILITY_TYPES.has(row.capability_type as CapabilityType)
    ) throw new Error('PROFILE_RESPONSE_INVALID')
    return {
      keyword: row.keyword,
      capability_type: row.capability_type as CapabilityType,
    }
  })

  const hospital_relationships = root.hospital_relationships.map((value) => {
    const row = asRecord(value)
    if (
      !row || typeof row.hospital !== 'string' ||
      !(row.department === null || typeof row.department === 'string') ||
      typeof row.relationship_strength !== 'string' ||
      !RELATIONSHIP_STRENGTHS.has(row.relationship_strength as RelationshipStrength)
    ) throw new Error('PROFILE_RESPONSE_INVALID')
    return {
      hospital: row.hospital,
      department: row.department as string | null,
      relationship_strength: row.relationship_strength as RelationshipStrength,
    }
  })

  const can_find_manufacturer = triState(root.can_find_manufacturer)
  const can_partner_channel = triState(root.can_partner_channel)
  const can_handle_lease = triState(root.can_handle_lease)
  if (
    can_find_manufacturer === undefined ||
    can_partner_channel === undefined ||
    can_handle_lease === undefined ||
    !(root.updated_at === null || typeof root.updated_at === 'string')
  ) throw new Error('PROFILE_RESPONSE_INVALID')

  return {
    product_capabilities,
    hospital_relationships,
    can_find_manufacturer,
    can_partner_channel,
    can_handle_lease,
    updated_at: root.updated_at as string | null,
  }
}

async function parseResponse(response: Response): Promise<LocalCustomerProfile> {
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
  const root = asRecord(await response.json())
  if (!root || root.schema_version !== '0.1' || root.mode !== 'PRIVATE_CUSTOMER_PROFILE') {
    throw new Error('PROFILE_RESPONSE_INVALID')
  }
  return parseProfile(root.profile)
}

export async function loadCustomerProfile(): Promise<LocalCustomerProfile> {
  if (!isApiMode) return loadLocalCustomerProfile()
  const response = await fetch(`${apiBaseUrl}/profile`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  return parseResponse(response)
}

export async function saveCustomerProfile(profile: LocalCustomerProfile): Promise<LocalCustomerProfile> {
  if (!isApiMode) {
    saveLocalCustomerProfile(profile)
    return loadLocalCustomerProfile()
  }
  const response = await fetch(`${apiBaseUrl}/profile`, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      product_capabilities: profile.product_capabilities,
      hospital_relationships: profile.hospital_relationships,
      can_find_manufacturer: profile.can_find_manufacturer,
      can_partner_channel: profile.can_partner_channel,
      can_handle_lease: profile.can_handle_lease,
    }),
  })
  return parseResponse(response)
}

export async function clearCustomerProfile(): Promise<LocalCustomerProfile> {
  if (!isApiMode) {
    clearLocalCustomerProfile()
    return emptyLocalCustomerProfile()
  }
  const response = await fetch(`${apiBaseUrl}/profile`, {
    method: 'DELETE',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
  return emptyLocalCustomerProfile()
}
