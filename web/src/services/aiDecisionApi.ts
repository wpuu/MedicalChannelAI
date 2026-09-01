import type { CustomerContext, Decision, TodayActionCard } from '@/types'

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

export function aiDecisionErrorMessage(cause: unknown): string {
  if (!(cause instanceof AiDecisionError)) {
    return '网络连接异常或AI服务暂时不可用，请重试'
  }
  if (cause.code === 'AI_NOT_CONFIGURED') {
    return 'AI服务尚未启用；公开商机和跟进功能不受影响'
  }
  if (cause.code === 'AI_RATE_LIMITED') {
    return 'AI请求较多，请约1分钟后再试'
  }
  if (cause.code === 'AI_PROVIDER_AUTH_UNAVAILABLE') {
    return 'AI服务连接异常，请稍后再试'
  }
  if (cause.code === 'AI_TIMEOUT') {
    return 'AI分析超时，可立即重试'
  }
  if (cause.code === 'AI_PROVIDER_UNAVAILABLE') {
    return 'AI服务暂时连接失败，请稍后再试'
  }
  if (cause.code === 'VERIFIED_SNAPSHOT_UNAVAILABLE') {
    return '公开商机数据正在更新，请稍后再试AI分析'
  }
  if (cause.code === 'SAME_ORIGIN_REQUIRED') {
    return '当前访问地址未通过AI安全校验，请从正式站点进入'
  }
  if (cause.code === 'OPPORTUNITY_WINDOW_CLOSED') {
    return '该项目公开窗口已经结束，当前不再生成行动建议'
  }
  if (cause.code === 'VERIFIED_OPPORTUNITY_NOT_FOUND') {
    return '该商机暂不在已核验商机池中'
  }
  if (cause.code === 'AI_RESPONSE_INVALID') {
    return 'AI返回内容未通过校验，请重试'
  }
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

function decisionFingerprint(card: TodayActionCard): string {
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
      if (
        !record ||
        typeof record.snapshot_as_of !== 'string' ||
        typeof record.opportunity_id !== 'string' ||
        typeof record.cached_at !== 'string'
      ) {
        continue
      }
      const decision = normalizeDecision(record.decision)
      if (!decision) continue
      entries.push({
        snapshot_as_of: record.snapshot_as_of,
        opportunity_id: record.opportunity_id,
        context_fingerprint:
          typeof record.context_fingerprint === 'string'
            ? record.context_fingerprint
            : fingerprint(null),
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

async function getSnapshotAsOf(): Promise<string | null> {
  try {
    const response = await fetch('/data/today-actions.public.json', {
      headers: { Accept: 'application/json' },
      cache: 'no-cache',
    })
    if (!response.ok) return null
    const payload: unknown = await response.json()
    const record = asRecord(payload)
    const value = record?.snapshot_as_of
    return typeof value === 'string' && !Number.isNaN(Date.parse(value)) ? value : null
  } catch {
    return null
  }
}

function findCachedDecision(
  opportunityId: string,
  snapshotAsOf: string,
  fingerprintValue: string,
): Decision | null {
  const entry = readCache().find(
    (item) =>
      item.opportunity_id === opportunityId &&
      item.snapshot_as_of === snapshotAsOf &&
      item.context_fingerprint === fingerprintValue,
  )
  return entry?.decision ?? null
}

function cacheDecision(
  opportunityId: string,
  snapshotAsOf: string,
  fingerprintValue: string,
  decision: Decision,
): void {
  const existing = readCache().filter(
    (item) =>
      !(
        item.opportunity_id === opportunityId &&
        item.snapshot_as_of === snapshotAsOf &&
        item.context_fingerprint === fingerprintValue
      ),
  )
  writeCache([
    {
      snapshot_as_of: snapshotAsOf,
      opportunity_id: opportunityId,
      context_fingerprint: fingerprintValue,
      cached_at: new Date().toISOString(),
      decision,
    },
    ...existing,
  ])
}

export async function hydrateCachedAiDecisions(
  cards: TodayActionCard[],
): Promise<TodayActionCard[]> {
  const snapshotAsOf = await getSnapshotAsOf()
  if (!snapshotAsOf) return cards
  return cards.map((card) => {
    if (
      card.model_decision_status === 'NOT_ELIGIBLE' ||
      card.model_decision_status === 'BLOCKED_GROUNDING'
    ) {
      return card
    }
    const decision = findCachedDecision(
      card.opportunity_id,
      snapshotAsOf,
      decisionFingerprint(card),
    )
    if (!decision) return card
    return {
      ...card,
      model_decision_status: 'READY',
      model_block_reason: null,
      decision,
    }
  })
}

export async function requestAiDecision(card: TodayActionCard): Promise<Decision> {
  if (
    card.model_decision_status === 'NOT_ELIGIBLE' ||
    card.model_decision_status === 'BLOCKED_GROUNDING'
  ) {
    throw new AiDecisionError('OPPORTUNITY_WINDOW_CLOSED', 409)
  }

  const snapshotAsOf = await getSnapshotAsOf()
  const customerContext = customerContextPayload(card)
  const fingerprintValue = decisionFingerprint(card)
  if (snapshotAsOf) {
    const cached = findCachedDecision(card.opportunity_id, snapshotAsOf, fingerprintValue)
    if (cached) return cached
  }

  const response = await fetch('/api/ai/analyze', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
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
  if (!decision) {
    throw new AiDecisionError('AI_RESPONSE_INVALID', 502)
  }

  if (snapshotAsOf) {
    cacheDecision(card.opportunity_id, snapshotAsOf, fingerprintValue, decision)
  }
  return decision
}
