import { apiBaseUrl, isApiMode } from './apiConfig'
import {
  getOpportunityFeedback,
  setOpportunityFeedback,
  type OpportunityFeedback,
} from './opportunityFeedbackStore'

const FEEDBACK_VALUES = new Set<OpportunityFeedback>([
  'ALREADY_KNOWN',
  'NEW_NOT_VALUABLE',
  'NEW_WORTH_FOLLOWING',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function parseValue(payload: unknown, opportunityId: string): OpportunityFeedback | null {
  const root = asRecord(payload)
  if (
    !root ||
    root.schema_version !== '0.1' ||
    root.opportunity_id !== opportunityId ||
    !(root.value === null || (typeof root.value === 'string' && FEEDBACK_VALUES.has(root.value as OpportunityFeedback)))
  ) {
    throw new Error('FEEDBACK_RESPONSE_INVALID')
  }
  return root.value as OpportunityFeedback | null
}

export async function loadRecommendationFeedback(opportunityId: string): Promise<OpportunityFeedback | null> {
  if (!isApiMode) return getOpportunityFeedback(opportunityId)
  const response = await fetch(`${apiBaseUrl}/feedback/${encodeURIComponent(opportunityId)}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
  return parseValue(await response.json(), opportunityId)
}

export async function saveRecommendationFeedback(
  opportunityId: string,
  value: OpportunityFeedback | null,
): Promise<OpportunityFeedback | null> {
  if (!isApiMode) {
    setOpportunityFeedback(opportunityId, value)
    return value
  }
  const response = await fetch(`${apiBaseUrl}/feedback/${encodeURIComponent(opportunityId)}`, {
    method: value === null ? 'DELETE' : 'PUT',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(value === null ? {} : { 'Content-Type': 'application/json' }),
    },
    ...(value === null ? {} : { body: JSON.stringify({ value }) }),
  })
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
  return parseValue(await response.json(), opportunityId)
}
