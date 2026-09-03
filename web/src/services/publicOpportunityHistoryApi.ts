import { apiBaseUrl, isApiMode } from './apiConfig'

export interface PublicHistoryChange {
  field: string
  before: unknown
  after: unknown
}

export interface PublicHistoryVersion {
  version: number
  observed_at: string
  change_type: 'INITIAL' | 'UPDATED'
  changed_fields: string[]
  changes: PublicHistoryChange[]
  summary: {
    project_name: unknown
    lifecycle_state: unknown
    registration_deadline: unknown
    registration_deadline_date: unknown
    bid_deadline: unknown
    budget: unknown
  }
}

export interface PublicOpportunityHistory {
  schema_version: '0.1'
  mode: 'PUBLIC_OPPORTUNITY_HISTORY'
  opportunity_id: string
  current_version: number | null
  count: number
  has_more: boolean
  versions: PublicHistoryVersion[]
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

async function responseError(response: Response): Promise<Error> {
  try {
    const root = asRecord(await response.json())
    if (root && typeof root.error === 'string') return new Error(root.error)
  } catch {
    // Fall back to status below.
  }
  return new Error(`HTTP_${response.status}`)
}

export async function getPublicOpportunityHistory(
  opportunityId: string,
): Promise<PublicOpportunityHistory | null> {
  if (!isApiMode) return null
  const response = await fetch(
    `${apiBaseUrl}/public-history/${encodeURIComponent(opportunityId)}`,
    {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    },
  )
  if (!response.ok) throw await responseError(response)
  const root = asRecord(await response.json())
  if (
    !root ||
    root.schema_version !== '0.1' ||
    root.mode !== 'PUBLIC_OPPORTUNITY_HISTORY' ||
    root.opportunity_id !== opportunityId ||
    !Number.isInteger(root.count) ||
    typeof root.has_more !== 'boolean' ||
    !Array.isArray(root.versions)
  ) {
    throw new Error('PUBLIC_HISTORY_RESPONSE_INVALID')
  }
  return root as unknown as PublicOpportunityHistory
}
