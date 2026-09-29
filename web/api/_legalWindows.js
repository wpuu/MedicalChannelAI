// Runtime refresher for the statutory challenge windows (质疑期) that the
// Python snapshot builder derives per card (see
// web/pipeline/medical_channel_pipeline/legal_windows.py — the canonical
// implementation and the only place that owns the holiday table).
//
// The snapshot embeds the working-day calendar (`snapshot.working_calendar`),
// so this module never hard-codes holidays. Between two daily snapshot builds
// it only recomputes `remaining_working_days` and `status`; the anchor and
// deadline dates are left untouched because they come from the notice facts.
//
// Everything here is an estimate under 财政部令第94号 — never an official
// deadline. The UI is responsible for labelling it that way.

const DAY_MS = 24 * 60 * 60 * 1000
const MAX_SPAN_DAYS = 4000

function tianjinDateKey(nowMs) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(nowMs))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function dateKeyToUtcMs(key) {
  if (typeof key !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(key)) return null
  const [year, month, day] = key.split('-').map(Number)
  const ms = Date.UTC(year, month - 1, day)
  const check = new Date(ms)
  if (check.getUTCFullYear() !== year || check.getUTCMonth() + 1 !== month || check.getUTCDate() !== day) return null
  return ms
}

function utcMsToDateKey(ms) {
  return new Date(ms).toISOString().slice(0, 10)
}

export function normalizeWorkingCalendar(calendar) {
  const holidays = new Set(Array.isArray(calendar?.holidays) ? calendar.holidays.filter((v) => typeof v === 'string') : [])
  const adjusted = new Set(
    Array.isArray(calendar?.adjusted_workdays) ? calendar.adjusted_workdays.filter((v) => typeof v === 'string') : [],
  )
  return { holidays, adjustedWorkdays: adjusted, official: holidays.size > 0 }
}

export function isWorkingDay(dateKey, calendar) {
  const normalized = calendar?.holidays instanceof Set ? calendar : normalizeWorkingCalendar(calendar)
  if (normalized.adjustedWorkdays.has(dateKey)) return true
  if (normalized.holidays.has(dateKey)) return false
  const ms = dateKeyToUtcMs(dateKey)
  if (ms === null) return false
  const weekday = new Date(ms).getUTCDay()
  return weekday !== 0 && weekday !== 6
}

// Working days d with today <= d <= deadline; 0 once the deadline has passed.
export function workingDaysRemaining(todayKey, deadlineKey, calendar) {
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

export function refreshLegalWindows(legalWindows, now = Date.now(), calendar = null) {
  if (!Array.isArray(legalWindows)) return legalWindows ?? null
  const todayKey = tianjinDateKey(now)
  return legalWindows.map((item) => {
    if (!item || typeof item !== 'object' || dateKeyToUtcMs(item.deadline_date) === null) return item
    const remaining = workingDaysRemaining(todayKey, item.deadline_date, calendar)
    return {
      ...item,
      remaining_working_days: remaining,
      status: remaining > 0 ? 'OPEN' : 'CLOSED',
    }
  })
}
