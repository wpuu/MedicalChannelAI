import type { TodayActionCard } from '@/types'

const DEADLINE_URGENCY_MAX_POINTS = 10
const PUBLICATION_FRESHNESS_MAX_POINTS = 7
const DAY_MS = 24 * 60 * 60 * 1000

function parsedTime(value: string | null | undefined): number | null {
  if (!value) return null
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? null : timestamp
}

function tianjinDateKey(now: number): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(now))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function validDateOnly(value: string | null | undefined): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  ) return null
  return value
}

function tianjinDateEndMs(value: string): number | null {
  const dateOnly = validDateOnly(value)
  if (!dateOnly) return null
  const timestamp = Date.parse(`${dateOnly}T23:59:59.999+08:00`)
  return Number.isNaN(timestamp) ? null : timestamp
}

function nextActionDeadline(card: TodayActionCard, now: number): number | null {
  const registration = parsedTime(card.facts.registration_deadline)
  if (registration !== null && registration > now) return registration

  const registrationDate = validDateOnly(card.facts.registration_deadline_date)
  if (registration === null && registrationDate !== null && registrationDate >= tianjinDateKey(now)) {
    const end = tianjinDateEndMs(registrationDate)
    if (end !== null && end > now) return end
  }

  const bid = parsedTime(card.facts.bid_deadline)
  return bid !== null && bid > now ? bid : null
}

function deadlineUrgencyPoints(card: TodayActionCard, now: number): number {
  const deadline = nextActionDeadline(card, now)
  if (deadline === null) return 0
  const hoursLeft = (deadline - now) / 3_600_000
  if (hoursLeft <= 24) return 10
  if (hoursLeft <= 72) return 9
  if (hoursLeft <= 7 * 24) return 7
  if (hoursLeft <= 14 * 24) return 5
  if (hoursLeft <= 30 * 24) return 3
  return 1
}

function publicationFreshnessPoints(card: TodayActionCard, now: number): number {
  const published = validDateOnly(card.facts.publish_date?.slice(0, 10))
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

function percentToPoints(percent: number | undefined, maxPoints: number): number {
  const value = Number(percent ?? 0)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(maxPoints, Math.round((value / 100) * maxPoints)))
}

function pointsToPercent(points: number, maxPoints: number): number {
  return Math.max(0, Math.min(100, Math.round((points / maxPoints) * 100)))
}

export function refreshTrialTemporalPriority(
  card: TodayActionCard,
  now = Date.now(),
): TodayActionCard {
  const oldUrgency = percentToPoints(
    card.priority.components.DEADLINE_URGENCY,
    DEADLINE_URGENCY_MAX_POINTS,
  )
  const oldFreshness = percentToPoints(
    card.priority.components.PUBLICATION_FRESHNESS,
    PUBLICATION_FRESHNESS_MAX_POINTS,
  )
  const newUrgency = deadlineUrgencyPoints(card, now)
  const newFreshness = publicationFreshnessPoints(card, now)
  const score = Math.max(
    0,
    Math.min(100, card.priority.score - oldUrgency - oldFreshness + newUrgency + newFreshness),
  )

  return {
    ...card,
    priority: {
      ...card.priority,
      score,
      components: {
        ...card.priority.components,
        DEADLINE_URGENCY: pointsToPercent(newUrgency, DEADLINE_URGENCY_MAX_POINTS),
        PUBLICATION_FRESHNESS: pointsToPercent(newFreshness, PUBLICATION_FRESHNESS_MAX_POINTS),
      },
    },
  }
}

export function rerankTrialTemporalCards(cards: TodayActionCard[], now: number): TodayActionCard[] {
  return cards
    .map((card) => refreshTrialTemporalPriority(card, now))
    .sort((left, right) => {
      const scoreDifference = right.priority.score - left.priority.score
      if (scoreDifference) return scoreDifference
      const leftDeadline = nextActionDeadline(left, now) ?? Number.POSITIVE_INFINITY
      const rightDeadline = nextActionDeadline(right, now) ?? Number.POSITIVE_INFINITY
      if (leftDeadline !== rightDeadline) return leftDeadline - rightDeadline
      return left.rank - right.rank
    })
    .map((card, index) => ({ ...card, rank: index + 1 }))
}
