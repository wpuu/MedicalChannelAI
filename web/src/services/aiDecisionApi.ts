import { verifiedSnapshotUrl } from '@/config/snapshotConfig'
import type { CustomerContext, Decision, TodayActionCard } from '@/types'
import { isApiMode } from './apiConfig'
import { beginAiRequest, endAiRequest } from './aiRequestGate'
import { getVerifiedSnapshotAsOf } from './verifiedSnapshotClient'

const CACHE_KEY = 'medopp.grounded-ai-decisions.v1'
const MAX_CACHE_ENTRIES = 50

interface CachedDecisionEntry {
  snapshot_as_of: string
  opportunity_id: string
  context_fingerprint: string
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

// Transient provider failures (slow tail, one invalid model sample, brief
// upstream 5xx) are retried once automatically so the user does not have to
// click the button again. Deterministic failures (auth, closed window, rate
// limit, configuration) are surfaced immediately.
const AUTO_RETRY_CODES = new Set(['AI_TIMEOUT', 'AI_RESPONSE_INVALID', 'AI_PROVIDER_UNAVAILABLE', 'AI_HTTP_502', 'AI_HTTP_503', 'AI_HTTP_504'])
const AUTO_RETRY_DELAY_MS = 800

export function isAutoRetryableAiError(cause: unknown): boolean {
  if (cause instanceof AiDecisionError) return AUTO_RETRY_CODES.has(cause.code)
  // fetch() network failure (TypeError) — e.g. a dropped mobile connection.
  return cause instanceof TypeError
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function aiDecisionErrorMessage(cause: unknown): string {
  if (!(cause instanceof AiDecisionError)) return '网络连接异常或AI服务暂时不可用，请重试'
  if (cause.code === 'AI_NETWORK_UNAVAILABLE') return '网络连接不稳定，已自动重试仍未成功，请检查网络后再试'
  if (cause.code === 'AI_CLIENT_BUSY') return '已有AI分析任务正在处理，请稍候'
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

function fingerprint(value: unknown): string {
  const text = JSON.stringify(value ?? null)
  let hash = 2166136261
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

export function decisionFingerprint(card: TodayActionCard): string {
  return fingerprint({
    customer_context: customerContextPayload(card),
    runtime_window: {
      match_status: card.match_status,
      recommendation_mode: card.recommendation_mode,
      registration_deadline: card.facts.registration_deadline,
      bid_deadline: card.facts.bid_deadline,
    },
  })
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
      if (!record || typeof record.snapshot_as_of !== 'string' || typeof record.opportunity_id !== 'string' || typeof record.cached_at !== 'string') continue
      const decision = normalizeDecision(record.decision)
      if (!decision) continue
      entries.push({
        snapshot_as_of: record.snapshot_as_of,
        opportunity_id: record.opportunity_id,
        context_fingerprint: typeof record.context_fingerprint === 'string' ? record.context_fingerprint : fingerprint(null),
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

export function clearAiDecisionCache(): void {
  try {
    localStorage.removeItem(CACHE_KEY)
  } catch {
    // Best effort only.
  }
}

function getSnapshotAsOf(): Promise<string | null> {
  return getVerifiedSnapshotAsOf(verifiedSnapshotUrl)
}

function findCachedDecision(opportunityId: string, snapshotAsOf: string, fingerprintValue: string): Decision | null {
  const entry = readCache().find(
    (item) => item.opportunity_id === opportunityId && item.snapshot_as_of === snapshotAsOf && item.context_fingerprint === fingerprintValue,
  )
  return entry?.decision ?? null
}

function cacheDecision(opportunityId: string, snapshotAsOf: string, fingerprintValue: string, decision: Decision): void {
  const existing = readCache().filter(
    (item) => !(item.opportunity_id === opportunityId && item.snapshot_as_of === snapshotAsOf && item.context_fingerprint === fingerprintValue),
  )
  writeCache([{ snapshot_as_of: snapshotAsOf, opportunity_id: opportunityId, context_fingerprint: fingerprintValue, cached_at: new Date().toISOString(), decision }, ...existing])
}

export interface AiDecisionBatchResult {
  decisions: Record<string, Decision>
  misses: string[]
  errors: Record<string, string>
  requested_count: number
  ready_count: number
  cache_hit_count: number
}

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
  }).slice(0, 10)
}

async function postAiDecisionBatch(opportunityIds: string[], cacheOnly: boolean): Promise<AiDecisionBatchResult> {
  const response = await fetch('/api/ai/analyze', {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({
      opportunity_ids: opportunityIds,
      cache_only: cacheOnly,
    }),
  })

  const payload: unknown = await response.json().catch(() => null)
  const record = asRecord(payload)
  if (!response.ok) {
    const code = typeof record?.error === 'string' ? record.error : `AI_HTTP_${response.status}`
    throw new AiDecisionError(code, response.status)
  }

  const decisions: Record<string, Decision> = {}
  const misses: string[] = []
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
    } else if (item?.status === 'MISS') {
      misses.push(opportunityId)
    } else {
      errors[opportunityId] = typeof item?.error === 'string' ? item.error : 'AI_BATCH_ITEM_FAILED'
    }
  }

  return {
    decisions,
    misses,
    errors,
    requested_count: typeof record?.requested_count === 'number' ? record.requested_count : opportunityIds.length,
    ready_count: typeof record?.ready_count === 'number' ? record.ready_count : Object.keys(decisions).length,
    cache_hit_count: typeof record?.cache_hit_count === 'number' ? record.cache_hit_count : 0,
  }
}

export async function requestAiDecisionBatch(
  cards: TodayActionCard[],
  options: { cacheOnly?: boolean } = {},
): Promise<AiDecisionBatchResult> {
  const eligible = batchEligibleCards(cards)
  if (eligible.length === 0) {
    return {
      decisions: {},
      misses: [],
      errors: {},
      requested_count: 0,
      ready_count: 0,
      cache_hit_count: 0,
    }
  }

  const cacheOnly = options.cacheOnly === true
  let gateAcquired = false
  if (!cacheOnly) {
    if (!beginAiRequest()) throw new AiDecisionError('AI_CLIENT_BUSY', 429)
    gateAcquired = true
  }

  try {
    const first = await postAiDecisionBatch(eligible.map((card) => card.opportunity_id), cacheOnly)
    if (cacheOnly) return first
    const retryIds = Object.entries(first.errors)
      .filter(([, code]) => AUTO_RETRY_CODES.has(code))
      .map(([opportunityId]) => opportunityId)
    if (retryIds.length === 0) return first

    // One automatic pass for items that failed transiently; anything the slow
    // first pass managed to store is now served from the shared cache.
    await wait(AUTO_RETRY_DELAY_MS)
    let second: AiDecisionBatchResult
    try {
      second = await postAiDecisionBatch(retryIds, false)
    } catch {
      return first
    }
    const errors = { ...first.errors }
    for (const opportunityId of retryIds) delete errors[opportunityId]
    Object.assign(errors, second.errors)
    const decisions = { ...first.decisions, ...second.decisions }
    return {
      decisions,
      misses: [...new Set([...first.misses, ...second.misses])],
      errors,
      requested_count: first.requested_count,
      ready_count: Object.keys(decisions).length,
      cache_hit_count: first.cache_hit_count + second.cache_hit_count,
    }
  } finally {
    if (gateAcquired) endAiRequest()
  }
}

export async function hydrateSharedAiDecisions(
  cards: TodayActionCard[],
): Promise<TodayActionCard[]> {
  try {
    const result = await requestAiDecisionBatch(cards, { cacheOnly: true })
    if (Object.keys(result.decisions).length === 0) return cards
    return cards.map((card) => {
      const decision = result.decisions[card.opportunity_id]
      return decision
        ? { ...card, model_decision_status: 'READY', model_block_reason: null, decision }
        : card
    })
  } catch {
    // Shared hydration is a best-effort optimization. The normal single-item
    // analysis path remains available when cache lookup is unavailable.
    return cards
  }
}

export async function hydrateCachedAiDecisions(cards: TodayActionCard[]): Promise<TodayActionCard[]> {
  const sharedHydrated = await hydrateSharedAiDecisions(cards)
  // Pilot personalization is server-side. A browser cache cannot know when the
  // authenticated user's private profile changed, so do not reuse personalized
  // decisions from localStorage in API mode.
  if (isApiMode) return sharedHydrated
  const snapshotAsOf = await getSnapshotAsOf()
  if (!snapshotAsOf) return sharedHydrated
  return sharedHydrated.map((card) => {
    if (card.decision) return card
    if (card.model_decision_status === 'NOT_ELIGIBLE' || card.model_decision_status === 'BLOCKED_GROUNDING') return card
    const decision = findCachedDecision(card.opportunity_id, snapshotAsOf, decisionFingerprint(card))
    if (!decision) return card
    return { ...card, model_decision_status: 'READY', model_block_reason: null, decision }
  })
}

export async function requestAiDecision(card: TodayActionCard): Promise<Decision> {
  if (card.model_decision_status === 'NOT_ELIGIBLE' || card.model_decision_status === 'BLOCKED_GROUNDING') {
    throw new AiDecisionError('OPPORTUNITY_WINDOW_CLOSED', 409)
  }

  const useLocalContext = !isApiMode
  const snapshotAsOf = useLocalContext ? await getSnapshotAsOf() : null
  const customerContext = useLocalContext ? customerContextPayload(card) : null
  const fingerprintValue = useLocalContext ? decisionFingerprint(card) : fingerprint(null)
  if (snapshotAsOf) {
    const cached = findCachedDecision(card.opportunity_id, snapshotAsOf, fingerprintValue)
    if (cached) return cached
  }

  if (!beginAiRequest()) throw new AiDecisionError('AI_CLIENT_BUSY', 429)
  const requestOnce = async (): Promise<Decision> => {
    const response = await fetch('/api/ai/analyze', {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({
        opportunity_id: card.opportunity_id,
        ...(customerContext ? { customer_context: customerContext } : {}),
      }),
    })

    const payload: unknown = await response.json().catch(() => null)
    const record = asRecord(payload)
    if (!response.ok) {
      const code = typeof record?.error === 'string' ? record.error : `AI_HTTP_${response.status}`
      throw new AiDecisionError(code, response.status)
    }

    const decision = normalizeDecision(record?.decision)
    if (!decision) throw new AiDecisionError('AI_RESPONSE_INVALID', 502)
    return decision
  }
  try {
    let decision: Decision
    try {
      decision = await requestOnce()
    } catch (cause) {
      if (!isAutoRetryableAiError(cause)) throw cause
      // If the slow first attempt finished server-side, this retry is served
      // from the shared durable cache almost instantly.
      await wait(AUTO_RETRY_DELAY_MS)
      decision = await requestOnce()
    }
    if (snapshotAsOf) cacheDecision(card.opportunity_id, snapshotAsOf, fingerprintValue, decision)
    return decision
  } catch (cause) {
    if (cause instanceof TypeError) throw new AiDecisionError('AI_NETWORK_UNAVAILABLE', 0)
    throw cause
  } finally {
    endAiRequest()
  }
}
