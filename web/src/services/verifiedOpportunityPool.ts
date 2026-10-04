import { verifiedSnapshotUrl } from '@/config/snapshotConfig'
import type { AwardPriceReference, AwardLedgerEntry, NoticeSuppressedProject, TodayActionCard } from '@/types'
import type { PublicTodayActionCard, TodayActionsPublicResponse } from '@/types/public'
import { refreshLegalWindows } from '@/utils/legalWindows'
import { normalizeProjectNumber } from '@/utils/projectNumber'
import {
  backfillLocalFollowupSnapshots,
  hydrateLocalFollowups,
} from './localFollowupStore'
import { personalizeTrialCards } from './localCustomerProfile'
import { loadVerifiedSnapshotPayload } from './verifiedSnapshotClient'

const LATE_WINDOW_PERCENT = 32

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function asString(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

function numberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/,/g, '').trim())
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function normalizeBudget(value: unknown): number | null {
  const direct = numberValue(value)
  if (direct !== null) return direct
  const record = asRecord(value)
  if (!record) return null
  for (const key of ['amount', 'amount_cny', 'budget_cny', 'value']) {
    const parsed = numberValue(record[key])
    if (parsed !== null) return parsed
  }
  return null
}

function normalizeProducts(items: unknown[]): TodayActionCard['facts']['products'] {
  const result: NonNullable<TodayActionCard['facts']['products']> = []
  for (const item of items) {
    if (typeof item === 'string') {
      const name = item.trim()
      if (name) result.push({ name, category: null, quantity: null, specification: null })
      continue
    }
    const record = asRecord(item)
    if (!record) continue
    const name = asString(record.raw_name ?? record.product_name ?? record.name ?? record.item_name)
    if (!name) continue
    result.push({
      name,
      category: asString(record.category ?? record.product_category),
      quantity: asString(record.quantity ?? record.qty),
      specification: asString(record.specification ?? record.spec ?? record.model),
    })
  }
  return result.length ? result : null
}

function normalizeContact(value: unknown): TodayActionCard['facts']['official_contact'] {
  const direct = asString(value)
  if (direct) return { name: direct, title: null, phone: null, email: null }
  const record = asRecord(value)
  if (!record) return null
  const contact = {
    name: asString(record.name ?? record.contact_name),
    title: asString(record.title ?? record.role),
    phone: asString(record.phone ?? record.telephone ?? record.mobile),
    email: asString(record.email),
  }
  return Object.values(contact).some(Boolean) ? contact : null
}

function componentPercent(card: PublicTodayActionCard, code: string): number {
  const component = card.priority.components.find((item) => item.code === code)
  if (!component || component.max_points <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((component.points / component.max_points) * 100)))
}

function mapPublicCard(card: PublicTodayActionCard): TodayActionCard {
  return {
    rank: card.rank,
    opportunity_id: card.opportunity_id,
    facts: {
      project_code: card.facts.project_number,
      project_name: card.facts.project_name,
      hospital: card.facts.hospital_name,
      buyer_name: card.facts.buyer_name,
      department: card.facts.department,
      region: card.facts.region,
      market_code: card.facts.market_code ?? null,
      market_name: card.facts.market_name ?? null,
      market_admin_code: card.facts.market_admin_code ?? null,
      lifecycle_stage: card.facts.lifecycle_state,
      notice_type: card.facts.notice_type,
      publish_date: card.facts.published_at,
      registration_deadline: card.facts.registration_deadline,
      registration_deadline_date: card.facts.registration_deadline_date,
      registration_deadline_precision: card.facts.registration_deadline_precision,
      bid_deadline: card.facts.bid_deadline,
      expected_purchase_date: card.facts.expected_procurement_at,
      budget: normalizeBudget(card.facts.budget),
      procurement_method: card.facts.procurement_method,
      product_categories: card.facts.product_categories,
      products: normalizeProducts(card.facts.product_items),
      official_contact: normalizeContact(card.facts.public_contact),
      verification_status:
        card.facts.verification_status === 'VERIFIED'
          ? 'VERIFIED'
          : card.facts.verification_status === 'UNVERIFIED'
            ? 'UNVERIFIED'
            : 'PARTIAL',
      coverage_status:
        card.facts.coverage_status === 'FULL'
          ? 'FULL'
          : card.facts.coverage_status === 'NONE'
            ? 'NONE'
            : 'PARTIAL',
    },
    evidence_source_urls: [...card.evidence_source_urls],
    legal_windows: Array.isArray(card.legal_windows) ? card.legal_windows.map((item) => ({ ...item })) : null,
    official_notices: Array.isArray(card.official_notices) ? card.official_notices.map((item) => ({ ...item, packages: [...item.packages] })) : null,
    customer_context: {
      hospital_relationship: null,
      matching_product_capabilities: [],
      partnering_policy: {
        can_find_manufacturer: card.customer_context.partnering_policy.can_seek_temporary_manufacturer,
        can_partner_channel: card.customer_context.partnering_policy.can_cooperate_with_channel_partner,
        can_handle_lease: card.customer_context.partnering_policy.can_do_rental_projects,
      },
    },
    priority: {
      score: card.priority.score,
      score_scope: 'PUBLIC',
      components: {
        PRODUCT_EXECUTION_CAPABILITY: componentPercent(card, 'PRODUCT_EXECUTION_CAPABILITY'),
        RELATIONSHIP: componentPercent(card, 'RELATIONSHIP'),
        EXECUTION_FLEXIBILITY: componentPercent(card, 'EXECUTION_FLEXIBILITY'),
        INTERVENTION_STAGE: componentPercent(card, 'INTERVENTION_STAGE'),
        DEADLINE_URGENCY: componentPercent(card, 'DEADLINE_URGENCY'),
        PROJECT_AMOUNT: componentPercent(card, 'PROJECT_AMOUNT'),
        PRODUCT_SPECIFICITY: componentPercent(card, 'PRODUCT_SPECIFICITY'),
        PUBLICATION_FRESHNESS: componentPercent(card, 'PUBLICATION_FRESHNESS'),
      },
    },
    match_status: card.match_status,
    recommendation_mode: card.recommendation_mode,
    model_decision_status: card.model_decision_status,
    model_block_reason: card.model_block_reason,
    decision: card.decision
      ? {
          action: card.decision.action,
          reasons: card.decision.reasons,
          risks: card.decision.risks,
          needs_human_confirmation: card.decision.requires_human_confirmation
            ? ['执行前需要人工确认']
            : [],
        }
      : null,
    followup_status: 'NEW',
    followup_history: [],
    remind_at: null,
  }
}

function parsedTime(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

function shanghaiDateEnd(value: string | null | undefined): number | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  return parsedTime(`${value}T23:59:59+08:00`)
}

function applyRuntimeActionability(card: TodayActionCard, now: number): TodayActionCard | null {
  const bidDeadline = parsedTime(card.facts.bid_deadline)
  const registrationDeadline =
    parsedTime(card.facts.registration_deadline) ?? shanghaiDateEnd(card.facts.registration_deadline_date)
  if (bidDeadline !== null && bidDeadline <= now) return null
  if (bidDeadline === null && registrationDeadline !== null && registrationDeadline <= now) return null

  const lateWindow =
    registrationDeadline !== null &&
    registrationDeadline <= now &&
    bidDeadline !== null &&
    bidDeadline > now
  if (!lateWindow) return card

  const currentStagePercent = card.priority.components.INTERVENTION_STAGE
  const reduction = Math.max(
    0,
    Math.round(((currentStagePercent - LATE_WINDOW_PERCENT) / 100) * 25),
  )
  return {
    ...card,
    match_status: 'LATE_WINDOW',
    recommendation_mode: 'LATE_WINDOW',
    model_decision_status:
      card.model_decision_status === 'NOT_ELIGIBLE' || card.model_decision_status === 'BLOCKED_GROUNDING'
        ? card.model_decision_status
        : 'AWAITING_MODEL',
    decision: null,
    priority: {
      ...card.priority,
      score: Math.max(0, card.priority.score - reduction),
      components: {
        ...card.priority.components,
        INTERVENTION_STAGE: LATE_WINDOW_PERCENT,
      },
    },
  }
}

function rerank(cards: TodayActionCard[]): TodayActionCard[] {
  return [...cards]
    .sort((a, b) => b.priority.score - a.priority.score || a.rank - b.rank)
    .map((card, index) => ({ ...card, rank: index + 1 }))
}

async function fetchSnapshot(): Promise<TodayActionsPublicResponse> {
  const payload = await loadVerifiedSnapshotPayload(verifiedSnapshotUrl)
  const data = payload as TodayActionsPublicResponse
  if (
    data.schema_version !== '0.1' ||
    data.mode !== 'TODAY_ACTIONS' ||
    !Array.isArray(data.cards) ||
    typeof data.snapshot_as_of !== 'string' ||
    Number.isNaN(Date.parse(data.snapshot_as_of))
  ) {
    throw new Error('SNAPSHOT_RESPONSE_INVALID')
  }
  return data
}

export function refreshAwardLedger(
  entries: AwardLedgerEntry[] | null | undefined,
  now: number,
  calendar: TodayActionsPublicResponse['working_calendar'],
): AwardLedgerEntry[] {
  if (!Array.isArray(entries)) return []
  return entries.map((entry) => ({
    ...entry,
    legal_windows: refreshLegalWindows(entry.legal_windows, now, calendar),
    items: (entry.items ?? []).map((item) => ({ ...item, unit_price_cny: item.unit_price_basis === 'EXPLICIT_UNIT' ? item.unit_price_cny : null })),
  }))
}

/**
 * Published 中标/成交 results from the verified snapshot with the statutory
 * challenge windows recomputed for "now". Shared by the followups and detail
 * pages so a followed project that has since been awarded is visible as such.
 * Goes through the deduplicated snapshot client (ETag revalidation), never a
 * second download path.
 */
export async function getAwardLedger(): Promise<{
  snapshot_as_of: string
  entries: AwardLedgerEntry[]
}> {
  const data = await fetchSnapshot()
  return {
    snapshot_as_of: data.snapshot_as_of,
    entries: refreshAwardLedger(data.award_ledger, Date.now(), data.working_calendar),
  }
}

/**
 * 成交价参考 rows (brand × model × unit price from official award notices) plus
 * the device-family taxonomy they were classified with. Public snapshot data in
 * both modes; absent on older snapshots.
 */
export async function getAwardPriceReference(): Promise<{
  snapshot_as_of: string
  reference: AwardPriceReference | null
}> {
  const data = await fetchSnapshot()
  const reference = data.award_price_reference
  return {
    snapshot_as_of: data.snapshot_as_of,
    reference: reference && Array.isArray(reference.rows) && Array.isArray(reference.families)
      ? (() => {
          const rows = reference.rows.filter((row) => row.unit_price_basis === 'EXPLICIT_UNIT')
          const family_row_counts: Record<string, number> = {}
          for (const row of rows) {
            const family = row.family ?? 'OTHER'
            family_row_counts[family] = (family_row_counts[family] ?? 0) + 1
          }
          return { ...reference, rows, row_count: rows.length, family_row_counts }
        })()
      : null,
  }
}

export function findAwardForProject(
  entries: readonly AwardLedgerEntry[] | null | undefined,
  projectNumber: string | null | undefined,
  marketCode: string | null | undefined,
): AwardLedgerEntry | null {
  const key = normalizeProjectNumber(projectNumber)
  const market = String(marketCode ?? '').trim().toUpperCase()
  if (!key || !market || !Array.isArray(entries)) return null
  return entries.find((entry) => entry.market_code?.trim().toUpperCase() === market && normalizeProjectNumber(entry.project_number) === key) ?? null
}

export async function getVerifiedOpportunityPool(): Promise<{
  snapshot_as_of: string
  total: number
  cards: TodayActionCard[]
  award_ledger: AwardLedgerEntry[]
  awarded_project_count: number
  notice_suppressed_project_count: number
  notice_suppressed_projects: NoticeSuppressedProject[]
}> {
  const data = await fetchSnapshot()
  const publicCards = Array.isArray(data.opportunity_pool) ? data.opportunity_pool : data.cards
  const mapped = publicCards.map(mapPublicCard)
  backfillLocalFollowupSnapshots(mapped)
  const active = mapped
    .map((card) => applyRuntimeActionability(card, Date.now()))
    .filter((card): card is TodayActionCard => card !== null)
  const followed = hydrateLocalFollowups(rerank(active))
  const personalized = personalizeTrialCards(followed)
  return {
    award_ledger: refreshAwardLedger(data.award_ledger, Date.now(), data.working_calendar),
    awarded_project_count: data.awarded_project_count ?? 0,
    notice_suppressed_project_count: data.notice_suppressed_project_count ?? 0,
    notice_suppressed_projects: Array.isArray(data.notice_suppressed_projects)
      ? data.notice_suppressed_projects.map((item) => ({ ...item }))
      : [],
    snapshot_as_of: data.snapshot_as_of,
    total: personalized.length,
    cards: personalized,
  }
}

export async function getVerifiedPoolOpportunity(id: string): Promise<TodayActionCard | null> {
  const pool = await getVerifiedOpportunityPool()
  return pool.cards.find((item) => item.opportunity_id === id) ?? null
}
