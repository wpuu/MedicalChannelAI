import type { LegalWindow, TodayActionCard, WorkingCalendar } from '@/types'

/**
 * Browser twin of web/api/_legalWindows.js. The holiday table itself is owned by
 * pipeline/medical_channel_pipeline/legal_windows.py and arrives embedded in the
 * snapshot (`working_calendar`); this file never hard-codes holidays.
 *
 * Everything here is an estimate under 财政部令第94号 — the UI must always
 * render LEGAL_WINDOW_DISCLAIMER next to these figures.
 */

const DAY_MS = 24 * 60 * 60 * 1000
const MAX_SPAN_DAYS = 4000

export const LEGAL_WINDOW_DISCLAIMER =
  '按《政府采购质疑和投诉办法》（财政部令第94号）以工作日推算，非官方截止时间；以采购文件、公告及财政部门答复为准。'

export const LEGAL_WINDOW_LABELS: Record<LegalWindow['code'], string> = {
  DOCUMENT_CHALLENGE: '招标文件质疑期',
  RESULT_CHALLENGE: '中标/成交结果质疑期',
}

export const LEGAL_WINDOW_BASIS_NOTES: Record<LegalWindow['code'], string> = {
  DOCUMENT_CHALLENGE:
    '自获取招标文件截止日起 7 个工作日（94号令第十一条）。若您更早获取文件，应自获取之日起算，实际截止会更早。',
  RESULT_CHALLENGE:
    '自中标/成交公告期限届满之日（公告发布后 1 个工作日，87号令第六十九条）起 7 个工作日（94号令第十条、实施条例第五十三条）。',
}

export const COMPLAINT_RULE_NOTE =
  '质疑后采购人/代理机构应在 7 个工作日内答复（94号令第十三条）；对答复不满意或逾期未答复，可在答复期满后 15 个工作日内向同级财政部门投诉（第十七条）。'

interface NormalizedCalendar {
  holidays: Set<string>
  adjustedWorkdays: Set<string>
}

function tianjinDateKey(nowMs: number): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(nowMs))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function dateKeyToUtcMs(key: unknown): number | null {
  if (typeof key !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(key)) return null
  const [year, month, day] = key.split('-').map(Number)
  const ms = Date.UTC(year, month - 1, day)
  const check = new Date(ms)
  if (check.getUTCFullYear() !== year || check.getUTCMonth() + 1 !== month || check.getUTCDate() !== day) {
    return null
  }
  return ms
}

function utcMsToDateKey(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10)
}

export function normalizeWorkingCalendar(calendar: WorkingCalendar | null | undefined): NormalizedCalendar {
  return {
    holidays: new Set(Array.isArray(calendar?.holidays) ? calendar.holidays : []),
    adjustedWorkdays: new Set(Array.isArray(calendar?.adjusted_workdays) ? calendar.adjusted_workdays : []),
  }
}

export function isWorkingDay(dateKey: string, calendar: NormalizedCalendar): boolean {
  if (calendar.adjustedWorkdays.has(dateKey)) return true
  if (calendar.holidays.has(dateKey)) return false
  const ms = dateKeyToUtcMs(dateKey)
  if (ms === null) return false
  const weekday = new Date(ms).getUTCDay()
  return weekday !== 0 && weekday !== 6
}

/** Working days d with today <= d <= deadline; 0 once the deadline has passed. */
export function workingDaysRemaining(
  todayKey: string,
  deadlineKey: string,
  calendar: WorkingCalendar | null | undefined,
): number {
  const todayMs = dateKeyToUtcMs(todayKey)
  const deadlineMs = dateKeyToUtcMs(deadlineKey)
  if (todayMs === null || deadlineMs === null || deadlineMs < todayMs) return 0
  const normalized = normalizeWorkingCalendar(calendar)
  let count = 0
  let guard = 0
  for (let ms = todayMs; ms <= deadlineMs && guard < MAX_SPAN_DAYS; ms += DAY_MS, guard += 1) {
    if (isWorkingDay(utcMsToDateKey(ms), normalized)) count += 1
  }
  return count
}

export function refreshLegalWindows(
  windows: LegalWindow[] | null | undefined,
  now: number,
  calendar: WorkingCalendar | null | undefined,
): LegalWindow[] | null {
  if (!Array.isArray(windows)) return null
  const todayKey = tianjinDateKey(now)
  return windows.map((item) => {
    if (dateKeyToUtcMs(item.deadline_date) === null) return item
    const remaining = workingDaysRemaining(todayKey, item.deadline_date, calendar)
    return { ...item, remaining_working_days: remaining, status: remaining > 0 ? 'OPEN' : 'CLOSED' }
  })
}

export function primaryLegalWindow(card: Pick<TodayActionCard, 'legal_windows'>): LegalWindow | null {
  const windows = Array.isArray(card.legal_windows) ? card.legal_windows : []
  return windows.find((item) => item.status === 'OPEN') ?? windows[0] ?? null
}

function shortDate(dateKey: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateKey)
  if (!match) return dateKey
  return `${Number(match[2])}月${Number(match[3])}日`
}

export interface LegalWindowSummary {
  code: LegalWindow['code']
  label: string
  status: LegalWindow['status']
  remaining: number
  deadlineText: string
  /** One-line, action-oriented sentence for cards. */
  headline: string
  basisNote: string
  estimateOnly: boolean
}

export function legalWindowSummary(card: Pick<TodayActionCard, 'legal_windows'>): LegalWindowSummary | null {
  const window = primaryLegalWindow(card)
  if (!window) return null
  const label = LEGAL_WINDOW_LABELS[window.code] ?? '质疑期'
  const deadlineText = shortDate(window.deadline_date)
  const remaining = window.remaining_working_days
  let headline: string
  if (window.status !== 'OPEN' || remaining <= 0) {
    headline = `${label}已过（推算截止 ${deadlineText}）`
  } else if (remaining === 1) {
    headline = `${label}今天是最后一个工作日（推算截止 ${deadlineText}）`
  } else {
    headline = `${label}还剩 ${remaining} 个工作日（推算最晚 ${deadlineText}）`
  }
  return {
    code: window.code,
    label,
    status: window.status,
    remaining,
    deadlineText,
    headline,
    basisNote: LEGAL_WINDOW_BASIS_NOTES[window.code] ?? '',
    estimateOnly: Boolean(window.calendar),
  }
}
