import type { Decision, TodayActionCard } from '@/types'

export class AiDecisionError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code)
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
}

export async function requestAiDecision(card: TodayActionCard): Promise<Decision> {
  const response = await fetch('/api/ai/analyze', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ opportunity_id: card.opportunity_id }),
  })

  const payload: unknown = await response.json().catch(() => null)
  const record = asRecord(payload)
  if (!response.ok) {
    const code = typeof record?.error === 'string' ? record.error : `AI_HTTP_${response.status}`
    throw new AiDecisionError(code, response.status)
  }

  const decision = asRecord(record?.decision)
  const action = typeof decision?.action === 'string' ? decision.action.trim() : ''
  const reasons = stringArray(decision?.reasons)
  const risks = stringArray(decision?.risks)
  if (!action || reasons.length === 0) {
    throw new AiDecisionError('AI_RESPONSE_INVALID', 502)
  }

  return {
    action,
    reasons,
    risks,
    needs_human_confirmation: ['执行前需要人工确认公开附件、客户资源与实际项目条件'],
  }
}
