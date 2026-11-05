import type { TodayActionCard } from '../types/index.ts'

interface ResearchEventFacts {
  research_event_at?: string | null
  research_event_text?: string | null
}

/** A published demonstration time closes actionability; it is not a bid/registration deadline. */
export function researchEventWindowClosed(facts: ResearchEventFacts, now = Date.now()): boolean {
  const value = facts.research_event_at
  if (value == null && facts.research_event_text == null) return false
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return true
  const timestamp = Date.parse(value)
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  if (Number.isNaN(timestamp) || Number(value.slice(11, 13)) > 23 || date.getUTCFullYear() !== year || date.getUTCMonth() + 1 !== month || date.getUTCDate() !== day) return true
  return timestamp <= now
}

export function archiveResearchEventCard(card: TodayActionCard): TodayActionCard {
  const stagePoints = Math.max(0, Math.round((card.priority.components.INTERVENTION_STAGE / 100) * 25))
  const urgencyPoints = Math.max(0, Math.round(((card.priority.components.DEADLINE_URGENCY ?? 0) / 100) * 10))
  return {
    ...card,
    match_status: 'ARCHIVE',
    recommendation_mode: 'ARCHIVE',
    model_decision_status: 'NOT_ELIGIBLE',
    model_block_reason: '公开现场调研时间已到或无法核验，当前仅保留事实与历史跟进记录。',
    decision: null,
    priority: {
      ...card.priority,
      score: Math.max(0, card.priority.score - stagePoints - urgencyPoints),
      components: { ...card.priority.components, INTERVENTION_STAGE: 0, DEADLINE_URGENCY: 0 },
    },
  }
}
