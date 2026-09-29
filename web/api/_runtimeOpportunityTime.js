import { refreshLegalWindows } from './_legalWindows.js'

const TIANJIN_TIME_ZONE = 'Asia/Shanghai'
const RELATIVE_REGISTRATION_WINDOW_7_DAYS = 'RELATIVE_REGISTRATION_WINDOW_7_DAYS'
const DAY_MS = 24 * 60 * 60 * 1000

function parsedTime(value) {
  if (typeof value !== 'string' || !value.trim()) return null
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? null : timestamp
}

function tianjinDateKey(now) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TIANJIN_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(now))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function validDateOnly(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  ) return null
  return value
}

function tianjinDateEndMs(value) {
  const dateOnly = validDateOnly(value)
  if (!dateOnly) return null
  const timestamp = Date.parse(`${dateOnly}T23:59:59.999+08:00`)
  return Number.isNaN(timestamp) ? null : timestamp
}

function relativeRegistrationDeadlineMs(facts) {
  const flags = new Set(Array.isArray(facts?.quality_flags) ? facts.quality_flags : [])
  if (!flags.has(RELATIVE_REGISTRATION_WINDOW_7_DAYS)) return null
  const published = validDateOnly(String(facts?.published_at || '').slice(0, 10))
  const publishedEnd = published ? tianjinDateEndMs(published) : null
  return publishedEnd === null ? null : publishedEnd + 7 * DAY_MS
}

function runtimeActionability(facts, now) {
  const bidDeadline = parsedTime(facts?.bid_deadline)
  const registrationDeadline = parsedTime(facts?.registration_deadline)
  const registrationDeadlineDate = validDateOnly(facts?.registration_deadline_date)
  const localDate = tianjinDateKey(now)

  if (bidDeadline !== null && bidDeadline <= now) {
    return { mode: 'ARCHIVE', interventionPoints: 0 }
  }

  if (registrationDeadline !== null && registrationDeadline <= now) {
    return bidDeadline === null
      ? { mode: 'ARCHIVE', interventionPoints: 0 }
      : { mode: 'LATE_WINDOW', interventionPoints: 8 }
  }

  if (
    registrationDeadline === null &&
    registrationDeadlineDate !== null &&
    registrationDeadlineDate < localDate
  ) {
    return bidDeadline === null
      ? { mode: 'ARCHIVE', interventionPoints: 0 }
      : { mode: 'LATE_WINDOW', interventionPoints: 8 }
  }

  const relativeDeadline = relativeRegistrationDeadlineMs(facts)
  if (relativeDeadline !== null && relativeDeadline <= now) {
    return { mode: 'ARCHIVE', interventionPoints: 0 }
  }

  return { mode: 'PUBLIC_OPPORTUNITY', interventionPoints: 25 }
}

function nextActionDeadlineMs(facts, now) {
  const registrationDeadline = parsedTime(facts?.registration_deadline)
  if (registrationDeadline !== null && registrationDeadline > now) return registrationDeadline

  const registrationDeadlineDate = validDateOnly(facts?.registration_deadline_date)
  if (registrationDeadline === null && registrationDeadlineDate !== null) {
    const localDate = tianjinDateKey(now)
    if (registrationDeadlineDate >= localDate) {
      const end = tianjinDateEndMs(registrationDeadlineDate)
      if (end !== null && end > now) return end
    }
  }

  const bidDeadline = parsedTime(facts?.bid_deadline)
  if (bidDeadline !== null && bidDeadline > now) return bidDeadline

  const relativeDeadline = relativeRegistrationDeadlineMs(facts)
  if (relativeDeadline !== null && relativeDeadline > now) return relativeDeadline
  return null
}

function deadlineUrgencyPoints(facts, now) {
  const deadline = nextActionDeadlineMs(facts, now)
  if (deadline === null) return 0
  const hoursLeft = (deadline - now) / 3_600_000
  if (hoursLeft <= 24) return 10
  if (hoursLeft <= 72) return 9
  if (hoursLeft <= 7 * 24) return 7
  if (hoursLeft <= 14 * 24) return 5
  if (hoursLeft <= 30 * 24) return 3
  return 1
}

function publicationFreshnessPoints(facts, now) {
  const published = validDateOnly(String(facts?.published_at || '').slice(0, 10))
  if (!published) return 0
  const localDate = tianjinDateKey(now)
  const publishedUtc = Date.parse(`${published}T00:00:00Z`)
  const localUtc = Date.parse(`${localDate}T00:00:00Z`)
  if (Number.isNaN(publishedUtc) || Number.isNaN(localUtc)) return 0
  const ageDays = Math.round((localUtc - publishedUtc) / DAY_MS)
  if (ageDays < 0) return 0
  if (ageDays <= 1) return 7
  if (ageDays <= 3) return 6
  if (ageDays <= 7) return 5
  if (ageDays <= 14) return 3
  if (ageDays <= 30) return 1
  return 0
}

function clampComponentPoints(component, points) {
  const max = Number(component?.max_points)
  const safeMax = Number.isFinite(max) && max >= 0 ? max : points
  return Math.max(0, Math.min(safeMax, points))
}

function refreshedPriority(priority, action, facts, now) {
  if (!priority || !Array.isArray(priority.components)) return priority
  const replacements = new Map([
    ['INTERVENTION_STAGE', action.interventionPoints],
    ['DEADLINE_URGENCY', deadlineUrgencyPoints(facts, now)],
    ['PUBLICATION_FRESHNESS', publicationFreshnessPoints(facts, now)],
  ])
  let score = Number(priority.score || 0)
  const components = priority.components.map((component) => {
    if (!replacements.has(component.code)) return { ...component }
    const nextPoints = clampComponentPoints(component, replacements.get(component.code))
    const previousPoints = Number(component.points || 0)
    score += nextPoints - previousPoints
    return {
      ...component,
      points: nextPoints,
      basis: component.code === 'INTERVENTION_STAGE' ? action.mode : component.basis,
    }
  })
  return {
    ...priority,
    score: Math.max(0, Math.min(100, score)),
    components,
  }
}

export function runtimeRefreshSnapshotCard(card, now = Date.now(), workingCalendar = null) {
  if (!card || typeof card !== 'object' || !card.facts) return null
  const action = runtimeActionability(card.facts, now)
  if (action.mode === 'ARCHIVE') return null

  const priority = refreshedPriority(card.priority, action, card.facts, now)
  const oldScore = Number(card.priority?.score || 0)
  const newScore = Number(priority?.score || oldScore)
  const temporalChanged = card.recommendation_mode !== action.mode || oldScore !== newScore
  const preserveBlock = ['BLOCKED_GROUNDING', 'NOT_ELIGIBLE'].includes(card.model_decision_status)

  const refreshed = {
    ...card,
    recommendation_mode: action.mode,
    priority,
    model_decision_status: temporalChanged && !preserveBlock ? 'AWAITING_MODEL' : card.model_decision_status,
    model_block_reason: temporalChanged && !preserveBlock ? null : card.model_block_reason,
    decision: temporalChanged ? null : card.decision,
  }
  // Derived 质疑期 countdown lives outside `facts` on purpose: facts stay the
  // verified public record, while the remaining-working-days figure is
  // recomputed on every request from the calendar embedded in the snapshot.
  if (Array.isArray(card.legal_windows)) {
    refreshed.legal_windows = refreshLegalWindows(card.legal_windows, now, workingCalendar)
  }
  return refreshed
}

function publishedSortTimestamp(facts) {
  const raw = String(facts?.published_at || '').trim()
  if (!raw) return 0
  const exact = parsedTime(raw)
  if (exact !== null) return exact
  const dateOnly = validDateOnly(raw.slice(0, 10))
  if (!dateOnly) return 0
  const timestamp = Date.parse(`${dateOnly}T00:00:00+08:00`)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

export function runtimeRefreshSnapshotPool(cards, now = Date.now(), workingCalendar = null) {
  const refreshed = (Array.isArray(cards) ? cards : [])
    .map((card) => runtimeRefreshSnapshotCard(card, now, workingCalendar))
    .filter(Boolean)

  return refreshed
    .sort((left, right) => {
      const scoreDifference = Number(right.priority?.score || 0) - Number(left.priority?.score || 0)
      if (scoreDifference) return scoreDifference
      const leftDeadline = nextActionDeadlineMs(left.facts, now) ?? Number.POSITIVE_INFINITY
      const rightDeadline = nextActionDeadlineMs(right.facts, now) ?? Number.POSITIVE_INFINITY
      if (leftDeadline !== rightDeadline) return leftDeadline - rightDeadline
      const publicationDifference = publishedSortTimestamp(right.facts) - publishedSortTimestamp(left.facts)
      if (publicationDifference) return publicationDifference
      return String(left.opportunity_id || '').localeCompare(String(right.opportunity_id || ''))
    })
    .map((card, index) => ({ ...card, rank: index + 1 }))
}
