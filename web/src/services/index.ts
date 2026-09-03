import { demoDatasetMode } from '@/config/demoDataset'
import { verifiedSnapshotUrl } from '@/config/snapshotConfig'
import { apiBaseUrl } from './apiConfig'
import { GroundedApiTodayActionsService } from './GroundedApiTodayActionsService'
import { MockTodayActionsService } from './MockTodayActionsService'
import { RuntimeTrialTodayActionsService } from './RuntimeTrialTodayActionsService'
import { StaticSnapshotTodayActionsService } from './StaticSnapshotTodayActionsService'
import type { TodayActionsService } from './TodayActionsService'

/**
 * Service selection:
 * - VITE_API_BASE_URL configured: real backend Public Views + grounded server actions.
 * - verified trial: evidence-pipeline generated snapshot, bundled by default or externally refreshed.
 * - synthetic local demo: fictional Mock data.
 */
export const todayActionsService: TodayActionsService = apiBaseUrl
  ? new GroundedApiTodayActionsService(apiBaseUrl)
  : demoDatasetMode === 'verified'
    ? new RuntimeTrialTodayActionsService(
        new StaticSnapshotTodayActionsService(verifiedSnapshotUrl),
      )
    : new MockTodayActionsService()

export type { TodayActionsService }
