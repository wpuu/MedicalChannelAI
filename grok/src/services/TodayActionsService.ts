import type {
  CardActionState,
  CommunicationScript,
  FollowUpAction,
  FollowUpRecord,
  TodayActionCard,
  TodayActionsPayload,
  TodayActionsSummary,
} from "@/types/today-actions";

export interface TodayActionsService {
  getTodayPayload(): Promise<TodayActionsPayload>;
  getTodaySummary(): Promise<TodayActionsSummary>;
  getTodayCards(): Promise<TodayActionCard[]>;
  getOpportunity(id: string): Promise<TodayActionCard | null>;
  getFollowUps(opportunityId: string): Promise<FollowUpRecord[]>;
  addFollowUp(
    opportunityId: string,
    action: FollowUpAction,
    note: string,
    remindAt?: string | null,
  ): Promise<FollowUpRecord>;
  getActionState(opportunityId: string): Promise<CardActionState>;
  setActionState(
    opportunityId: string,
    action: FollowUpAction,
    remindAt?: string | null,
  ): Promise<CardActionState>;
  generateScript(opportunityId: string): Promise<CommunicationScript>;
}
