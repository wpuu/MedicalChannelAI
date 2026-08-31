import type { TodayActionCard } from '@/types'

const SNAPSHOT_STALE_AFTER_MS = 24 * 60 * 60 * 1000
const INTERVENTION_MAX_POINTS = 30
const LATE_WINDOW_POINTS = 6

export interface RuntimeFreshnessState {
  card: TodayActionCard
  activeToday: boolean
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

function interventionPoints(card: TodayActionCard): number {
  return Math.round(
    (Math.max(0, Math.min(100, card.priority.components.INTERVENTION_STAGE)) / 100) *
      INTERVENTION_MAX_POINTS,
  )
}

function withInterventionPoints(card: TodayActionCard, points: number): TodayActionCard {
  const previous = interventionPoints(card)
  const next = Math.max(0, Math.min(INTERVENTION_MAX_POINTS, points))
  return {
    ...card,
    priority: {
      ...card.priority,
      score: Math.max(0, Math.min(100, card.priority.score - previous + next)),
      components: {
        ...card.priority.components,
        INTERVENTION_STAGE: Math.round((next / INTERVENTION_MAX_POINTS) * 100),
      },
    },
  }
}

export function applyRuntimeFreshness(
  card: TodayActionCard,
  nowMs = Date.now(),
): RuntimeFreshnessState {
  const registrationDeadline = parseTime(card.facts.registration_deadline)
  const bidDeadline = parseTime(card.facts.bid_deadline)

  const bidClosed = bidDeadline !== null && bidDeadline <= nowMs
  const registrationOnlyClosed =
    bidDeadline === null && registrationDeadline !== null && registrationDeadline <= nowMs

  if (bidClosed || registrationOnlyClosed) {
    const archived = withInterventionPoints(card, 0)
    return {
      activeToday: false,
      card: {
        ...archived,
        match_status: 'ARCHIVE',
        recommendation_mode: 'ARCHIVE',
        model_decision_status: 'NOT_ELIGIBLE',
        model_block_reason: '公开截止时间已过，当前仅保留事实与历史跟进记录。',
        decision: null,
      },
    }
  }

  const lateWindow =
    registrationDeadline !== null &&
    registrationDeadline <= nowMs &&
    bidDeadline !== null &&
    bidDeadline > nowMs

  if (lateWindow) {
    const downgraded = withInterventionPoints(
      card,
      Math.min(interventionPoints(card), LATE_WINDOW_POINTS),
    )
    return {
      activeToday: true,
      card: {
        ...downgraded,
        match_status: 'LATE_WINDOW',
        recommendation_mode: 'LATE_WINDOW',
        decision: null,
        model_decision_status:
          card.model_decision_status === 'NOT_ELIGIBLE' ||
          card.model_decision_status === 'BLOCKED_GROUNDING'
            ? card.model_decision_status
            : 'AWAITING_MODEL',
      },
    }
  }

  return {
    activeToday: true,
    card: { ...card },
  }
}

export function runtimeCoverageWarning(
  baseWarning: string,
  snapshotAsOf: string,
  nowMs = Date.now(),
): string {
  const snapshotMs = parseTime(snapshotAsOf)
  if (snapshotMs === null) return baseWarning
  const ageMs = Math.max(0, nowMs - snapshotMs)
  if (ageMs >= SNAPSHOT_STALE_AFTER_MS) {
    const ageHours = Math.floor(ageMs / (60 * 60 * 1000))
    return `${baseWarning} · 当前公开快照约 ${ageHours} 小时未更新，可能漏掉最新项目；系统已按当前时间自动剔除已截止项目。`
  }
  return `${baseWarning} · 系统会按当前时间自动校验报名/投标截止窗口。`
}
