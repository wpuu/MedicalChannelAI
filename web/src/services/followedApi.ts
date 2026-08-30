import { apiBaseUrl, isApiMode } from './apiConfig'

export interface FollowedOpportunity {
  opportunity_id: string
  followup_status: string
  remind_at: string | null
  latest_note: string | null
  followup_updated_at: string
  facts: {
    project_number: string | null
    project_name: string | null
    buyer_name: string | null
    hospital_name: string | null
    department: string | null
    lifecycle_state: string | null
    published_at: string | null
    bid_deadline: string | null
    expected_procurement_at: string | null
    budget_cny: number | null
  }
  evidence_source_urls: string[]
}

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
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function exactKeys(record: Record<string, unknown>, allowed: string[]): boolean {
  const expected = new Set(allowed)
  const keys = Object.keys(record)
  return keys.length === expected.size && keys.every((key) => expected.has(key))
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function nullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value))
}

function validateItem(value: unknown): FollowedOpportunity {
  const row = asRecord(value)
  if (
    !row ||
    !exactKeys(row, [
      'opportunity_id',
      'followup_status',
      'remind_at',
      'latest_note',
      'followup_updated_at',
      'facts',
      'evidence_source_urls',
    ]) ||
    typeof row.opportunity_id !== 'string' ||
    !/^opp_[0-9a-fA-F-]{36}$/.test(row.opportunity_id) ||
    typeof row.followup_status !== 'string' ||
    !FOLLOWUP_STATUSES.has(row.followup_status) ||
    !nullableString(row.remind_at) ||
    !nullableString(row.latest_note) ||
    typeof row.followup_updated_at !== 'string' ||
    Number.isNaN(new Date(row.followup_updated_at).getTime()) ||
    !Array.isArray(row.evidence_source_urls) ||
    row.evidence_source_urls.some((item) => typeof item !== 'string')
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }

  const facts = asRecord(row.facts)
  if (
    !facts ||
    !exactKeys(facts, [
      'project_number',
      'project_name',
      'buyer_name',
      'hospital_name',
      'department',
      'lifecycle_state',
      'published_at',
      'bid_deadline',
      'expected_procurement_at',
      'budget_cny',
    ]) ||
    !nullableString(facts.project_number) ||
    !nullableString(facts.project_name) ||
    !nullableString(facts.buyer_name) ||
    !nullableString(facts.hospital_name) ||
    !nullableString(facts.department) ||
    !nullableString(facts.lifecycle_state) ||
    !nullableString(facts.published_at) ||
    !nullableString(facts.bid_deadline) ||
    !nullableString(facts.expected_procurement_at) ||
    !nullableNumber(facts.budget_cny)
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }

  return {
    opportunity_id: row.opportunity_id,
    followup_status: row.followup_status,
    remind_at: row.remind_at,
    latest_note: row.latest_note,
    followup_updated_at: row.followup_updated_at,
    facts: {
      project_number: facts.project_number,
      project_name: facts.project_name,
      buyer_name: facts.buyer_name,
      hospital_name: facts.hospital_name,
      department: facts.department,
      lifecycle_state: facts.lifecycle_state,
      published_at: facts.published_at,
      bid_deadline: facts.bid_deadline,
      expected_procurement_at: facts.expected_procurement_at,
      budget_cny: facts.budget_cny,
    },
    evidence_source_urls: [...row.evidence_source_urls] as string[],
  }
}

export async function getFollowedOpportunities(): Promise<FollowedOpportunity[]> {
  if (!isApiMode) return []
  const response = await fetch(`${apiBaseUrl}/followed`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
  const value: unknown = await response.json()
  const root = asRecord(value)
  if (
    !root ||
    !exactKeys(root, ['schema_version', 'mode', 'count', 'items']) ||
    root.schema_version !== '0.1' ||
    root.mode !== 'FOLLOWED_OPPORTUNITIES' ||
    typeof root.count !== 'number' ||
    !Number.isInteger(root.count) ||
    root.count < 0 ||
    root.count > 100 ||
    !Array.isArray(root.items)
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }
  const items = root.items.map(validateItem)
  if (root.count !== items.length) throw new Error('FOLLOWED_RESPONSE_INVALID')
  return items
}
