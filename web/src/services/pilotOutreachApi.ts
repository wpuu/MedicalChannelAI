import type { OutreachDraft } from '@/types'
import { apiBaseUrl, isApiMode } from './apiConfig'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export async function requestPilotOutreachDraft(opportunityId: string): Promise<OutreachDraft> {
  if (!isApiMode) throw new Error('API_MODE_REQUIRED')
  const response = await fetch(`${apiBaseUrl}/ai/analyze?route=outreach`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ opportunity_id: opportunityId }),
  })

  const payload = asRecord(await response.json().catch(() => null))
  if (!response.ok) {
    const error = typeof payload?.error === 'string' ? payload.error : `HTTP_${response.status}`
    throw new Error(error)
  }

  if (
    !payload ||
    typeof payload.opportunity_id !== 'string' ||
    typeof payload.generated_at !== 'string' ||
    typeof payload.draft !== 'string' ||
    typeof payload.disclaimer !== 'string'
  ) {
    throw new Error('OUTREACH_RESPONSE_INVALID')
  }

  return {
    opportunity_id: payload.opportunity_id,
    generated_at: payload.generated_at,
    draft: payload.draft,
    disclaimer: payload.disclaimer,
  }
}
