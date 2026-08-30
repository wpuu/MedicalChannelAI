import type {
  FollowUpRecord,
  TodayActionCard,
  TodaySummaryStats,
} from "../types/today-actions";
import { TODAY_ACTIONS_MOCK } from "../mock/today-actions.mock";
import type { TodayActionsService } from "./TodayActionsService";

const SIMULATED_LATENCY_MS = 180;

function delay<T>(value: T, ms = SIMULATED_LATENCY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

/**
 * Mock 实现：数据存储在内存中，模拟真实异步服务的调用方式。
 * 后续可增加 ApiTodayActionsService 实现同一接口，页面代码无需改动。
 */
export class MockTodayActionsService implements TodayActionsService {
  // 使用深拷贝作为“内存数据库”，允许 Demo 内的交互（如新增跟进记录）持久化于当前会话
  private data: TodayActionCard[] = JSON.parse(JSON.stringify(TODAY_ACTIONS_MOCK));

  async getTodayActions(): Promise<TodayActionCard[]> {
    const sorted = [...this.data].sort((a, b) => a.rank - b.rank).slice(0, 5);
    return delay(sorted);
  }

  async getOpportunityById(opportunityId: string): Promise<TodayActionCard | undefined> {
    const found = this.data.find((item) => item.opportunity_id === opportunityId);
    return delay(found);
  }

  async getSummaryStats(): Promise<TodaySummaryStats> {
    const total_candidates = this.data.length;
    const matched_opportunities = this.data.filter(
      (item) => item.match_status === "MATCHED" || item.match_status === "PARTIAL"
    ).length;
    const today_focus = this.data.filter(
      (item) => item.priority.tier === "立即关注" || item.priority.tier === "重点跟进"
    ).length;
    const awaiting_ai = this.data.filter((item) => item.model_decision_status !== "READY").length;

    return delay({ total_candidates, matched_opportunities, today_focus, awaiting_ai });
  }

  async addFollowUpRecord(
    opportunityId: string,
    record: Omit<FollowUpRecord, "id" | "timestamp">
  ): Promise<FollowUpRecord> {
    const target = this.data.find((item) => item.opportunity_id === opportunityId);
    const newRecord: FollowUpRecord = {
      ...record,
      id: `f-${opportunityId}-${Date.now()}`,
      timestamp: new Date().toLocaleString("zh-CN", { hour12: false }),
    };
    if (target) {
      target.follow_up_records = [newRecord, ...target.follow_up_records];
    }
    return delay(newRecord, 100);
  }
}

// 单例导出，方便页面直接使用；未来切换为 ApiTodayActionsService 时只需替换此处
export const todayActionsService: TodayActionsService = new MockTodayActionsService();
