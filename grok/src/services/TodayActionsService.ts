import type {
  FollowupInput,
  OutreachDraft,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'

export interface TodayActionsService {
  getTodayActions(): Promise<TodayActionsResponse>
  getOpportunity(id: string): Promise<TodayActionCard | null>
  updateFollowup(id: string, input: FollowupInput): Promise<void>
  requestOutreachDraft(id: string): Promise<OutreachDraft>
}
