import type { FollowUpRecord, TodayActionCard, TodaySummaryStats } from "../types/today-actions";

/**
 * Today Actions 数据服务抽象接口。
 * 页面层只依赖该接口，不直接访问 Mock 数据。
 * 未来接入真实后端时，实现 ApiTodayActionsService 即可无缝替换。
 */
export interface TodayActionsService {
  /** 获取今日行动卡片列表（最多5条） */
  getTodayActions(): Promise<TodayActionCard[]>;

  /** 根据商机ID获取单条详情 */
  getOpportunityById(opportunityId: string): Promise<TodayActionCard | undefined>;

  /** 获取今日概览统计数据 */
  getSummaryStats(): Promise<TodaySummaryStats>;

  /** 追加一条销售跟进记录 */
  addFollowUpRecord(
    opportunityId: string,
    record: Omit<FollowUpRecord, "id" | "timestamp">
  ): Promise<FollowUpRecord>;
}
