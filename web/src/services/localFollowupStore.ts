import type { FollowupRecord, FollowupStatus, TodayActionCard } from '@/types'

const STORAGE_KEY = 'medopp.pipeline-followups.v1'
const LOCAL_REMINDER_PREFIX = 'local-reminder:'

export interface StoredPublicOpportunity {
  opportunity_id: string
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

export interface StoredFollowupEntry {
  status: FollowupStatus
  remind_at: string | null
  history: FollowupRecord[]
  public_snapshot?: StoredPublicOpportunity
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
const REMINDER_TERMINAL_STATUSES = new Set<FollowupStatus>([
  'WON',
  'LOST',
  'NOT_FIT',
  'ARCHIVED',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function asNullableString(value: unknown): string | null {
  return value === null || typeof value === 'string' ? value : null
}

function parseHistory(value: unknown): FollowupRecord[] {
  if (!Array.isArray(value)) return []
  const records: FollowupRecord[] = []
  for (const item of value) {
    const row = asRecord(item)
    if (!row) continue
    const status = row.status
    if (typeof status !== 'string' || !FOLLOWUP_STATUSES.has(status as FollowupStatus)) continue
    if (typeof row.id !== 'string' || typeof row.at !== 'string' || typeof row.actor !== 'string') continue
    records.push({
      id: row.id,
      status: status as FollowupStatus,
      note: typeof row.note === 'string' ? row.note : undefined,
      reason: typeof row.reason === 'string' ? row.reason : undefined,
      remind_at: typeof row.remind_at === 'string' ? row.remind_at : undefined,
      at: row.at,
      actor: row.actor,
    })
  }
  return records
}

function parsePublicSnapshot(value: unknown): StoredPublicOpportunity | undefined {
  const row = asRecord(value)
  const facts = asRecord(row?.facts)
  if (!row || !facts || typeof row.opportunity_id !== 'string' || !Array.isArray(row.evidence_source_urls)) {
    return undefined
  }
  if (row.evidence_source_urls.some((item) => typeof item !== 'string')) return undefined

  const budgetValue = facts.budget_cny
  const budget =
    budgetValue === null || (typeof budgetValue === 'number' && Number.isFinite(budgetValue))
      ? budgetValue
      : null

  return {
    opportunity_id: row.opportunity_id,
    facts: {
      project_number: asNullableString(facts.project_number),
      project_name: asNullableString(facts.project_name),
      buyer_name: asNullableString(facts.buyer_name),
      hospital_name: asNullableString(facts.hospital_name),
      department: asNullableString(facts.department),
      lifecycle_state: asNullableString(facts.lifecycle_state),
      published_at: asNullableString(facts.published_at),
      bid_deadline: asNullableString(facts.bid_deadline),
      expected_procurement_at: asNullableString(facts.expected_procurement_at),
      budget_cny: budget,
    },
    evidence_source_urls: [...row.evidence_source_urls] as string[],
  }
}

export function readLocalFollowups(): Record<string, StoredFollowupEntry> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = asRecord(JSON.parse(raw))
    if (!parsed) return {}

    const result: Record<string, StoredFollowupEntry> = {}
    for (const [opportunityId, value] of Object.entries(parsed)) {
      const row = asRecord(value)
      if (!row || typeof row.status !== 'string') continue
      if (!FOLLOWUP_STATUSES.has(row.status as FollowupStatus)) continue
      result[opportunityId] = {
        status: row.status as FollowupStatus,
        remind_at: asNullableString(row.remind_at),
        history: parseHistory(row.history),
        public_snapshot: parsePublicSnapshot(row.public_snapshot),
      }
    }
    return result
  } catch {
    return {}
  }
}

function writeLocalFollowups(entries: Record<string, StoredFollowupEntry>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // Trial persistence is best-effort. The current in-memory interaction still works.
  }
}

function toStoredPublicOpportunity(card: TodayActionCard): StoredPublicOpportunity {
  return {
    opportunity_id: card.opportunity_id,
    facts: {
      project_number: card.facts.project_code,
      project_name: card.facts.project_name,
      buyer_name: card.facts.buyer_name ?? null,
      hospital_name: card.facts.hospital,
      department: card.facts.department,
      lifecycle_state: card.facts.lifecycle_stage,
      published_at: card.facts.publish_date,
      bid_deadline: card.facts.bid_deadline,
      expected_procurement_at: card.facts.expected_purchase_date,
      budget_cny: card.facts.budget,
    },
    evidence_source_urls: [...card.evidence_source_urls],
  }
}

export function hydrateLocalFollowups(cards: TodayActionCard[]): TodayActionCard[] {
  const stored = readLocalFollowups()
  return cards.map((card) => {
    const saved = stored[card.opportunity_id]
    return saved
      ? {
          ...card,
          followup_status: saved.status,
          remind_at: saved.remind_at,
          followup_history: saved.history,
        }
      : card
  })
}

export function backfillLocalFollowupSnapshots(cards: TodayActionCard[]): void {
  const stored = readLocalFollowups()
  let changed = false
  for (const card of cards) {
    const saved = stored[card.opportunity_id]
    if (!saved || saved.public_snapshot) continue
    stored[card.opportunity_id] = {
      ...saved,
      public_snapshot: toStoredPublicOpportunity(card),
    }
    changed = true
  }
  if (changed) writeLocalFollowups(stored)
}

export function persistLocalFollowup(card: TodayActionCard): void {
  const stored = readLocalFollowups()
  const existing = stored[card.opportunity_id]
  const remindAt = REMINDER_TERMINAL_STATUSES.has(card.followup_status)
    ? null
    : card.remind_at ?? existing?.remind_at ?? null
  stored[card.opportunity_id] = {
    status: card.followup_status,
    remind_at: remindAt,
    history: card.followup_history,
    public_snapshot: toStoredPublicOpportunity(card),
  }
  writeLocalFollowups(stored)
}

export function listStoredFollowups(): Array<{
  opportunity_id: string
  entry: StoredFollowupEntry
}> {
  return Object.entries(readLocalFollowups())
    .filter(([, entry]) => entry.status !== 'NEW' || Boolean(entry.remind_at))
    .map(([opportunity_id, entry]) => ({ opportunity_id, entry }))
}

export function getStoredHistoricalOpportunityCard(opportunityId: string): TodayActionCard | null {
  const entry = readLocalFollowups()[opportunityId]
  const snapshot = entry?.public_snapshot
  if (!entry || !snapshot) return null

  return {
    rank: 0,
    opportunity_id: snapshot.opportunity_id,
    facts: {
      project_code: snapshot.facts.project_number,
      project_name: snapshot.facts.project_name,
      hospital: snapshot.facts.hospital_name,
      buyer_name: snapshot.facts.buyer_name,
      department: snapshot.facts.department,
      region: null,
      lifecycle_stage: snapshot.facts.lifecycle_state,
      notice_type: null,
      publish_date: snapshot.facts.published_at,
      registration_deadline: null,
      bid_deadline: snapshot.facts.bid_deadline,
      expected_purchase_date: snapshot.facts.expected_procurement_at,
      budget: snapshot.facts.budget_cny,
      procurement_method: null,
      product_categories: [],
      products: null,
      official_contact: null,
      verification_status: 'VERIFIED',
      coverage_status: 'PARTIAL',
    },
    evidence_source_urls: [...snapshot.evidence_source_urls],
    customer_context: {
      hospital_relationship: null,
      matching_product_capabilities: [],
      partnering_policy: {
        can_find_manufacturer: null,
        can_partner_channel: null,
        can_handle_lease: null,
      },
    },
    priority: {
      score: 0,
      components: {
        PRODUCT_EXECUTION_CAPABILITY: 0,
        RELATIONSHIP: 0,
        INTERVENTION_STAGE: 0,
        PROJECT_AMOUNT: 0,
      },
    },
    match_status: 'ARCHIVE',
    recommendation_mode: 'ARCHIVE',
    model_decision_status: 'NOT_ELIGIBLE',
    model_block_reason: '该商机已不在当前有效商机池中，仅保留历史公开事实与跟进记录。',
    decision: null,
    followup_status: entry.status,
    followup_history: entry.history,
    remind_at: entry.remind_at,
  }
}

export function localReminderId(opportunityId: string): string {
  return `${LOCAL_REMINDER_PREFIX}${opportunityId}`
}

export function opportunityIdFromLocalReminderId(reminderId: string): string | null {
  return reminderId.startsWith(LOCAL_REMINDER_PREFIX)
    ? reminderId.slice(LOCAL_REMINDER_PREFIX.length) || null
    : null
}

export function clearLocalReminder(opportunityId: string): void {
  const stored = readLocalFollowups()
  const entry = stored[opportunityId]
  if (!entry) return
  stored[opportunityId] = {
    ...entry,
    remind_at: null,
  }
  writeLocalFollowups(stored)
}

export function resetLocalFollowups(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Best effort only.
  }
}
