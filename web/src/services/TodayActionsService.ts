import type {
  FollowupInput,
  OutreachDraft,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'

export interface TodayActionsLoadOptions {
  hydrateFollowups?: boolean
}

export interface TodayActionsService {
  getTodayActions(options?: TodayActionsLoadOptions): Promise<TodayActionsResponse>
  getOpportunity(id: string): Promise<TodayActionCard | null>
  updateFollowup(id: string, input: FollowupInput): Promise<void>
  requestOutreachDraft(id: string): Promise<OutreachDraft>
}
