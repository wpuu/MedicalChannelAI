import { MockTodayActionsService } from './MockTodayActionsService'
import type { TodayActionsService } from './TodayActionsService'

export const todayActionsService: TodayActionsService = new MockTodayActionsService()
export type { TodayActionsService }
