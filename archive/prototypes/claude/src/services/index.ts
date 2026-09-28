import { MockTodayActionsService } from './MockTodayActionsService';
import type { TodayActionsService } from './TodayActionsService';

// 当前使用本地 Mock 数据服务。
// 未来接入真实后端时，只需替换为 new ApiTodayActionsService()，
// 页面与组件层不需要任何改动。
export const todayActionsService: TodayActionsService = new MockTodayActionsService();

export type { TodayActionsService } from './TodayActionsService';
