import type { OutreachDraft, TodayActionsResponse } from '@/types'
import { ApiTodayActionsService } from './ApiTodayActionsService'

interface ServerOutreachDraft {
  schema_version: '0.1'
  opportunity_id: string
  disclaimer: string
  generated_at: string
  draft: string
  strategy_code: string
  supporting_fact_ids: string[]
  supporting_profile_paths: string[]
  requires_human_confirmation: true
  cached?: boolean
}

const FORBIDDEN_KEYS = new Set([
  'tenant_id',
  'profile_id',
  'model_input',
  'provider',
  'api_key',
  'upstream_model',
  'lease_id',
  'task_id',
  'completion_nonce',
])

const TODAY_POLL_DELAYS_MS = [1000, 1500, 2000, 2500] as const

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function hasPendingDecision(data: TodayActionsResponse): boolean {
  return data.model_request_count > 0 ||
    data.cards.some((card) => card.model_decision_status === 'AWAITING_MODEL')
}

function assertSafeOutreach(value: unknown, path = '$'): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertSafeOutreach(item, `${path}[${index}]`))
    return
  }
  if (value === null || typeof value !== 'object') return
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (FORBIDDEN_KEYS.has(key.toLowerCase())) {
      throw new Error(`OUTREACH_INTERNAL_FIELD:${path}.${key}`)
    }
    assertSafeOutreach(child, `${path}.${key}`)
  }
}

function validateOutreach(payload: unknown, opportunityId: string): ServerOutreachDraft {
  assertSafeOutreach(payload)
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('OUTREACH_RESPONSE_INVALID')
  }
  const value = payload as Partial<ServerOutreachDraft>
  if (
    value.schema_version !== '0.1' ||
    value.opportunity_id !== opportunityId ||
    typeof value.disclaimer !== 'string' ||
    !value.disclaimer.trim() ||
    typeof value.generated_at !== 'string' ||
    !value.generated_at.trim() ||
    typeof value.draft !== 'string' ||
    !value.draft.trim() ||
    typeof value.strategy_code !== 'string' ||
    !Array.isArray(value.supporting_fact_ids) ||
    !Array.isArray(value.supporting_profile_paths) ||
    value.requires_human_confirmation !== true
  ) {
    throw new Error('OUTREACH_RESPONSE_INVALID')
  }
  return value as ServerOutreachDraft
}

export class GroundedApiTodayActionsService extends ApiTodayActionsService {
  private readonly outreachBaseUrl: string

  constructor(baseUrl: string) {
    super(baseUrl)
    this.outreachBaseUrl = baseUrl.replace(/\/+$/, '')
  }

  override async getTodayActions(): Promise<TodayActionsResponse> {
    let data = await super.getTodayActions()
    for (const delay of TODAY_POLL_DELAYS_MS) {
      if (!hasPendingDecision(data)) return data
      await sleep(delay)
      data = await super.getTodayActions()
    }
    return data
  }

  override async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    const response = await fetch(
      `${this.outreachBaseUrl}/outreach/${encodeURIComponent(id)}`,
      {
        method: 'POST',
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: '{}',
      },
    )
    if (!response.ok) throw new Error(`HTTP_${response.status}`)
    const payload = validateOutreach(await response.json(), id)
    return {
      opportunity_id: payload.opportunity_id,
      disclaimer: payload.disclaimer,
      generated_at: payload.generated_at,
      draft: payload.draft,
    }
  }
}
