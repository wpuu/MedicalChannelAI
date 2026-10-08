import type { CustomerContext, Decision, TodayActionCard } from '@/types'
import { isApiMode } from './apiConfig'
import { beginAiRequest, endAiRequest } from './aiRequestGate'

// Legacy browser cache of per-card model answers. Per-card next steps are now
// deterministic server rules, so the old entries are only cleared.
const LEGACY_CACHE_KEY = 'medopp.grounded-ai-decisions.v1'

export class AiDecisionError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code)
  }
}

export function aiDecisionErrorMessage(cause: unknown): string {
  if (!(cause instanceof AiDecisionError)) return '网络连接异常或AI服务暂时不可用，请重试'
  if (cause.code === 'AI_NETWORK_UNAVAILABLE') return '网络连接不稳定，已自动重试仍未成功，请检查网络后再试'
  if (cause.code === 'AI_CLIENT_BUSY') return '已有AI研判正在处理，请稍候'
  if (cause.code === 'AI_NOT_CONFIGURED') return 'AI服务尚未启用；公开商机和跟进功能不受影响'
  if (cause.code === 'AI_RATE_LIMITED') return 'AI请求较多，请约1分钟后再试'
  if (cause.code === 'AI_PROVIDER_AUTH_UNAVAILABLE') return 'AI服务连接异常，请稍后再试'
  if (cause.code === 'AI_TIMEOUT') return 'AI服务响应较慢，已自动重试仍未完成，请稍后再试'
  if (cause.code === 'AI_PROVIDER_UNAVAILABLE') return 'AI服务暂时连接失败，请稍后再试'
  if (cause.code === 'VERIFIED_SNAPSHOT_UNAVAILABLE') return '公开商机数据正在更新，请稍后再试AI分析'
  if (cause.code === 'VERIFIED_SNAPSHOT_NOT_FRESH') return '公开商机快照已超过安全刷新窗口，请先核对官方依据，待数据刷新后再使用AI分析'
  if (cause.code === 'SAME_ORIGIN_REQUIRED') return '当前访问地址未通过AI安全校验，请从正式站点进入'
  if (cause.code === 'OPPORTUNITY_WINDOW_CLOSED') return '该项目公开窗口已经结束，当前不再生成行动建议'
  if (cause.code === 'VERIFIED_OPPORTUNITY_NOT_FOUND') return '该商机暂不在已核验商机池中'
  if (cause.code === 'AI_RESPONSE_INVALID') return 'AI返回内容未通过校验，请重试'
  if (cause.code === 'AUTH_REQUIRED') return '登录状态已失效，请重新登录后再分析'
  if (cause.code === 'PRIVATE_PROFILE_UNAVAILABLE') return '暂时无法读取账号私有资源，请稍后再试'
  if (cause.code === 'PRIVATE_DATABASE_NOT_CONFIGURED') return '试用账号数据库尚未配置完成'
  if (cause.code === 'PILOT_CUSTOMER_CONTEXT_SERVER_ONLY') return '试用版个性化资料只能由服务端账号读取，请刷新页面后重试'
  return 'AI分析暂时不可用，请重试'
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

function customerContextPayload(card: TodayActionCard): CustomerContext | null {
  const context = card.customer_context
  const policy = context.partnering_policy
  const hasContext = Boolean(
    context.target_hospital ||
      context.hospital_relationship ||
      context.matching_product_capabilities.length > 0 ||
      policy.can_find_manufacturer !== null ||
      policy.can_partner_channel !== null ||
      policy.can_handle_lease !== null,
  )
  return hasContext ? context : null
}

export function clearAiDecisionCache(): void {
  try {
    localStorage.removeItem(LEGACY_CACHE_KEY)
  } catch {
    // Best effort only.
  }
}

export interface AiDecisionBatchResult {
  decisions: Record<string, Decision>
  errors: Record<string, string>
  requested_count: number
  ready_count: number
}

const MAX_BATCH_IDS = 10
const MAX_HYDRATE_CHUNKS = 3

function batchEligibleCards(cards: TodayActionCard[]): TodayActionCard[] {
  const seen = new Set<string>()
  return cards.filter((card) => {
    if (
      card.model_decision_status === 'NOT_ELIGIBLE' ||
      card.model_decision_status === 'BLOCKED_GROUNDING' ||
      card.decision
    ) {
      return false
    }
    if (seen.has(card.opportunity_id)) return false
    seen.add(card.opportunity_id)
    return true
  })
}

async function postJson(body: Record<string, unknown>): Promise<Record<string, unknown> | null> {
  const response = await fetch('/api/ai/analyze', {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload: unknown = await response.json().catch(() => null)
  const record = asRecord(payload)
  if (!response.ok) {
    const code = typeof record?.error === 'string' ? record.error : `AI_HTTP_${response.status}`
    throw new AiDecisionError(code, response.status)
  }
  return record
}

async function postAiDecisionBatch(opportunityIds: string[]): Promise<AiDecisionBatchResult> {
  const record = await postJson({ opportunity_ids: opportunityIds })
  const decisions: Record<string, Decision> = {}
  const errors: Record<string, string> = {}
  const items = Array.isArray(record?.items) ? record.items : []
  for (const rawItem of items) {
    const item = asRecord(rawItem)
    const opportunityId = typeof item?.opportunity_id === 'string' ? item.opportunity_id : ''
    if (!opportunityId) continue
    if (item?.status === 'READY') {
      const decision = normalizeDecision(item.decision)
      if (decision) decisions[opportunityId] = decision
      else errors[opportunityId] = 'AI_RESPONSE_INVALID'
    } else {
      errors[opportunityId] = typeof item?.error === 'string' ? item.error : 'AI_BATCH_ITEM_FAILED'
    }
  }
  return {
    decisions,
    errors,
    requested_count: opportunityIds.length,
    ready_count: Object.keys(decisions).length,
  }
}

/**
 * Rule-based next steps for many cards: one request per 10 cards, answered
 * from verified facts without a model call, so no client-side AI gate.
 */
export async function requestAiDecisionBatch(cards: TodayActionCard[]): Promise<AiDecisionBatchResult> {
  const eligible = batchEligibleCards(cards).slice(0, MAX_BATCH_IDS * MAX_HYDRATE_CHUNKS)
  const chunks: string[][] = []
  for (let index = 0; index < eligible.length; index += MAX_BATCH_IDS) {
    chunks.push(eligible.slice(index, index + MAX_BATCH_IDS).map((card) => card.opportunity_id))
  }
  const results = await Promise.all(chunks.map((ids) => postAiDecisionBatch(ids)))
  const decisions = Object.assign({}, ...results.map((result) => result.decisions)) as Record<string, Decision>
  const errors = Object.assign({}, ...results.map((result) => result.errors)) as Record<string, string>
  return {
    decisions,
    errors,
    requested_count: eligible.length,
    ready_count: Object.keys(decisions).length,
  }
}

export async function hydrateSharedAiDecisions(
  cards: TodayActionCard[],
): Promise<TodayActionCard[]> {
  try {
    const result = await requestAiDecisionBatch(cards)
    if (Object.keys(result.decisions).length === 0) return cards
    return cards.map((card) => {
      const decision = result.decisions[card.opportunity_id]
      return decision
        ? { ...card, model_decision_status: 'READY', model_block_reason: null, decision }
        : card
    })
  } catch {
    // Best effort: the card keeps its single-item fallback button.
    return cards
  }
}

export async function hydrateCachedAiDecisions(cards: TodayActionCard[]): Promise<TodayActionCard[]> {
  return hydrateSharedAiDecisions(cards)
}

export async function requestAiDecision(card: TodayActionCard): Promise<Decision> {
  if (card.model_decision_status === 'NOT_ELIGIBLE' || card.model_decision_status === 'BLOCKED_GROUNDING') {
    throw new AiDecisionError('OPPORTUNITY_WINDOW_CLOSED', 409)
  }
  // Trial mode keeps the user's own resources in this browser; the server
  // applies them as deterministic rules. Pilot mode reads them server-side.
  const useLocalContext = !isApiMode
  const customerContext = useLocalContext ? customerContextPayload(card) : null
  try {
    const record = await postJson({
      opportunity_id: card.opportunity_id,
      ...(customerContext ? { customer_context: customerContext } : {}),
    })
    const decision = normalizeDecision(record?.decision)
    if (!decision) throw new AiDecisionError('AI_RESPONSE_INVALID', 502)
    return decision
  } catch (cause) {
    if (cause instanceof TypeError) throw new AiDecisionError('AI_NETWORK_UNAVAILABLE', 0)
    throw cause
  }
}

// ---- Page brief -------------------------------------------------------------

export interface PageBriefFocus {
  opportunity_id: string
  project_name: string | null
  buyer_name: string | null
  reason_code: string
  reason_label: string
  fact_line: string
  next_step: string
  note: string | null
}

export interface PageBriefSkip {
  opportunity_id: string
  project_name: string | null
  buyer_name: string | null
  reason_code: string
  reason_label: string
}

export interface PageBrief {
  brief_source: 'AI' | 'RULES'
  item_count: number
  early_signal_count: number
  headline: string | null
  focus: PageBriefFocus[]
  skip: PageBriefSkip[]
  same_buyer_groups: { buyer_name: string; opportunity_ids: string[]; count: number }[]
  deadlines_within_7_days: {
    opportunity_id: string
    project_name: string | null
    buyer_name: string | null
    label: string
    at: string
    days_left: number
  }[]
}

export interface PageBriefResult {
  brief: PageBrief
  generated_for_date: string | null
  ai_error: string | null
  cache_hit: boolean
}

function normalizePageBrief(value: unknown): PageBrief | null {
  const record = asRecord(value)
  if (!record || !Array.isArray(record.focus)) return null
  const source = record.brief_source === 'AI' ? 'AI' : 'RULES'
  return {
    brief_source: source,
    item_count: typeof record.item_count === 'number' ? record.item_count : 0,
    early_signal_count: typeof record.early_signal_count === 'number' ? record.early_signal_count : 0,
    headline: typeof record.headline === 'string' && record.headline.trim() ? record.headline.trim() : null,
    focus: record.focus.filter((item): item is PageBriefFocus => Boolean(asRecord(item)?.opportunity_id)),
    skip: Array.isArray(record.skip)
      ? record.skip.filter((item): item is PageBriefSkip => Boolean(asRecord(item)?.opportunity_id))
      : [],
    same_buyer_groups: Array.isArray(record.same_buyer_groups) ? record.same_buyer_groups as PageBrief['same_buyer_groups'] : [],
    deadlines_within_7_days: Array.isArray(record.deadlines_within_7_days)
      ? record.deadlines_within_7_days as PageBrief['deadlines_within_7_days']
      : [],
  }
}

/**
 * Whole-region brief. cacheOnly=true never triggers a model call: it returns
 * today's shared AI brief if one exists, otherwise the rule brief. Generation
 * is one combined model call over every open opportunity of the region.
 */
export async function requestPageBrief(
  markets: string[],
  options: { cacheOnly?: boolean } = {},
): Promise<PageBriefResult> {
  const cacheOnly = options.cacheOnly === true
  let gateAcquired = false
  if (!cacheOnly) {
    if (!beginAiRequest()) throw new AiDecisionError('AI_CLIENT_BUSY', 429)
    gateAcquired = true
  }
  try {
    const record = await postJson({ page_brief: { markets }, cache_only: cacheOnly })
    const brief = normalizePageBrief(record?.brief)
    if (!brief) throw new AiDecisionError('AI_RESPONSE_INVALID', 502)
    const cache = asRecord(record?.shared_public_cache)
    return {
      brief,
      generated_for_date: typeof record?.generated_for_date === 'string' ? record.generated_for_date : null,
      ai_error: typeof record?.ai_error === 'string' ? record.ai_error : null,
      cache_hit: cache?.cache_hit === true,
    }
  } catch (cause) {
    if (cause instanceof TypeError) throw new AiDecisionError('AI_NETWORK_UNAVAILABLE', 0)
    throw cause
  } finally {
    if (gateAcquired) endAiRequest()
  }
}
