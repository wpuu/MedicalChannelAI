import type { Facts, FollowupRecord, FollowupStatus, TodayActionCard } from '@/types'

export const TRIAL_FOLLOWUP_STORAGE_KEY = 'medopp.pipeline-followups.v1'

export interface StoredTrialOpportunitySnapshot {
  rank: number
  facts: Facts
  evidence_source_urls: string[]
}

export interface StoredTrialFollowup {
  opportunity_id: string
  status: FollowupStatus
  remind_at: string | null
  history: FollowupRecord[]
  snapshot: StoredTrialOpportunitySnapshot | null
}

const FOLLOWUP_STATUSES = new Set<FollowupStatus>([
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
  'ARCHIVED',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function isFollowupStatus(value: unknown): value is FollowupStatus {
  return typeof value === 'string' && FOLLOWUP_STATUSES.has(value as FollowupStatus)
}

function normalizeHistory(value: unknown): FollowupRecord[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is FollowupRecord => {
    const row = asRecord(item)
    return Boolean(
      row &&
        typeof row.id === 'string' &&
        isFollowupStatus(row.status) &&
        typeof row.at === 'string' &&
        typeof row.actor === 'string',
    )
  })
}

function normalizeSnapshot(value: unknown): StoredTrialOpportunitySnapshot | null {
  const row = asRecord(value)
  if (!row || typeof row.rank !== 'number' || !Number.isFinite(row.rank)) return null
  const facts = asRecord(row.facts)
  if (!facts || !Array.isArray(row.evidence_source_urls)) return null
  if (row.evidence_source_urls.some((item) => typeof item !== 'string')) return null
  return {
    rank: row.rank,
    facts: row.facts as Facts,
    evidence_source_urls: [...row.evidence_source_urls] as string[],
  }
}

export function readTrialFollowups(): Record<string, StoredTrialFollowup> {
  try {
    const raw = localStorage.getItem(TRIAL_FOLLOWUP_STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    const root = asRecord(parsed)
    if (!root) return {}

    const result: Record<string, StoredTrialFollowup> = {}
    for (const [opportunityId, value] of Object.entries(root)) {
      const row = asRecord(value)
      if (!row || !isFollowupStatus(row.status)) continue
      result[opportunityId] = {
        opportunity_id: opportunityId,
        status: row.status,
        remind_at: typeof row.remind_at === 'string' ? row.remind_at : null,
        history: normalizeHistory(row.history),
        snapshot: normalizeSnapshot(row.snapshot),
      }
    }
    return result
  } catch {
    return {}
  }
}

function writeTrialFollowups(store: Record<string, StoredTrialFollowup>): void {
  try {
    localStorage.setItem(TRIAL_FOLLOWUP_STORAGE_KEY, JSON.stringify(store))
  } catch {
    // Browser storage is optional; the in-memory trial still remains usable.
  }
}

export function hydrateTrialFollowups(cards: TodayActionCard[]): TodayActionCard[] {
  const stored = readTrialFollowups()
  return cards.map((card) => {
    const saved = stored[card.opportunity_id]
    if (!saved) return card
    return {
      ...card,
      followup_status: saved.status,
      remind_at: saved.remind_at,
      followup_history: saved.history,
    }
  })
}

export function persistTrialFollowupCards(cards: TodayActionCard[]): void {
  const stored = readTrialFollowups()
  const currentIds = new Set(cards.map((card) => card.opportunity_id))

  for (const card of cards) {
    if (card.followup_status === 'NEW') {
      delete stored[card.opportunity_id]
      continue
    }
    stored[card.opportunity_id] = {
      opportunity_id: card.opportunity_id,
      status: card.followup_status,
      remind_at: card.remind_at,
      history: card.followup_history,
      snapshot: {
        rank: card.rank,
        facts: card.facts,
        evidence_source_urls: [...card.evidence_source_urls],
      },
    }
  }

  // Entries absent from today's feed are intentionally retained. They are the
  // user's follow-up history and must survive Top5/snapshot churn.
  for (const [opportunityId, entry] of Object.entries(stored)) {
    if (!currentIds.has(opportunityId) && entry.status === 'NEW') {
      delete stored[opportunityId]
    }
  }

  writeTrialFollowups(stored)
}

export function listStoredTrialFollowups(): StoredTrialFollowup[] {
  return Object.values(readTrialFollowups()).filter(
    (entry) => entry.status !== 'NEW' && entry.snapshot !== null,
  )
}
