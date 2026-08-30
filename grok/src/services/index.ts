import { MockTodayActionsService } from "@/services/MockTodayActionsService";
import type { TodayActionsService } from "@/services/TodayActionsService";

/**
 * 当前使用 Mock 实现。后续可替换为 ApiTodayActionsService。
 * 页面只依赖 TodayActionsService，不直接读取 mock 数据。
 */
export const todayActionsService: TodayActionsService =
  new MockTodayActionsService();
