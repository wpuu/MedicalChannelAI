import { demoDatasetMode } from '@/config/demoDataset'
import { verifiedSnapshotUrl } from '@/config/snapshotConfig'
import type { FollowupInput, OutreachDraft, TodayActionCard, TodayActionsResponse } from '@/types'
import { apiBaseUrl } from './apiConfig'
import { GroundedApiTodayActionsService } from './GroundedApiTodayActionsService'
import type { TodayActionsLoadOptions, TodayActionsService } from './TodayActionsService'

class DeferredTodayActionsService implements TodayActionsService {
  private delegatePromise: Promise<TodayActionsService> | null = null

  constructor(private readonly loader: () => Promise<TodayActionsService>) {}

  private delegate(): Promise<TodayActionsService> {
    if (!this.delegatePromise) this.delegatePromise = this.loader()
    return this.delegatePromise
  }

  async getTodayActions(options?: TodayActionsLoadOptions): Promise<TodayActionsResponse> {
    return (await this.delegate()).getTodayActions(options)
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    return (await this.delegate()).getOpportunity(id)
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    return (await this.delegate()).updateFollowup(id, input)
  }

  async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    return (await this.delegate()).requestOutreachDraft(id)
  }
}

class PilotApiTodayActionsService implements TodayActionsService {
  private readonly primary: GroundedApiTodayActionsService
  private readonly fullPool: GroundedApiTodayActionsService

  constructor(baseUrl: string) {
    const normalized = baseUrl.replace(/\/+$/, '')
    this.primary = new GroundedApiTodayActionsService(normalized)
    // The Opportunity Pool already requests hydrateFollowups:false as its load profile.
    // Route that one read through a same-function alias which keeps the full pool,
    // while normal Today stays on the lighter /today response.
    this.fullPool = new GroundedApiTodayActionsService(`${normalized}/opportunity-pool`)
  }

  async getTodayActions(options?: TodayActionsLoadOptions): Promise<TodayActionsResponse> {
    const service = options?.hydrateFollowups === false ? this.fullPool : this.primary
    return service.getTodayActions(options)
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    return this.primary.getOpportunity(id)
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    return this.primary.updateFollowup(id, input)
  }

  async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    return this.primary.requestOutreachDraft(id)
  }
}

async function loadVerifiedTrialService(): Promise<TodayActionsService> {
  const [{ RuntimeTrialTodayActionsService }, { StaticSnapshotTodayActionsService }] = await Promise.all([
    import('./RuntimeTrialTodayActionsService'),
    import('./StaticSnapshotTodayActionsService'),
  ])
  return new RuntimeTrialTodayActionsService(
    new StaticSnapshotTodayActionsService(verifiedSnapshotUrl),
  )
}

async function loadSyntheticDemoService(): Promise<TodayActionsService> {
  const { MockTodayActionsService } = await import('./MockTodayActionsService')
  return new MockTodayActionsService()
}

/**
 * Service selection:
 * - VITE_API_BASE_URL configured: real backend Public Views + grounded server actions stay on the primary path.
 * - verified trial: evidence-pipeline generated snapshot is loaded only when the trial build needs it.
 * - synthetic local demo: fictional Mock implementation is loaded only for the demo build.
 */
export const todayActionsService: TodayActionsService = apiBaseUrl
  ? new PilotApiTodayActionsService(apiBaseUrl)
  : new DeferredTodayActionsService(
      demoDatasetMode === 'verified' ? loadVerifiedTrialService : loadSyntheticDemoService,
    )

export type { TodayActionsService }
