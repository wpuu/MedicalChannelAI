import type {
  TodayActionsResponse,
  TodayActionCard,
  FollowupInput,
  OutreachDraft,
  FollowupHistoryEntry,
} from '../types/opportunity';
import type { TodayActionsService } from './TodayActionsService';
import { todayActionsMock } from '../data/today-actions.mock';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const FOLLOWUP_ACTION_LABEL: Record<string, string> = {
  NEW: '新发现',
  REVIEWING: '正在评估',
  CONTACTED: '已联系',
  RELATIONSHIP_VERIFIED: '关系已确认',
  PREPARING: '准备中',
  BID_SUBMITTED: '已投标',
  WON: '已成交',
  LOST: '未成交',
  NOT_FIT: '不适合',
  MONITOR: '持续观察',
  ARCHIVED: '已归档',
};

function cloneResponse(): TodayActionsResponse {
  return JSON.parse(JSON.stringify(todayActionsMock)) as TodayActionsResponse;
}

/**
 * MockTodayActionsService
 * 首版本地数据服务：所有数据来自本地 Mock，跟进状态保存在内存中，
 * 刷新页面后会重置（明确演示性质，不假装已持久化到服务器）。
 */
export class MockTodayActionsService implements TodayActionsService {
  private store: TodayActionsResponse;

  constructor() {
    this.store = cloneResponse();
  }

  async getTodayActions(): Promise<TodayActionsResponse> {
    await delay(450);
    return JSON.parse(JSON.stringify(this.store));
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    await delay(350);
    const card = this.store.cards.find((c) => c.opportunity_id === id);
    return card ? JSON.parse(JSON.stringify(card)) : null;
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    await delay(300);
    const card = this.store.cards.find((c) => c.opportunity_id === id);
    if (!card) return;
    const entry: FollowupHistoryEntry = {
      id: `h-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      status: input.status,
      note: input.note ?? null,
      not_fit_reason: input.not_fit_reason ?? null,
      at: new Date().toISOString(),
    };
    card.followup = {
      status: input.status,
      not_fit_reason: input.not_fit_reason ?? null,
      updated_at: entry.at,
      history: [...card.followup.history, entry],
    };
  }

  async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    await delay(700);
    const card = this.store.cards.find((c) => c.opportunity_id === id);
    const hospitalName = card?.facts.hospital_name ?? '该医院';
    const department = card?.facts.department ?? '相关科室';
    const productName = card?.facts.products?.[0]?.name ?? '相关产品';
    const owner = card?.customer_context.hospital_relationship?.owner ?? '（尚无对接人记录）';

    const content = [
      `【演示话术 · 仅供参考】`,
      ``,
      `${department}的老师，您好！`,
      `了解到${hospitalName}近期有${productName}相关的采购计划，我们此前在${department}也有过合作基础（内部对接人：${owner}）。`,
      `方便的话想和您简单同步一下当前的需求细节和时间节奏，看看是否有可以配合的地方，`,
      `我们这边可以根据实际情况提供设备方案、报价及必要的资质材料。`,
      `期待您的回复，谢谢！`,
    ].join('\n');

    return {
      opportunity_id: id,
      generated_at: new Date().toISOString(),
      content,
      disclaimer: '演示模式 · 正式版将根据当前商机事实和客户资源按需生成，内容仅供销售参考，不构成官方承诺。',
    };
  }
}

export const followupActionLabel = (status: string) => FOLLOWUP_ACTION_LABEL[status] ?? status;
