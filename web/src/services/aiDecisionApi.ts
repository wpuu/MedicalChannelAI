import type { Decision, TodayActionCard } from '@/types'

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

function normalizeDecision(value: unknown): Decision | null {
  const record = asRecord(value)
  if (!record) return null
  const action = typeof record.action === 'string' ? record.action.trim() : ''
  const reasons = stringArray(record.reasons)
  const risks = stringArray(record.risks)
  const confirmations = stringArray(record.needs_human_confirmation)
  if (!action || reasons.length === 0) return null
  return {
    action,
    reasons,
    risks,
    needs_human_confirmation:
      confirmations.length > 0
        ? confirmations
        : ['执行前需要人工确认公开附件、客户资源与实际项目条件'],
  }
}

function readCache(): CachedDecisionEntry[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const entries: CachedDecisionEntry[] = []
    for (const item of parsed) {
      const record = asRecord(item)
      if (
        !record ||
        typeof record.snapshot_as_of !== 'string' ||
        typeof record.opportunity_id !== 'string' ||
        typeof record.cached_at !== 'string'
      ) {
        continue
      }
      const decision = normalizeDecision(record.decision)
      if (!decision) continue
      entries.push({
        snapshot_as_of: record.snapshot_as_of,
        opportunity_id: record.opportunity_id,
        cached_at: record.cached_at,
        decision,
      })
    }
    return entries
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

async function getSnapshotAsOf(): Promise<string | null> {
  try {
    const response = await fetch('/data/today-actions.public.json', {
      headers: { Accept: 'application/json' },
      cache: 'no-cache',
    })
    if (!response.ok) return null
    const payload: unknown = await response.json()
    const record = asRecord(payload)
    const value = record?.snapshot_as_of
    return typeof value === 'string' && !Number.isNaN(Date.parse(value)) ? value : null
  } catch {
    return null
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

export async function requestAiDecision(card: TodayActionCard): Promise<Decision> {
  const snapshotAsOf = await getSnapshotAsOf()
  if (snapshotAsOf) {
    const cached = getCachedDecision(card.opportunity_id, snapshotAsOf)
    if (cached) return cached
  }

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

  const decision = normalizeDecision(record?.decision)
  if (!decision) {
    throw new AiDecisionError('AI_RESPONSE_INVALID', 502)
  }

  if (snapshotAsOf) {
    cacheDecision(card.opportunity_id, snapshotAsOf, decision)
  }
  return decision
}
