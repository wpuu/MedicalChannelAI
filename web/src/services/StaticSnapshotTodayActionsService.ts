import type {
  FollowupInput,
  FollowupRecord,
  OutreachDraft,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'
import type { PublicTodayActionCard, TodayActionsPublicResponse } from '@/types/public'
import {
  backfillLocalFollowupSnapshots,
  hydrateLocalFollowups,
  persistLocalFollowup,
} from './localFollowupStore'
import { personalizeTrialCards } from './localCustomerProfile'
import type { TodayActionsService } from './TodayActionsService'
import { loadVerifiedSnapshotPayload } from './verifiedSnapshotClient'
import { refreshLegalWindows } from '@/utils/legalWindows'
import { refreshAwardLedger } from './verifiedOpportunityPool'

const COVERAGE_WARNING = '当前业务地区 · 公开事实来自证据流水线快照；各地区仍为部分来源覆盖。'
const INTERVENTION_MAX_POINTS = 25
const LATE_WINDOW_POINTS = 8
const LATE_WINDOW_PERCENT = Math.round((LATE_WINDOW_POINTS / INTERVENTION_MAX_POINTS) * 100)
const MAX_TODAY_CARDS = 5

const FORBIDDEN_PUBLIC_KEYS = new Set([
  'model_requests',
  'model_input',
  'task_payloads',
  'agnes_dispatch_plan',
  'lease',
  'lease_id',
  'provider',
  'api_key',
  'upstream_model',
  'completion_nonce',
  'task_id',
])

const FORBIDDEN_PUBLIC_PREFIXES = [
  'model_input_',
  'agnes_dispatch_',
  'provider_',
  'lease_',
  'api_key_',
  'upstream_model_',
]

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function assertNoInternalFields(value: unknown, path = '$'): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoInternalFields(item, `${path}[${index}]`))
    return
  }
  const record = asRecord(value)
  if (!record) return
  for (const [key, child] of Object.entries(record)) {
    const normalized = key.toLowerCase()
    if (
      FORBIDDEN_PUBLIC_KEYS.has(normalized) ||
      FORBIDDEN_PUBLIC_PREFIXES.some((prefix) => normalized.startsWith(prefix))
    ) {
      throw new Error(`PUBLIC_VIEW_INTERNAL_FIELD:${path}.${key}`)
    }
    assertNoInternalFields(child, `${path}.${key}`)
  }
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
      quality_flags: card.facts.quality_flags ?? [],
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
    evidence_source_urls: card.evidence_source_urls,
    legal_windows: Array.isArray(card.legal_windows) ? card.legal_windows.map((item) => ({ ...item })) : null,
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

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function splitContactNames(value: string | null | undefined): string[] {
  if (!value) return []
  return value
    .split(/[、，,；;／/]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function outreachGreeting(contact: string | null | undefined): string {
  const names = splitContactNames(contact)
  if (names.length >= 2) return '各位老师好：'
  if (names.length === 1) return `${names[0]}老师，您好：`
  return '您好：'
}

function chineseDateTime(value: string | null | undefined): string | null {
  if (!value) return null
  const match = value.match(/^(20\d{2})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (!match) return value
  return `${match[1]}年${Number(match[2])}月${Number(match[3])}日 ${match[4]}:${match[5]}`
}

function chineseDate(value: string | null | undefined): string | null {
  if (!value) return null
  const match = value.match(/^(20\d{2})-(\d{2})-(\d{2})$/)
  if (!match) return value
  return `${match[1]}年${Number(match[2])}月${Number(match[3])}日`
}

function isMarketResearchCard(card: TodayActionCard): boolean {
  const text = `${card.facts.lifecycle_stage ?? ''}|${card.facts.notice_type ?? ''}|${card.facts.project_name ?? ''}`
  return /MARKET_RESEARCH|调研|需求调查|需求征集|意向征集/.test(text)
}

function buildGroundedDraft(card: TodayActionCard): string {
  const project = card.facts.project_name ?? '相关项目'
  const greeting = outreachGreeting(card.facts.official_contact?.name)
  const registration = chineseDateTime(card.facts.registration_deadline)
  const registrationDate = chineseDate(card.facts.registration_deadline_date)
  const bid = chineseDateTime(card.facts.bid_deadline)
  const marketResearch = isMarketResearchCard(card)
  const facts = [
    card.facts.budget ? `项目预算约${Math.round(card.facts.budget / 10000)}万元` : null,
    registration
      ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截至${registration}`
      : registrationDate
        ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截止日期为${registrationDate}（官方未公布具体时间）`
        : null,
    bid ? `投标/响应截止${bid}` : null,
  ].filter((item): item is string => Boolean(item))

  const closing =
    card.recommendation_mode === 'LATE_WINDOW'
      ? '注意到前期报名或文件获取时间已过，想确认后续是否还有公开答疑或合规的资料对接窗口；如无，我们将按公告安排关注后续进展。'
      : marketResearch
        ? '想确认目前是否仍接受产品资料、技术交流或需求反馈；如方便，我们可以按公开要求准备相关资料。'
        : '想确认目前是否还有公开答疑、技术交流或资料对接窗口；如方便，我们可以按项目要求准备相关资料。'

  return [
    greeting,
    '',
    `关注到「${project}」的公开${marketResearch ? '调研' : '采购'}信息。`,
    facts.length ? `公开信息显示，${facts.join('，')}。` : '目前可核验的公开信息有限。',
    '',
    closing,
  ].join('\n')
}

function parsedTime(value: string | null): number | null {
  if (!value) return null
  const time = Date.parse(value)
  return Number.isNaN(time) ? null : time
}

function tianjinDateKey(now: number): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(now))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function validDateOnly(value: string | null | undefined): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  ) {
    return null
  }
  return value
}

function interventionPointsFromPercent(value: number): number {
  return Math.max(0, Math.round((value / 100) * INTERVENTION_MAX_POINTS))
}

function archivedRuntimeCard(card: TodayActionCard): TodayActionCard {
  const currentStagePoints = interventionPointsFromPercent(
    card.priority.components.INTERVENTION_STAGE,
  )
  return {
    ...card,
    match_status: 'ARCHIVE',
    recommendation_mode: 'ARCHIVE',
    model_decision_status: 'NOT_ELIGIBLE',
    model_block_reason: '公开截止时间已过，当前仅保留事实与历史跟进记录。',
    decision: null,
    priority: {
      ...card.priority,
      score: Math.max(0, card.priority.score - currentStagePoints),
      components: {
        ...card.priority.components,
        INTERVENTION_STAGE: 0,
      },
    },
  }
}

function applyRuntimeActionability(
  card: TodayActionCard,
  now: number,
  includeInactive: boolean,
): TodayActionCard | null {
  const bidDeadline = parsedTime(card.facts.bid_deadline)
  const registrationDeadline = parsedTime(card.facts.registration_deadline)
  const registrationDeadlineDate = validDateOnly(card.facts.registration_deadline_date)
  const localDate = tianjinDateKey(now)
  const bidClosed = bidDeadline !== null && bidDeadline <= now
  const registrationOnlyClosed =
    bidDeadline === null &&
    ((registrationDeadline !== null && registrationDeadline <= now) ||
      (registrationDeadline === null &&
        registrationDeadlineDate !== null &&
        registrationDeadlineDate < localDate))

  if (bidClosed || registrationOnlyClosed) {
    return includeInactive ? archivedRuntimeCard(card) : null
  }

  const lateWindow =
    bidDeadline !== null &&
    bidDeadline > now &&
    ((registrationDeadline !== null && registrationDeadline <= now) ||
      (registrationDeadline === null &&
        registrationDeadlineDate !== null &&
        registrationDeadlineDate < localDate))
  if (!lateWindow) return { ...card }

  const currentStagePoints = interventionPointsFromPercent(
    card.priority.components.INTERVENTION_STAGE,
  )
  const stagePointReduction = Math.max(0, currentStagePoints - LATE_WINDOW_POINTS)
  return {
    ...card,
    match_status: 'LATE_WINDOW',
    recommendation_mode: 'LATE_WINDOW',
    model_decision_status:
      card.model_decision_status === 'NOT_ELIGIBLE' ||
      card.model_decision_status === 'BLOCKED_GROUNDING'
        ? card.model_decision_status
        : 'AWAITING_MODEL',
    decision: null,
    priority: {
      ...card.priority,
      score: Math.max(0, card.priority.score - stagePointReduction),
      components: {
        ...card.priority.components,
        INTERVENTION_STAGE: LATE_WINDOW_PERCENT,
      },
    },
  }
}

function freshnessWarning(snapshotAsOf: string, now: number): string {
  const snapshotTime = Date.parse(snapshotAsOf)
  if (Number.isNaN(snapshotTime)) return COVERAGE_WARNING
  const ageHours = Math.max(0, (now - snapshotTime) / 3_600_000)
  if (ageHours >= 72) {
    return `${COVERAGE_WARNING} 当前快照已超过72小时未更新，可能遗漏新项目；页面会自动排除已过截止日期的旧项目，但新增商机请以官方来源为准。`
  }
  if (ageHours >= 24) {
    return `${COVERAGE_WARNING} 当前快照已超过24小时未更新，可能遗漏新项目；已过截止日期的项目会在浏览器端自动降级或移出今日行动。`
  }
  return COVERAGE_WARNING
}

function rerank(cards: TodayActionCard[]): TodayActionCard[] {
  return [...cards]
    .sort((a, b) => b.priority.score - a.priority.score || a.rank - b.rank)
    .map((card, index) => ({ ...card, rank: index + 1 }))
}

export class StaticSnapshotTodayActionsService implements TodayActionsService {
  private snapshot: TodayActionsResponse | null = null

  constructor(private readonly snapshotUrl: string) {}

  private derivePool(
    data: TodayActionsResponse,
    includeInactive = false,
  ): TodayActionCard[] {
    const now = Date.now()
    const publicPool = data.opportunity_pool?.length ? data.opportunity_pool : data.cards
    const runtimeCards = publicPool
      .map((card) => applyRuntimeActionability(card, now, includeInactive))
      .filter((card): card is TodayActionCard => card !== null)
      .map((card) => ({
        ...card,
        legal_windows: refreshLegalWindows(card.legal_windows, now, data.working_calendar),
      }))
    const followedCards = hydrateLocalFollowups(rerank(runtimeCards))
    return personalizeTrialCards(followedCards)
  }

  private deriveLocalState(
    data: TodayActionsResponse,
    includeInactive = false,
  ): TodayActionsResponse {
    const now = Date.now()
    const pool = this.derivePool(data, includeInactive)
    const todayCards = includeInactive ? pool : pool.slice(0, MAX_TODAY_CARDS)
    return {
      ...data,
      matched_count: includeInactive ? data.matched_count : pool.length,
      card_count: todayCards.length,
      opportunity_pool_count: pool.length,
      coverage_warning: freshnessWarning(data.refreshed_at, now),
      cards: todayCards,
      opportunity_pool: pool,
    }
  }

  private async ensureLoaded(): Promise<TodayActionsResponse> {
    if (this.snapshot) return this.snapshot
    const payload = await loadVerifiedSnapshotPayload(this.snapshotUrl)
    assertNoInternalFields(payload)
    const data = payload as TodayActionsPublicResponse
    if (
      data.schema_version !== '0.1' ||
      data.mode !== 'TODAY_ACTIONS' ||
      !Array.isArray(data.cards) ||
      (data.opportunity_pool !== undefined && !Array.isArray(data.opportunity_pool)) ||
      typeof data.snapshot_as_of !== 'string' ||
      Number.isNaN(Date.parse(data.snapshot_as_of))
    ) {
      throw new Error('SNAPSHOT_RESPONSE_INVALID')
    }

    const mappedCards = data.cards.map(mapPublicCard)
    const mappedPool = (data.opportunity_pool ?? data.cards).map(mapPublicCard)
    backfillLocalFollowupSnapshots(mappedPool)

    this.snapshot = {
      schema_version: data.schema_version,
      mode: data.mode,
      input_candidate_count: data.input_candidate_count,
      matched_count: data.matched_count,
      card_count: data.card_count,
      opportunity_pool_count: data.opportunity_pool_count ?? mappedPool.length,
      model_request_count: data.model_request_count,
      coverage_warning: COVERAGE_WARNING,
      generated_at: data.snapshot_as_of,
      refreshed_at: data.snapshot_as_of,
      working_calendar: data.working_calendar ?? null,
      awarded_project_count: data.awarded_project_count ?? 0,
      award_ledger: refreshAwardLedger(data.award_ledger, Date.now(), data.working_calendar),
      cards: mappedCards,
      opportunity_pool: mappedPool,
      model_requests: [],
    }
    return this.snapshot
  }

  async getTodayActions(): Promise<TodayActionsResponse> {
    return structuredClone(this.deriveLocalState(await this.ensureLoaded()))
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    const data = this.deriveLocalState(await this.ensureLoaded(), true)
    const card = (data.opportunity_pool ?? data.cards).find((item) => item.opportunity_id === id)
    return card ? structuredClone(card) : null
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    const data = this.deriveLocalState(await this.ensureLoaded(), true)
    const card = (data.opportunity_pool ?? data.cards).find((item) => item.opportunity_id === id)
    if (!card) throw new Error('未找到对应商机')
    const record: FollowupRecord = {
      id: uid('fu'),
      status: input.status,
      note: input.note,
      reason: input.reason,
      remind_at: input.remind_at,
      at: new Date().toISOString(),
      actor: '当前用户',
    }
    card.followup_status = input.status
    card.remind_at = input.remind_at ?? (input.status === 'MONITOR' ? card.remind_at : null)
    card.followup_history = [record, ...card.followup_history]
    persistLocalFollowup(card)
  }

  async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    const card = await this.getOpportunity(id)
    if (!card || !card.evidence_source_urls.length || card.model_decision_status === 'NOT_ELIGIBLE') {
      throw new Error('OUTREACH_GROUNDING_INSUFFICIENT')
    }
    return {
      opportunity_id: id,
      generated_at: new Date().toISOString(),
      draft: buildGroundedDraft(card),
      disclaimer: '发送前请核对公开信息与实际情况；未推断医院关系、厂家授权或中标概率。',
    }
  }
}