import { demoDatasetMode } from '@/config/demoDataset'
import { apiBaseUrl } from './apiConfig'
import { GroundedApiTodayActionsService } from './GroundedApiTodayActionsService'
import { MockTodayActionsService } from './MockTodayActionsService'
import { StaticSnapshotTodayActionsService } from './StaticSnapshotTodayActionsService'
import type { TodayActionsService } from './TodayActionsService'

/**
 * Service selection:
 * - VITE_API_BASE_URL configured: real backend Public Views + grounded server actions.
 * - verified static trial: evidence-pipeline generated JSON snapshot.
 * - synthetic local demo: fictional Mock data.
 */
export const todayActionsService: TodayActionsService = apiBaseUrl
  ? new GroundedApiTodayActionsService(apiBaseUrl)
  : demoDatasetMode === 'verified'
    ? new StaticSnapshotTodayActionsService('/data/today-actions.public.json')
    : new MockTodayActionsService()

export type { TodayActionsService }
