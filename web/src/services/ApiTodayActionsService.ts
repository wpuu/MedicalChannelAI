import type {
  CapabilityType,
  FollowupInput,
  FollowupRecord,
  FollowupStatus,
  NotFitReason,
  OutreachDraft,
  RelationshipStrength,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'
import type {
  PublicProductCapability,
  PublicTodayActionCard,
  TodayActionsPublicResponse,
} from '@/types/public'
import type { TodayActionsService } from './TodayActionsService'

const COVERAGE_WARNING = '当前处于天津 Pilot 阶段，公开数据覆盖持续扩展中。'

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

const NOT_FIT_REASON_TO_CODE: Record<NotFitReason, string> = {
  没有对应产品: 'NO_PRODUCT_CAPABILITY',
  暂无厂家资源: 'NO_MANUFACTURER_ACCESS',
  医院关系太弱: 'RELATIONSHIP_TOO_WEAK',
  项目金额太小: 'AMOUNT_TOO_SMALL',
  介入时间太晚: 'PROJECT_TOO_LATE',
  判断竞争对手已锁定: 'COMPETITOR_LOCKED_CUSTOMER_JUDGMENT',
  科室不匹配: 'DEPARTMENT_OUT_OF_SCOPE',
  区域不匹配: 'REGION_OUT_OF_SCOPE',
  不做租赁项目: 'RENTAL_NOT_SUPPORTED',
  其他: 'OTHER',
}

const CODE_TO_NOT_FIT_REASON = new Map<string, NotFitReason>(
  Object.entries(NOT_FIT_REASON_TO_CODE).map(([label, code]) => [code, label as NotFitReason]),
)

interface ServerFollowupRecord {
  id: string
  status: FollowupStatus
  note: string | null
  reason: string | null
  remind_at: string | null
  at: string
  actor: string
}

interface ServerFollowupState {
  schema_version: '0.1'
  opportunity_id: string
  current_status: FollowupStatus
  remind_at: string | null
  history: ServerFollowupRecord[]
  profile_learning: unknown
  mutation_inserted?: boolean
}

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
    const blocked =
      FORBIDDEN_PUBLIC_KEYS.has(normalized) ||
      FORBIDDEN_PUBLIC_PREFIXES.some((prefix) => normalized.startsWith(prefix))
    if (blocked) {
      throw new Error(`PUBLIC_VIEW_INTERNAL_FIELD:${path}.${key}`)
    }
    assertNoInternalFields(child, `${path}.${key}`)
  }
}

function asString(value: unknown): string | null {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed || null
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

function firstString(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = asString(record[key])
    if (value) return value
  }
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

function normalizeVerification(value: string | null): 'VERIFIED' | 'UNVERIFIED' | 'PARTIAL' {
  if (value === 'VERIFIED') return 'VERIFIED'
  if (value === 'UNVERIFIED') return 'UNVERIFIED'
  return 'PARTIAL'
}

function normalizeCoverage(value: string | null): 'FULL' | 'PARTIAL' | 'NONE' {
  if (value === 'FULL') return 'FULL'
  if (value === 'NONE') return 'NONE'
  return 'PARTIAL'
}

function normalizeRelationshipStrength(value: string | null): RelationshipStrength {
  if (
    value === 'STRONG' ||
    value === 'MEDIUM' ||
    value === 'HISTORICAL' ||
    value === 'WEAK' ||
    value === 'UNKNOWN' ||
    value === 'NONE'
  ) {
    return value
  }
  return 'UNKNOWN'
}

function normalizeCapabilityType(value: string | null): CapabilityType | null {
  const allowed: CapabilityType[] = [
    'DIRECT',
    'NEED_MANUFACTURER',
    'PARTNER',
    'DIRECT_AUTHORIZED',
    'DIRECT_UNCONFIRMED',
    'RENTAL_CAPABLE',
    'CAN_SOURCE_PARTNER',
    'SERVICE_ONLY',
  ]
  return allowed.find((item) => item === value) ?? null
}

function normalizeProductItems(items: unknown[]): TodayActionCard['facts']['products'] {
  const result: NonNullable<TodayActionCard['facts']['products']> = []
  for (const item of items) {
    if (typeof item === 'string') {
      const name = item.trim()
      if (name) result.push({ name, category: null, quantity: null, specification: null })
      continue
    }
    const record = asRecord(item)
    if (!record) continue
    const name = firstString(record, ['raw_name', 'product_name', 'name', 'item_name'])
    if (!name) continue
    result.push({
      name,
      category: firstString(record, ['category', 'product_category']),
      quantity: firstString(record, ['quantity', 'qty']),
      specification: firstString(record, ['specification', 'spec', 'model']),
    })
  }
  return result.length ? result : null
}

function normalizePublicContact(value: unknown): TodayActionCard['facts']['official_contact'] {
  const direct = asString(value)
  if (direct) return { name: direct, title: null, phone: null, email: null }
  const record = asRecord(value)
  if (!record) return null
  const contact = {
    name: firstString(record, ['name', 'contact_name']),
    title: firstString(record, ['title', 'role']),
    phone: firstString(record, ['phone', 'telephone', 'mobile']),
    email: firstString(record, ['email']),
  }
  return Object.values(contact).some(Boolean) ? contact : null
}

function normalizeCapability(
  capability: PublicProductCapability,
): TodayActionCard['customer_context']['matching_product_capabilities'][number] | null {
  const category = capability.category ?? capability.subcategory
  const capabilityType = normalizeCapabilityType(capability.capability_type)
  if (!category || !capabilityType) return null
  return {
    category,
    subcategory: capability.subcategory,
    matched_taxonomy_ids: capability.matched_taxonomy_ids,
    brands: capability.brands,
    capability_type: capabilityType,
  }
}

function componentPercent(card: PublicTodayActionCard, code: string): number {
  const component = card.priority.components.find((item) => item.code === code)
  if (!component || component.max_points <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((component.points / component.max_points) * 100)))
}

function mapPublicCard(card: PublicTodayActionCard): TodayActionCard {
  const relationship = card.customer_context.hospital_relationship
  const capabilities = card.customer_context.matching_product_capabilities
    .map(normalizeCapability)
    .filter((item): item is NonNullable<typeof item> => item !== null)

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
      products: normalizeProductItems(card.facts.product_items),
      official_contact: normalizePublicContact(card.facts.public_contact),
      verification_status: normalizeVerification(card.facts.verification_status),
      coverage_status: normalizeCoverage(card.facts.coverage_status),
    },
    evidence_source_urls: card.evidence_source_urls,
    customer_context: {
      hospital_relationship:
        relationship && relationship.confirmed_by_customer
          ? {
              hospital: relationship.hospital_name,
              department: relationship.department,
              relationship_strength: normalizeRelationshipStrength(
                relationship.relationship_strength,
              ),
              owner: relationship.owner,
              last_confirmed_at: relationship.last_confirmed_at,
            }
          : null,
      matching_product_capabilities: capabilities,
      partnering_policy: {
        can_find_manufacturer:
          card.customer_context.partnering_policy.can_seek_temporary_manufacturer,
        can_partner_channel:
          card.customer_context.partnering_policy.can_cooperate_with_channel_partner,
        can_handle_lease: card.customer_context.partnering_policy.can_do_rental_projects,
      },
    },
    priority: {
      score: card.priority.score,
      score_scope:
        card.priority.score_scope ??
        (card.priority.score_type === 'BUSINESS_PRIORITY_PERSONALIZED_V2' ? 'PERSONALIZED' : 'PUBLIC'),
      components: {
        PRODUCT_EXECUTION_CAPABILITY: componentPercent(
          card,
          'PRODUCT_EXECUTION_CAPABILITY',
        ),
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

function mapFollowupRecord(record: ServerFollowupRecord): FollowupRecord {
  return {
    id: record.id,
    status: record.status,
    note: record.note ?? undefined,
    reason: record.reason ? (CODE_TO_NOT_FIT_REASON.get(record.reason) ?? record.reason) : undefined,
    remind_at: record.remind_at ?? undefined,
    at: record.at,
    actor: record.actor,
  }
}

function applyFollowupState(card: TodayActionCard, state: ServerFollowupState): TodayActionCard {
  if (state.opportunity_id !== card.opportunity_id) {
    throw new Error('FOLLOWUP_OPPORTUNITY_MISMATCH')
  }
  return {
    ...card,
    followup_status: state.current_status,
    followup_history: state.history.map(mapFollowupRecord),
    remind_at: state.remind_at,
  }
}

export class ApiTodayActionsService implements TodayActionsService {
  private readonly baseUrl: string

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '')
  }

  private async requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        ...(init?.headers ?? {}),
      },
    })
    if (!response.ok) throw new Error(`HTTP_${response.status}`)
    const payload: unknown = await response.json()
    assertNoInternalFields(payload)
    return payload as T
  }

  private async getFollowupState(id: string): Promise<ServerFollowupState> {
    return this.requestJson<ServerFollowupState>(`/followup/${encodeURIComponent(id)}`)
  }

  private async enrichWithServerFollowup(card: TodayActionCard): Promise<TodayActionCard> {
    const state = await this.getFollowupState(card.opportunity_id)
    return applyFollowupState(card, state)
  }

  async getTodayActions(): Promise<TodayActionsResponse> {
    const data = await this.requestJson<TodayActionsPublicResponse>('/today')
    const cards = await Promise.all(
      data.cards.map(mapPublicCard).map((card) => this.enrichWithServerFollowup(card)),
    )
    return {
      schema_version: data.schema_version,
      mode: data.mode,
      input_candidate_count: data.input_candidate_count,
      matched_count: data.matched_count,
      card_count: data.card_count,
      model_request_count: data.model_request_count,
      coverage_warning: COVERAGE_WARNING,
      generated_at: data.snapshot_as_of,
      refreshed_at: data.snapshot_as_of,
      cards,
      model_requests: [],
    }
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    try {
      const card = await this.requestJson<PublicTodayActionCard>(
        `/opportunity/${encodeURIComponent(id)}`,
      )
      return await this.enrichWithServerFollowup(mapPublicCard(card))
    } catch (error) {
      if (error instanceof Error && error.message === 'HTTP_404') return null
      throw error
    }
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    const payload: Record<string, string> = {
      status: input.status,
      mutation_id: `followup:${crypto.randomUUID()}`,
    }
    if (input.note) payload.note = input.note
    if (input.remind_at) payload.remind_at = input.remind_at
    if (input.status === 'NOT_FIT') {
      const reason = input.reason as NotFitReason | undefined
      if (!reason || !NOT_FIT_REASON_TO_CODE[reason]) {
        throw new Error('NOT_FIT_REASON_REQUIRED')
      }
      payload.reason = NOT_FIT_REASON_TO_CODE[reason]
    }

    await this.requestJson<ServerFollowupState>(`/followup/${encodeURIComponent(id)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  }

  async requestOutreachDraft(_id: string): Promise<OutreachDraft> {
    throw new Error('OUTREACH_API_NOT_IMPLEMENTED')
  }
}
