import { ApiTodayActionsService } from './ApiTodayActionsService'
import { apiBaseUrl } from './apiConfig'
import { MockTodayActionsService } from './MockTodayActionsService'
import type { TodayActionsService } from './TodayActionsService'

/**
 * No API base URL: local Mock Demo.
 * VITE_API_BASE_URL configured: consume only the backend H5-safe Public View.
 */
export const todayActionsService: TodayActionsService = apiBaseUrl
  ? new ApiTodayActionsService(apiBaseUrl)
  : new MockTodayActionsService()

export type { TodayActionsService }
