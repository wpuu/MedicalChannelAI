import type { Decision, TodayActionCard, TodayActionsResponse } from '@/types'

const CACHE_KEY = 'medopp.grounded-ai-decisions.v1'
const MAX_CACHE_ENTRIES = 50

interface CachedDecisionEntry {
  snapshot_as_of: string
  opportunity_id: string
  cached_at: string
  decision: Decision
}

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

function readCache(): CachedDecisionEntry[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is CachedDecisionEntry => {
      const record = asRecord(item)
      return Boolean(
        record &&
          typeof record.snapshot_as_of === 'string' &&
          typeof record.opportunity_id === 'string' &&
          typeof record.cached_at === 'string' &&
          asRecord(record.decision),
      )
    })
  } catch {
    return []
  }
}

function writeCache(entries: CachedDecisionEntry[]): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(entries.slice(0, MAX_CACHE_ENTRIES)))
  } catch {
    // Cache is an optimization only. AI analysis still works when storage is unavailable.
  }
}

function getCachedDecision(opportunityId: string, snapshotAsOf: string): Decision | null {
  const entry = readCache().find(
    (item) =>
      item.opportunity_id === opportunityId && item.snapshot_as_of === snapshotAsOf,
  )
  return entry?.decision ?? null
}

function cacheDecision(
  opportunityId: string,
  snapshotAsOf: string,
  decision: Decision,
): void {
  const existing = readCache().filter(
    (item) =>
      !(
        item.opportunity_id === opportunityId &&
        item.snapshot_as_of === snapshotAsOf
      ),
  )
  writeCache([
    {
      snapshot_as_of: snapshotAsOf,
      opportunity_id: opportunityId,
      cached_at: new Date().toISOString(),
      decision,
    },
    ...existing,
  ])
}

export function hydrateCachedAiDecisions(data: TodayActionsResponse): TodayActionsResponse {
  const snapshotAsOf = data.refreshed_at
  const cached = readCache().filter((entry) => entry.snapshot_as_of === snapshotAsOf)
  if (cached.length === 0) return data
  const byId = new Map(cached.map((entry) => [entry.opportunity_id, entry.decision]))
  return {
    ...data,
    cards: data.cards.map((card) => {
      const decision = byId.get(card.opportunity_id)
      return decision
        ? {
            ...card,
            model_decision_status: 'READY',
            model_block_reason: null,
            decision,
          }
        : card
    }),
  }
}

export async function requestAiDecision(
  card: TodayActionCard,
  snapshotAsOf: string,
): Promise<Decision> {
  const cached = getCachedDecision(card.opportunity_id, snapshotAsOf)
  if (cached) return cached

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

  const rawDecision = asRecord(record?.decision)
  const action = typeof rawDecision?.action === 'string' ? rawDecision.action.trim() : ''
  const reasons = stringArray(rawDecision?.reasons)
  const risks = stringArray(rawDecision?.risks)
  if (!action || reasons.length === 0) {
    throw new AiDecisionError('AI_RESPONSE_INVALID', 502)
  }

  const decision: Decision = {
    action,
    reasons,
    risks,
    needs_human_confirmation: ['执行前需要人工确认公开附件、客户资源与实际项目条件'],
  }
  cacheDecision(card.opportunity_id, snapshotAsOf, decision)
  return decision
}
