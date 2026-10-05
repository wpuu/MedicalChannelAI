import type {
  FollowupInput,
  OutreachDraft,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'
import { outreachBudgetFactText } from '@/utils/outreachBudgetFact'
import type { TodayActionsService } from './TodayActionsService'
import { refreshTrialTemporalPriority, rerankTrialTemporalCards } from './trialTemporalPriority'

export { refreshTrialTemporalPriority } from './trialTemporalPriority'

const MAX_TODAY_CARDS = 5
function normalizeTrialOutreachBudget(draft: OutreachDraft, card: TodayActionCard | null): OutreachDraft {
  const budgetFact = outreachBudgetFactText(card?.facts.budget)
  if (!budgetFact) return draft
  return {
    ...draft,
    draft: draft.draft.replace(/项目预算约\d+(?:\.\d+)?万元/, budgetFact),
  }
}

export class RuntimeTrialTodayActionsService implements TodayActionsService {
  constructor(private readonly delegate: TodayActionsService) {}

  async getTodayActions(): Promise<TodayActionsResponse> {
    const data = await this.delegate.getTodayActions()
    const now = Date.now()
    const pool = rerankTrialTemporalCards(data.opportunity_pool?.length ? data.opportunity_pool : data.cards, now)
    const cards = pool.slice(0, MAX_TODAY_CARDS)
    return {
      ...data,
      matched_count: pool.length,
      card_count: cards.length,
      opportunity_pool_count: pool.length,
      cards,
      opportunity_pool: pool,
    }
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    const card = await this.delegate.getOpportunity(id)
    return card ? refreshTrialTemporalPriority(card) : null
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    return this.delegate.updateFollowup(id, input)
  }

  async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    const draft = await this.delegate.requestOutreachDraft(id)
    const card = await this.delegate.getOpportunity(id)
    return normalizeTrialOutreachBudget(draft, card)
  }
}
