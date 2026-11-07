import type { TodayActionCard } from '../types'

export type HematologyWholeDeviceScopeStatus = 'IN_SCOPE' | 'OUT_OF_SCOPE' | 'NEEDS_EVIDENCE'

export interface HematologyWholeDeviceEvidence {
  /** Official structured product entry, not a customer qualification fact. */
  field: string
  itemIndex: number
  productName: string
}

export interface HematologyWholeDeviceScopeResult {
  status: HematologyWholeDeviceScopeStatus
  reason: string
  evidence: HematologyWholeDeviceEvidence | null
}

/** Conservative frontend annotation only: not a bid-eligibility decision. */
export function classifyHematologyWholeDeviceScope(
  card: Pick<TodayActionCard, 'facts' | 'evidence_source_urls'>,
): HematologyWholeDeviceScopeResult
