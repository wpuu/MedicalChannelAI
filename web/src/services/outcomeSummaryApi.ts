import type { LostReason, NotFitReason, WonReason } from '@/types'
import { apiBaseUrl, isApiMode } from './apiConfig'
import { listStoredFollowups } from './localFollowupStore'

export interface OutcomeReasonCount {
  code: string
  label: string
  count: number
}

export interface PrivateOutcomeSummary {
  total_terminal: number
  won: number
  lost: number
  not_fit: number
  decided_count: number
  win_rate_percent: number | null
  won_reason_counts: OutcomeReasonCount[]
  lost_reason_counts: OutcomeReasonCount[]
  not_fit_reason_counts: OutcomeReasonCount[]
  unclassified_won: number
  unclassified_lost: number
  unclassified_not_fit: number
}

const WON_CODE_TO_LABEL: Record<string, WonReason> = {
  PRODUCT_OR_SPEC_MATCH: '产品或参数匹配',
  MANUFACTURER_OR_AUTHORIZATION_ADVANTAGE: '厂家/授权资源有优势',
  RELATIONSHIP_OR_COMMUNICATION_EFFECTIVE: '医院关系或沟通推进有效',
  PRICE_OR_COMMERCIAL_ADVANTAGE: '价格或商务条件有优势',
  INTERVENTION_TIMING_GOOD: '介入时机合适',
  BID_OR_RESPONSE_EXECUTION_STRONG: '投标/响应执行到位',
  SOLUTION_DEMAND_MATCH: '方案与客户需求匹配',
  OTHER: '其他',
}

const NOT_FIT_CODE_TO_LABEL: Record<string, NotFitReason> = {
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

const LOST_CODE_TO_LABEL: Record<string, LostReason> = {
  PRICE_OR_QUOTE_LOST: '价格/报价竞争失败',
  PRODUCT_OR_SPEC_MISMATCH: '产品或参数不匹配',
  MANUFACTURER_OR_AUTHORIZATION_GAP: '厂家/授权资源不足',
  HOSPITAL_RELATIONSHIP_GAP: '医院关系不足',
  INTERVENTION_TOO_LATE: '介入时间太晚',
  COMPETITOR_ADVANTAGE: '竞争对手优势明显',
  BID_OR_RESPONSE_EXECUTION_FAILED: '投标/响应执行失败',
  CUSTOMER_OR_PROJECT_CHANGED: '客户需求或项目变化',
  WITHDRAWN_BY_USER: '主动放弃',
  OTHER: '其他',
}

const WON_LABEL_TO_CODE = new Map(
  Object.entries(WON_CODE_TO_LABEL).map(([code, label]) => [label, code]),
)
const NOT_FIT_LABEL_TO_CODE = new Map(
  Object.entries(NOT_FIT_CODE_TO_LABEL).map(([code, label]) => [label, code]),
)
const LOST_LABEL_TO_CODE = new Map(
  Object.entries(LOST_CODE_TO_LABEL).map(([code, label]) => [label, code]),
)
const WON_NOTE_PREFIX = '成交复盘（当前用户判断）：'
const LOST_NOTE_PREFIX = '未成交原因（当前用户判断）：'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function nonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function parseReasonCounts(
  value: unknown,
  labels: Record<string, string>,
): OutcomeReasonCount[] {
  if (!Array.isArray(value)) throw new Error('OUTCOME_SUMMARY_INVALID')
  const seen = new Set<string>()
  return value.map((item) => {
    const row = asRecord(item)
    if (
      !row ||
      Object.keys(row).length !== 2 ||
      typeof row.code !== 'string' ||
      !labels[row.code] ||
      seen.has(row.code) ||
      !nonNegativeInteger(row.count) ||
      row.count === 0
    ) {
      throw new Error('OUTCOME_SUMMARY_INVALID')
    }
    seen.add(row.code)
    return { code: row.code, label: labels[row.code], count: row.count }
  })
}

function reasonCountTotal(items: OutcomeReasonCount[]): number {
  return items.reduce((total, item) => total + item.count, 0)
}

function parseSummary(value: unknown): PrivateOutcomeSummary {
  const root = asRecord(value)
  if (
    !root ||
    root.schema_version !== '0.1' ||
    root.mode !== 'PRIVATE_OUTCOME_SUMMARY' ||
    !nonNegativeInteger(root.total_terminal) ||
    !nonNegativeInteger(root.won) ||
    !nonNegativeInteger(root.lost) ||
    !nonNegativeInteger(root.not_fit) ||
    !nonNegativeInteger(root.decided_count) ||
    !(root.win_rate_percent === null ||
      (nonNegativeInteger(root.win_rate_percent) && root.win_rate_percent <= 100)) ||
    !nonNegativeInteger(root.unclassified_won) ||
    !nonNegativeInteger(root.unclassified_lost) ||
    !nonNegativeInteger(root.unclassified_not_fit)
  ) {
    throw new Error('OUTCOME_SUMMARY_INVALID')
  }

  if (
    root.total_terminal !== root.won + root.lost + root.not_fit ||
    root.decided_count !== root.won + root.lost
  ) {
    throw new Error('OUTCOME_SUMMARY_INVALID')
  }

  const wonReasonCounts = parseReasonCounts(root.won_reason_counts, WON_CODE_TO_LABEL)
  const lostReasonCounts = parseReasonCounts(root.lost_reason_counts, LOST_CODE_TO_LABEL)
  const notFitReasonCounts = parseReasonCounts(root.not_fit_reason_counts, NOT_FIT_CODE_TO_LABEL)
  if (
    reasonCountTotal(wonReasonCounts) + root.unclassified_won !== root.won ||
    reasonCountTotal(lostReasonCounts) + root.unclassified_lost !== root.lost ||
    reasonCountTotal(notFitReasonCounts) + root.unclassified_not_fit !== root.not_fit
  ) {
    throw new Error('OUTCOME_SUMMARY_INVALID')
  }

  return {
    total_terminal: root.total_terminal,
    won: root.won,
    lost: root.lost,
    not_fit: root.not_fit,
    decided_count: root.decided_count,
    win_rate_percent: root.win_rate_percent as number | null,
    won_reason_counts: wonReasonCounts,
    lost_reason_counts: lostReasonCounts,
    not_fit_reason_counts: notFitReasonCounts,
    unclassified_won: root.unclassified_won,
    unclassified_lost: root.unclassified_lost,
    unclassified_not_fit: root.unclassified_not_fit,
  }
}

function localReasonCode(
  status: 'WON' | 'LOST' | 'NOT_FIT',
  history: ReturnType<typeof listStoredFollowups>[number]['entry']['history'],
): string | null {
  if (status === 'NOT_FIT') {
    for (const event of history) {
      if (event.status !== 'NOT_FIT' || !event.reason) continue
      const direct = NOT_FIT_LABEL_TO_CODE.get(event.reason as NotFitReason)
      if (direct) return direct
      if (NOT_FIT_CODE_TO_LABEL[event.reason]) return event.reason
    }
    return null
  }

  if (status === 'WON') {
    for (const event of history) {
      if (event.status !== 'WON') continue
      if (event.reason) {
        const direct = WON_LABEL_TO_CODE.get(event.reason as WonReason)
        if (direct) return direct
        if (WON_CODE_TO_LABEL[event.reason]) return event.reason
      }
      const note = event.note?.trim()
      if (!note?.startsWith(WON_NOTE_PREFIX)) continue
      const code = WON_LABEL_TO_CODE.get(note.slice(WON_NOTE_PREFIX.length).trim() as WonReason)
      if (code) return code
    }
    return null
  }

  for (const event of history) {
    if (event.status !== 'LOST') continue
    if (event.reason) {
      const direct = LOST_LABEL_TO_CODE.get(event.reason as LostReason)
      if (direct) return direct
      if (LOST_CODE_TO_LABEL[event.reason]) return event.reason
    }
    const note = event.note?.trim()
    if (!note?.startsWith(LOST_NOTE_PREFIX)) continue
    const code = LOST_LABEL_TO_CODE.get(note.slice(LOST_NOTE_PREFIX.length).trim() as LostReason)
    if (code) return code
  }
  return null
}

function localSummary(): PrivateOutcomeSummary {
  let won = 0
  let lost = 0
  let notFit = 0
  let unclassifiedWon = 0
  let unclassifiedLost = 0
  let unclassifiedNotFit = 0
  const wonReasons = new Map<string, number>()
  const lostReasons = new Map<string, number>()
  const notFitReasons = new Map<string, number>()

  for (const { entry } of listStoredFollowups()) {
    if (entry.status === 'WON') {
      won += 1
      const code = localReasonCode('WON', entry.history)
      if (code) wonReasons.set(code, (wonReasons.get(code) ?? 0) + 1)
      else unclassifiedWon += 1
      continue
    }
    if (entry.status === 'LOST') {
      lost += 1
      const code = localReasonCode('LOST', entry.history)
      if (code) lostReasons.set(code, (lostReasons.get(code) ?? 0) + 1)
      else unclassifiedLost += 1
      continue
    }
    if (entry.status === 'NOT_FIT') {
      notFit += 1
      const code = localReasonCode('NOT_FIT', entry.history)
      if (code) notFitReasons.set(code, (notFitReasons.get(code) ?? 0) + 1)
      else unclassifiedNotFit += 1
    }
  }

  const toCounts = (counter: Map<string, number>, labels: Record<string, string>) =>
    [...counter.entries()]
      .map(([code, count]) => ({ code, label: labels[code], count }))
      .filter((item): item is OutcomeReasonCount => Boolean(item.label))
      .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))

  const decidedCount = won + lost
  return {
    total_terminal: won + lost + notFit,
    won,
    lost,
    not_fit: notFit,
    decided_count: decidedCount,
    win_rate_percent: decidedCount ? Math.round((won / decidedCount) * 100) : null,
    won_reason_counts: toCounts(wonReasons, WON_CODE_TO_LABEL),
    lost_reason_counts: toCounts(lostReasons, LOST_CODE_TO_LABEL),
    not_fit_reason_counts: toCounts(notFitReasons, NOT_FIT_CODE_TO_LABEL),
    unclassified_won: unclassifiedWon,
    unclassified_lost: unclassifiedLost,
    unclassified_not_fit: unclassifiedNotFit,
  }
}

async function responseError(response: Response): Promise<Error> {
  try {
    const root = asRecord(await response.json())
    if (typeof root?.error === 'string') return new Error(root.error)
  } catch {
    // Fall through to status-only error.
  }
  return new Error(`HTTP_${response.status}`)
}

export async function getPrivateOutcomeSummary(): Promise<PrivateOutcomeSummary> {
  if (!isApiMode) return localSummary()
  const response = await fetch(`${apiBaseUrl}/profile?route=outcome-summary`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await responseError(response)
  return parseSummary(await response.json())
}
