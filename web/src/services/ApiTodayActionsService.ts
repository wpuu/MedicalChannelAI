import type {
  CapabilityType,
  FollowupInput,
  FollowupRecord,
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

const FOLLOWUP_STORAGE_KEY = 'medopp.api-followups.v1'
const COVERAGE_WARNING = '当前处于天津 Pilot 阶段，公开数据覆盖持续扩展中。'

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
    value === 'UNKNOWN'
  ) {
    return value
  }
  return 'UNKNOWN'
}

function normalizeCapabilityType(value: string | null): CapabilityType | null {
  const allowed: CapabilityType[] = [
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
      components: {
        PRODUCT_EXECUTION_CAPABILITY: componentPercent(
          card,
          'PRODUCT_EXECUTION_CAPABILITY',
        ),
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

export class ApiTodayActionsService implements TodayActionsService {
  private readonly baseUrl: string
  private followups: Record<string, StoredFollowup>

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '')
    this.followups = this.readFollowups()
  }

  private readFollowups(): Record<string, StoredFollowup> {
    try {
      const raw = localStorage.getItem(FOLLOWUP_STORAGE_KEY)
      return raw ? (JSON.parse(raw) as Record<string, StoredFollowup>) : {}
    } catch {
      return {}
    }
  }

  private persistFollowups() {
    localStorage.setItem(FOLLOWUP_STORAGE_KEY, JSON.stringify(this.followups))
  }

  private enrichFollowup(card: TodayActionCard): TodayActionCard {
    const saved = this.followups[card.opportunity_id]
    if (!saved) return card
    return {
      ...card,
      followup_status: saved.status,
      followup_history: saved.history,
      remind_at: saved.remind_at,
    }
  }

  private async requestJson<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new Error(`HTTP_${response.status}`)
    return (await response.json()) as T
  }

  async getTodayActions(): Promise<TodayActionsResponse> {
    const data = await this.requestJson<TodayActionsPublicResponse>('/today')
    const now = new Date().toISOString()
    return {
      schema_version: data.schema_version,
      mode: data.mode,
      input_candidate_count: data.input_candidate_count,
      matched_count: data.matched_count,
      card_count: data.card_count,
      model_request_count: data.model_request_count,
      coverage_warning: COVERAGE_WARNING,
      generated_at: now,
      refreshed_at: now,
      cards: data.cards.map(mapPublicCard).map((card) => this.enrichFollowup(card)),
      model_requests: [],
    }
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    try {
      const card = await this.requestJson<PublicTodayActionCard>(
        `/opportunity/${encodeURIComponent(id)}`,
      )
      return this.enrichFollowup(mapPublicCard(card))
    } catch (error) {
      if (error instanceof Error && error.message === 'HTTP_404') return null
      throw error
    }
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    const previous = this.followups[id]
    const record: FollowupRecord = {
      id: `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      status: input.status,
      note: input.note,
      reason: input.reason,
      remind_at: input.remind_at,
      at: new Date().toISOString(),
      actor: '当前用户',
    }
    this.followups[id] = {
      status: input.status,
      remind_at: input.remind_at ?? previous?.remind_at ?? null,
      history: [record, ...(previous?.history ?? [])],
    }
    this.persistFollowups()
  }

  async requestOutreachDraft(_id: string): Promise<OutreachDraft> {
    throw new Error('OUTREACH_API_NOT_IMPLEMENTED')
  }
}
