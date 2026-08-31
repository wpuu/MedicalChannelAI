import type {
  FollowupInput,
  FollowupRecord,
  OutreachDraft,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'
import type { PublicTodayActionCard, TodayActionsPublicResponse } from '@/types/public'
import type { TodayActionsService } from './TodayActionsService'

const STORAGE_KEY = 'medopp.pipeline-followups.v1'
const COVERAGE_WARNING = '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。'

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

interface StoredFollowup {
  status: TodayActionCard['followup_status']
  remind_at: string | null
  history: FollowupRecord[]
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
      lifecycle_stage: card.facts.lifecycle_state,
      notice_type: card.facts.notice_type,
      publish_date: card.facts.published_at,
      registration_deadline: card.facts.registration_deadline,
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
    evidence_source_urls: card.evidence_source_urls,
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
      components: {
        PRODUCT_EXECUTION_CAPABILITY: componentPercent(card, 'PRODUCT_EXECUTION_CAPABILITY'),
        RELATIONSHIP: componentPercent(card, 'RELATIONSHIP'),
        INTERVENTION_STAGE: componentPercent(card, 'INTERVENTION_STAGE'),
        PROJECT_AMOUNT: componentPercent(card, 'PROJECT_AMOUNT'),
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

function buildGroundedDraft(card: TodayActionCard): string {
  const buyer = card.facts.hospital ?? card.facts.buyer_name ?? '相关单位'
  const project = card.facts.project_name ?? '相关项目'
  const contact = card.facts.official_contact?.name
  const greeting = contact ? `${contact}老师` : '老师'
  const facts = [
    card.facts.notice_type ? `公告类型：${card.facts.notice_type}` : null,
    card.facts.budget ? `公开预算：${Math.round(card.facts.budget / 10000)}万元` : null,
    card.facts.registration_deadline ? `报名/获取文件截止：${card.facts.registration_deadline}` : null,
    card.facts.bid_deadline ? `投标/响应截止：${card.facts.bid_deadline}` : null,
  ].filter(Boolean)
  return [
    '【公开事实沟通草稿】',
    '',
    `${greeting}您好：`,
    '',
    `关注到${buyer}公开发布了「${project}」。`,
    facts.length ? `目前可核验的公开信息包括：${facts.join('；')}。` : '当前公开信息有限，沟通时仅引用已核验内容。',
    '',
    '想进一步了解当前需求范围、时间安排以及后续资料对接窗口。如方便，我们再根据实际需求准备对应方案。',
    '',
    '说明：本草稿只使用公开采购事实，不代表医院立场，也未推断院内关系、厂家授权、品牌资源或中标概率。',
  ].join('\n')
}

export class StaticSnapshotTodayActionsService implements TodayActionsService {
  private snapshot: TodayActionsResponse | null = null

  constructor(private readonly snapshotUrl: string) {}

  private hydrateFollowups(cards: TodayActionCard[]): TodayActionCard[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return cards
      const stored = JSON.parse(raw) as Record<string, StoredFollowup>
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
    } catch {
      return cards
    }
  }

  private persistFollowups(): void {
    if (!this.snapshot) return
    try {
      const stored: Record<string, StoredFollowup> = {}
      for (const card of this.snapshot.cards) {
        stored[card.opportunity_id] = {
          status: card.followup_status,
          remind_at: card.remind_at,
          history: card.followup_history,
        }
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
    } catch {
      // Browsers that block localStorage can still use the in-memory snapshot.
    }
  }

  private async ensureLoaded(): Promise<TodayActionsResponse> {
    if (this.snapshot) return this.snapshot
    const response = await fetch(this.snapshotUrl, {
      headers: { Accept: 'application/json' },
      cache: 'no-cache',
    })
    if (!response.ok) throw new Error(`SNAPSHOT_HTTP_${response.status}`)
    const payload: unknown = await response.json()
    assertNoInternalFields(payload)
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
    this.snapshot = {
      schema_version: data.schema_version,
      mode: data.mode,
      input_candidate_count: data.input_candidate_count,
      matched_count: data.matched_count,
      card_count: data.card_count,
      model_request_count: data.model_request_count,
      coverage_warning: COVERAGE_WARNING,
      generated_at: data.snapshot_as_of,
      refreshed_at: data.snapshot_as_of,
      cards: this.hydrateFollowups(data.cards.map(mapPublicCard)),
      model_requests: [],
    }
    return this.snapshot
  }

  async getTodayActions(): Promise<TodayActionsResponse> {
    return structuredClone(await this.ensureLoaded())
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    const data = await this.ensureLoaded()
    const card = data.cards.find((item) => item.opportunity_id === id)
    return card ? structuredClone(card) : null
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    const data = await this.ensureLoaded()
    const card = data.cards.find((item) => item.opportunity_id === id)
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
    this.persistFollowups()
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
      disclaimer: '试用快照模式 · 仅依据已核验公开事实生成，不推断客户关系、厂家资源或医院内部信息。',
    }
  }
}
