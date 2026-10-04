import type { LegalWindow, TodayActionCard, WorkingCalendar } from '@/types'

/**
 * Browser twin of web/api/_legalWindows.js. The holiday table itself is owned by
 * pipeline/medical_channel_pipeline/legal_windows.py and arrives embedded in the
 * snapshot (`working_calendar`); this file never hard-codes holidays.
 *
 * Unverified rules and notice-specific anchors stay UNKNOWN; the UI must always
 * render LEGAL_WINDOW_DISCLAIMER next to these figures.
 */

const DAY_MS = 24 * 60 * 60 * 1000
const MAX_SPAN_DAYS = 4000

export const LEGAL_WINDOW_DISCLAIMER =
  '条件性推算，非官方截止时间；适用制度、法源及起算事实尚待核验，以官方原文及主管部门答复为准。'

export const LEGAL_WINDOW_LABELS: Record<LegalWindow['code'], string> = {
  DOCUMENT_CHALLENGE: '招标文件质疑期',
  RESULT_CHALLENGE: '中标/成交结果质疑期',
}

export const LEGAL_WINDOW_BASIS_NOTES: Record<LegalWindow['code'], string> = {
  DOCUMENT_CHALLENGE: '报名截止日不能证明法定起算日；文件获取事实及公告期限尚待核验。',
  RESULT_CHALLENGE: '结果发布日期不能单独证明适用制度或公告期限届满日。',
}

export const COMPLAINT_RULE_NOTE = '投诉规则的适用条件与起算事实尚待核验。'

interface NormalizedCalendar {
  holidays: Set<string>
  adjustedWorkdays: Set<string>
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
  _now: number,
  _calendar: WorkingCalendar | null | undefined,
): LegalWindow[] | null {
  if (!Array.isArray(windows)) return null
  return windows.map((item) => ({
    ...item,
    anchor_kind: 'UNVERIFIED',
    anchor_date: null,
    clock_start_date: undefined,
    deadline_date: null,
    remaining_working_days: 0,
    status: 'UNKNOWN',
    uncertainty_reason: 'APPLICABILITY_ANCHOR_AND_LEGAL_SOURCE_UNVERIFIED',
  }))
}

export function primaryLegalWindow(card: Pick<TodayActionCard, 'legal_windows'>): LegalWindow | null {
  const windows = Array.isArray(card.legal_windows) ? card.legal_windows : []
  return windows.find((item) => item.status === 'OPEN') ?? windows[0] ?? null
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
  // Older snapshots also lack verified legal applicability/anchor evidence.
  const deadlineText = '待核验'
  const remaining = 0
  const headline = `${label}：条件性推算 · 适用制度及起算待核验`

  return {
    code: window.code,
    label,
    status: 'UNKNOWN',
    remaining,
    deadlineText,
    headline,
    basisNote: LEGAL_WINDOW_BASIS_NOTES[window.code] ?? '',
    estimateOnly: true,
  }
}
