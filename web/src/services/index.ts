import { ApiTodayActionsService } from './ApiTodayActionsService'
import { MockTodayActionsService } from './MockTodayActionsService'
import type { TodayActionsService } from './TodayActionsService'

const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env
const apiBaseUrl = env?.VITE_API_BASE_URL?.trim()

/**
 * No API base URL: local Mock Demo.
 * VITE_API_BASE_URL configured: consume only the backend H5-safe Public View.
 */
export const todayActionsService: TodayActionsService = apiBaseUrl
  ? new ApiTodayActionsService(apiBaseUrl)
  : new MockTodayActionsService()

export type { TodayActionsService }
