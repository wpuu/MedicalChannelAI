import { demoDatasetMode } from '@/config/demoDataset'
import {
  ENABLED_MARKETS,
  marketCodeFromOpportunityId,
  marketCodesForSelection,
  type MarketCode,
} from '@/config/marketPreference'
import { verifiedSnapshotUrl } from '@/config/snapshotConfig'
import type { FollowupInput, OutreachDraft, TodayActionCard, TodayActionsResponse } from '@/types'
import { apiBaseUrl } from './apiConfig'
import { GroundedApiTodayActionsService } from './GroundedApiTodayActionsService'
import type { TodayActionsLoadOptions, TodayActionsService } from './TodayActionsService'

const ENABLED_MARKET_CODES = new Set<string>(ENABLED_MARKETS.map((item) => item.code))

function marketCodeForCard(card: TodayActionCard): MarketCode {
  const explicit = String(
    (card.facts as typeof card.facts & { market_code?: string | null }).market_code ?? '',
  ).trim().toUpperCase()
  if (ENABLED_MARKET_CODES.has(explicit)) return explicit as MarketCode
  // Compatibility only for the pre-v0.5.0 Tianjin snapshot and early regional
  // snapshots. New verified records carry explicit market metadata.
  return marketCodeFromOpportunityId(card.opportunity_id)
}

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

class MarketScopedTodayActionsService implements TodayActionsService {
  constructor(private readonly delegate: TodayActionsService) {}

  async getTodayActions(options?: TodayActionsLoadOptions): Promise<TodayActionsResponse> {
    const result = await this.delegate.getTodayActions(options)
    const allowed = new Set(marketCodesForSelection())
    const pool = (result.opportunity_pool ?? result.cards)
      .filter((card) => allowed.has(marketCodeForCard(card)))
      .map((card, index) => ({ ...card, rank: index + 1 }))
    const cards = pool.slice(0, 5).map((card, index) => ({ ...card, rank: index + 1 }))
    return {
      ...result,
      matched_count: pool.length,
      card_count: cards.length,
      opportunity_pool_count: pool.length,
      coverage_warning: '当前业务地区的商机来自已核验官方公开信息；各地区仍为部分来源覆盖。',
      cards,
      opportunity_pool: pool,
    }
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    return this.delegate.getOpportunity(id)
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    return this.delegate.updateFollowup(id, input)
  }

  async requestOutreachDraft(id: string): Promise<OutreachDraft> {
    return this.delegate.requestOutreachDraft(id)
  }
}

class PilotApiTodayActionsService implements TodayActionsService {
  private primary: GroundedApiTodayActionsService
  private readonly fullPool: GroundedApiTodayActionsService
  private readonly normalizedBaseUrl: string
  private primaryHasFormalNudge = false

  constructor(baseUrl: string) {
    const normalized = baseUrl.replace(/\/+$/, '')
    this.normalizedBaseUrl = normalized
    this.primary = new GroundedApiTodayActionsService(normalized)
    this.fullPool = new GroundedApiTodayActionsService(`${normalized}/opportunity-pool`)
  }

  async getTodayActions(options?: TodayActionsLoadOptions): Promise<TodayActionsResponse> {
    const service = options?.hydrateFollowups === false ? this.fullPool : this.primary
    const result = await service.getTodayActions(options)
    if (service === this.primary) {
      this.primaryHasFormalNudge =
        (result.procurement_intent_followup_summary?.formal_candidates_needing_action ?? 0) > 0
    }
    return result
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    return this.primary.getOpportunity(id)
  }

  async updateFollowup(id: string, input: FollowupInput): Promise<void> {
    await this.primary.updateFollowup(id, input)
    if (this.primaryHasFormalNudge) {
      this.primary = new GroundedApiTodayActionsService(this.normalizedBaseUrl)
      this.primaryHasFormalNudge = false
    }
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
  const verified = new RuntimeTrialTodayActionsService(
    new StaticSnapshotTodayActionsService(verifiedSnapshotUrl),
  )
  return new MarketScopedTodayActionsService(verified)
}

async function loadSyntheticDemoService(): Promise<TodayActionsService> {
  const { MockTodayActionsService } = await import('./MockTodayActionsService')
  return new MockTodayActionsService()
}

/**
 * Service selection:
 * - API configured: authenticated backend path.
 * - verified public trial: one shared verified snapshot, filtered locally by the user's business market.
 * - synthetic local demo: fictional Mock implementation.
 */
export const todayActionsService: TodayActionsService = apiBaseUrl
  ? new MarketScopedTodayActionsService(new PilotApiTodayActionsService(apiBaseUrl))
  : new DeferredTodayActionsService(
      demoDatasetMode === 'verified' ? loadVerifiedTrialService : loadSyntheticDemoService,
    )

export type { TodayActionsService }
