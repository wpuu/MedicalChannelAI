import type {
  TodayActionsResponse,
  TodayActionCard,
  FollowupInput,
  OutreachDraft,
} from '../types/opportunity';

/**
 * 今日行动数据服务抽象接口。
 * 未来接入真实后端时，只需新建 ApiTodayActionsService 实现该接口，
 * 页面层与组件层完全不需要改动。
 */
export interface TodayActionsService {
  /** 获取“今日行动”卡片集合 */
  getTodayActions(): Promise<TodayActionsResponse>;
  /** 获取单个商机详情 */
  getOpportunity(id: string): Promise<TodayActionCard | null>;
  /** 更新某个商机的跟进状态（首版仅本地保存，不代表已同步服务器） */
  updateFollowup(id: string, input: FollowupInput): Promise<void>;
  /** 按需生成沟通话术（首版为演示占位实现） */
  requestOutreachDraft(id: string): Promise<OutreachDraft>;
}
