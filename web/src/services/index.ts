import { apiBaseUrl } from './apiConfig'
import { GroundedApiTodayActionsService } from './GroundedApiTodayActionsService'
import { MockTodayActionsService } from './MockTodayActionsService'
import type { TodayActionsService } from './TodayActionsService'

/**
 * No API base URL: local Mock Demo.
 * VITE_API_BASE_URL configured: consume only backend H5-safe Public Views and
 * server-rendered grounded outreach drafts.
 */
export const todayActionsService: TodayActionsService = apiBaseUrl
  ? new GroundedApiTodayActionsService(apiBaseUrl)
  : new MockTodayActionsService()

export type { TodayActionsService }
