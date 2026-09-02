import type { FollowupStatus, TodayActionCard } from '@/types'
import { isStableOpportunityId } from '@/utils/opportunityId'
import { todayActionsService } from './index'
import { apiBaseUrl, isApiMode } from './apiConfig'
import { listStoredFollowups } from './localFollowupStore'

interface FollowedProductItem {
  name: string
  category: string | null
  quantity: string | null
  specification: string | null
}

interface FollowedPublicContact {
  name: string | null
  title: string | null
  phone: string | null
  email: string | null
}

export interface FollowedOpportunity {
  opportunity_id: string
  followup_status: string
  remind_at: string | null
  latest_note: string | null
  followup_updated_at: string
  facts: {
    project_number: string | null
    project_name: string | null
    buyer_name: string | null
    hospital_name: string | null
    department: string | null
    region: string | null
    lifecycle_state: string | null
    notice_type: string | null
    published_at: string | null
    registration_deadline: string | null
    registration_deadline_date: string | null
    bid_deadline: string | null
    expected_procurement_at: string | null
    budget_cny: number | null
    procurement_method: string | null
    product_categories: string[]
    product_items: FollowedProductItem[]
    public_contact: FollowedPublicContact | null
    verification_status: string | null
    coverage_status: string | null
  }
  evidence_source_urls: string[]
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

const NOT_FIT_REASON_LABEL: Record<string, string> = {
  NO_PRODUCT_CAPABILITY: '没有对应产品',
  NO_MANUFACTURER_ACCESS: '暂无厂家资源',
  RELATIONSHIP_TOO_WEAK: '医院关系太弱',
  AMOUNT_TOO_SMALL: '项目金额太小',
  PROJECT_TOO_LATE: '介入时间太晚',
  COMPETITOR_LOCKED_CUSTOMER_JUDGMENT: '判断竞争对手已锁定',
  DEPARTMENT_OUT_OF_SCOPE: '科室不匹配',
  REGION_OUT_OF_SCOPE: '区域不匹配',
  RENTAL_NOT_SUPPORTED: '不做租赁项目',
  OTHER: '其他',
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function exactKeys(record: Record<string, unknown>, allowed: string[]): boolean {
  const expected = new Set(allowed)
  const keys = Object.keys(record)
  return keys.length === expected.size && keys.every((key) => expected.has(key))
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function nullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value))
}

function isFollowupStatus(value: unknown): value is FollowupStatus {
  return typeof value === 'string' && FOLLOWUP_STATUSES.has(value as FollowupStatus)
}

async function responseError(response: Response): Promise<Error> {
  try {
    const root = asRecord(await response.json())
    if (typeof root?.error === 'string') return new Error(root.error)
  } catch {
    // Fall through to the status-only error.
  }
  return new Error(`HTTP_${response.status}`)
}

function validateProducts(value: unknown): FollowedProductItem[] {
  if (!Array.isArray(value)) throw new Error('FOLLOWED_RESPONSE_INVALID')
  return value.map((item) => {
    const row = asRecord(item)
    if (
      !row ||
      !exactKeys(row, ['name', 'category', 'quantity', 'specification']) ||
      typeof row.name !== 'string' ||
      !row.name.trim() ||
      !nullableString(row.category) ||
      !nullableString(row.quantity) ||
      !nullableString(row.specification)
    ) {
      throw new Error('FOLLOWED_RESPONSE_INVALID')
    }
    return {
      name: row.name,
      category: row.category,
      quantity: row.quantity,
      specification: row.specification,
    }
  })
}

function validateContact(value: unknown): FollowedPublicContact | null {
  if (value === null) return null
  const row = asRecord(value)
  if (
    !row ||
    !exactKeys(row, ['name', 'title', 'phone', 'email']) ||
    !nullableString(row.name) ||
    !nullableString(row.title) ||
    !nullableString(row.phone) ||
    !nullableString(row.email)
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }
  return {
    name: row.name,
    title: row.title,
    phone: row.phone,
    email: row.email,
  }
}

function validateItem(value: unknown): FollowedOpportunity {
  const row = asRecord(value)
  if (
    !row ||
    !exactKeys(row, [
      'opportunity_id',
      'followup_status',
      'remind_at',
      'latest_note',
      'followup_updated_at',
      'facts',
      'evidence_source_urls',
    ]) ||
    !isStableOpportunityId(row.opportunity_id) ||
    !isFollowupStatus(row.followup_status) ||
    !nullableString(row.remind_at) ||
    !nullableString(row.latest_note) ||
    typeof row.followup_updated_at !== 'string' ||
    Number.isNaN(new Date(row.followup_updated_at).getTime()) ||
    !Array.isArray(row.evidence_source_urls) ||
    row.evidence_source_urls.some((item) => typeof item !== 'string')
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }

  const facts = asRecord(row.facts)
  if (
    !facts ||
    !exactKeys(facts, [
      'project_number',
      'project_name',
      'buyer_name',
      'hospital_name',
      'department',
      'region',
      'lifecycle_state',
      'notice_type',
      'published_at',
      'registration_deadline',
      'registration_deadline_date',
      'bid_deadline',
      'expected_procurement_at',
      'budget_cny',
      'procurement_method',
      'product_categories',
      'product_items',
      'public_contact',
      'verification_status',
      'coverage_status',
    ]) ||
    !nullableString(facts.project_number) ||
    !nullableString(facts.project_name) ||
    !nullableString(facts.buyer_name) ||
    !nullableString(facts.hospital_name) ||
    !nullableString(facts.department) ||
    !nullableString(facts.region) ||
    !nullableString(facts.lifecycle_state) ||
    !nullableString(facts.notice_type) ||
    !nullableString(facts.published_at) ||
    !nullableString(facts.registration_deadline) ||
    !nullableString(facts.registration_deadline_date) ||
    !nullableString(facts.bid_deadline) ||
    !nullableString(facts.expected_procurement_at) ||
    !nullableNumber(facts.budget_cny) ||
    !nullableString(facts.procurement_method) ||
    !Array.isArray(facts.product_categories) ||
    facts.product_categories.some((item) => typeof item !== 'string') ||
    !nullableString(facts.verification_status) ||
    !nullableString(facts.coverage_status)
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }

  return {
    opportunity_id: row.opportunity_id,
    followup_status: row.followup_status,
    remind_at: row.remind_at,
    latest_note: row.latest_note,
    followup_updated_at: row.followup_updated_at,
    facts: {
      project_number: facts.project_number,
      project_name: facts.project_name,
      buyer_name: facts.buyer_name,
      hospital_name: facts.hospital_name,
      department: facts.department,
      region: facts.region,
      lifecycle_state: facts.lifecycle_state,
      notice_type: facts.notice_type,
      published_at: facts.published_at,
      registration_deadline: facts.registration_deadline,
      registration_deadline_date: facts.registration_deadline_date,
      bid_deadline: facts.bid_deadline,
      expected_procurement_at: facts.expected_procurement_at,
      budget_cny: facts.budget_cny,
      procurement_method: facts.procurement_method,
      product_categories: [...facts.product_categories] as string[],
      product_items: validateProducts(facts.product_items),
      public_contact: validateContact(facts.public_contact),
      verification_status: facts.verification_status,
      coverage_status: facts.coverage_status,
    },
    evidence_source_urls: [...row.evidence_source_urls] as string[],
  }
}

interface HistoricalFollowupState {
  status: FollowupStatus
  remind_at: string | null
  history: TodayActionCard['followup_history']
}

function validateHistoricalFollowupState(value: unknown, opportunityId: string): HistoricalFollowupState {
  const root = asRecord(value)
  if (
    !root ||
    root.schema_version !== '0.1' ||
    root.opportunity_id !== opportunityId ||
    !isFollowupStatus(root.current_status) ||
    !nullableString(root.remind_at) ||
    !Array.isArray(root.history)
  ) {
    throw new Error('FOLLOWUP_RESPONSE_INVALID')
  }

  const history = root.history.map((value) => {
    const row = asRecord(value)
    if (
      !row ||
      typeof row.id !== 'string' ||
      !isFollowupStatus(row.status) ||
      !nullableString(row.note) ||
      !nullableString(row.reason) ||
      !nullableString(row.remind_at) ||
      typeof row.at !== 'string' ||
      Number.isNaN(new Date(row.at).getTime()) ||
      typeof row.actor !== 'string'
    ) {
      throw new Error('FOLLOWUP_RESPONSE_INVALID')
    }
    return {
      id: row.id,
      status: row.status,
      note: row.note ?? undefined,
      reason: row.reason ? (NOT_FIT_REASON_LABEL[row.reason] ?? row.reason) : undefined,
      remind_at: row.remind_at ?? undefined,
      at: row.at,
      actor: row.actor,
    }
  })

  return {
    status: root.current_status,
    remind_at: root.remind_at,
    history,
  }
}

async function getLocalFollowedOpportunities(): Promise<FollowedOpportunity[]> {
  await todayActionsService.getTodayActions()

  return listStoredFollowups()
    .flatMap(({ opportunity_id, entry }) => {
      const snapshot = entry.public_snapshot
      if (!snapshot) return []
      const latestRecord = entry.history[0]
      const latestNote = entry.history.find((record) => Boolean(record.note?.trim()))?.note ?? null
      return [
        {
          opportunity_id,
          followup_status: entry.status,
          remind_at: entry.remind_at,
          latest_note: latestNote,
          followup_updated_at:
            latestRecord?.at ?? entry.remind_at ?? '1970-01-01T00:00:00.000Z',
          facts: {
            project_number: snapshot.facts.project_number,
            project_name: snapshot.facts.project_name,
            buyer_name: snapshot.facts.buyer_name,
            hospital_name: snapshot.facts.hospital_name,
            department: snapshot.facts.department,
            region: null,
            lifecycle_state: snapshot.facts.lifecycle_state,
            notice_type: null,
            published_at: snapshot.facts.published_at,
            registration_deadline: null,
            registration_deadline_date: null,
            bid_deadline: snapshot.facts.bid_deadline,
            expected_procurement_at: snapshot.facts.expected_procurement_at,
            budget_cny: snapshot.facts.budget_cny,
            procurement_method: null,
            product_categories: [],
            product_items: [],
            public_contact: null,
            verification_status: null,
            coverage_status: null,
          },
          evidence_source_urls: [...snapshot.evidence_source_urls],
        },
      ]
    })
    .sort(
      (a, b) =>
        new Date(b.followup_updated_at).getTime() - new Date(a.followup_updated_at).getTime(),
    )
}

export async function getFollowedOpportunities(): Promise<FollowedOpportunity[]> {
  if (!isApiMode) return getLocalFollowedOpportunities()
  const response = await fetch(`${apiBaseUrl}/followed`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await responseError(response)
  const value: unknown = await response.json()
  const root = asRecord(value)
  if (
    !root ||
    !exactKeys(root, ['schema_version', 'mode', 'count', 'items']) ||
    root.schema_version !== '0.1' ||
    root.mode !== 'FOLLOWED_OPPORTUNITIES' ||
    typeof root.count !== 'number' ||
    !Number.isInteger(root.count) ||
    root.count < 0 ||
    root.count > 100 ||
    !Array.isArray(root.items)
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }
  const items = root.items.map(validateItem)
  if (root.count !== items.length) throw new Error('FOLLOWED_RESPONSE_INVALID')
  return items
}

async function getFollowedOpportunityById(opportunityId: string): Promise<FollowedOpportunity | null> {
  const response = await fetch(`${apiBaseUrl}/followed?id=${encodeURIComponent(opportunityId)}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (response.status === 404) return null
  if (!response.ok) throw await responseError(response)
  const root = asRecord(await response.json())
  if (
    !root ||
    !exactKeys(root, ['schema_version', 'mode', 'item']) ||
    root.schema_version !== '0.1' ||
    root.mode !== 'FOLLOWED_OPPORTUNITY'
  ) {
    throw new Error('FOLLOWED_RESPONSE_INVALID')
  }
  return validateItem(root.item)
}

function verificationStatus(value: string | null): TodayActionCard['facts']['verification_status'] {
  if (value === 'VERIFIED') return 'VERIFIED'
  if (value === 'UNVERIFIED') return 'UNVERIFIED'
  return 'PARTIAL'
}

function coverageStatus(value: string | null): TodayActionCard['facts']['coverage_status'] {
  if (value === 'FULL') return 'FULL'
  if (value === 'NONE') return 'NONE'
  return 'PARTIAL'
}

export async function getHistoricalFollowedOpportunityCard(
  opportunityId: string,
): Promise<TodayActionCard | null> {
  if (!isApiMode) return null
  if (!isStableOpportunityId(opportunityId)) throw new Error('OPPORTUNITY_ID_INVALID')

  const item = await getFollowedOpportunityById(opportunityId)
  if (!item) return null

  const response = await fetch(`${apiBaseUrl}/followup/${encodeURIComponent(opportunityId)}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await responseError(response)
  const state = validateHistoricalFollowupState(await response.json(), opportunityId)

  return {
    rank: 0,
    opportunity_id: opportunityId,
    facts: {
      project_code: item.facts.project_number,
      project_name: item.facts.project_name,
      hospital: item.facts.hospital_name,
      buyer_name: item.facts.buyer_name,
      department: item.facts.department,
      region: item.facts.region,
      lifecycle_stage: item.facts.lifecycle_state,
      notice_type: item.facts.notice_type,
      publish_date: item.facts.published_at,
      registration_deadline: item.facts.registration_deadline,
      registration_deadline_date: item.facts.registration_deadline_date,
      registration_deadline_precision: item.facts.registration_deadline
        ? 'MINUTE'
        : item.facts.registration_deadline_date
          ? 'DAY'
          : null,
      bid_deadline: item.facts.bid_deadline,
      expected_purchase_date: item.facts.expected_procurement_at,
      budget: item.facts.budget_cny,
      procurement_method: item.facts.procurement_method,
      product_categories: [...item.facts.product_categories],
      products: item.facts.product_items.length ? item.facts.product_items.map((product) => ({ ...product })) : null,
      official_contact: item.facts.public_contact ? { ...item.facts.public_contact } : null,
      verification_status: verificationStatus(item.facts.verification_status),
      coverage_status: coverageStatus(item.facts.coverage_status),
    },
    evidence_source_urls: [...item.evidence_source_urls],
    customer_context: {
      target_hospital: null,
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
      score_scope: 'PUBLIC',
      components: {
        PRODUCT_EXECUTION_CAPABILITY: 0,
        RELATIONSHIP: 0,
        EXECUTION_FLEXIBILITY: 0,
        INTERVENTION_STAGE: 0,
        DEADLINE_URGENCY: 0,
        PROJECT_AMOUNT: 0,
        PRODUCT_SPECIFICITY: 0,
        PUBLICATION_FRESHNESS: 0,
      },
    },
    match_status: 'ARCHIVE',
    recommendation_mode: 'ARCHIVE',
    model_decision_status: 'NOT_ELIGIBLE',
    model_block_reason: '该商机已不在当前可行动商机池；仅展示已保存的历史公开快照与跟进记录。',
    decision: null,
    followup_status: state.status,
    followup_history: state.history,
    remind_at: state.remind_at,
  }
}
