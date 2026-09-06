import type { DiscoveryRadarResult } from './discoveryRadarApi'

export type DiscoveryCoverageRiskCode =
  | 'OPTIONAL_PAGE_INCOMPLETE'
  | 'DEEP_PAGINATION_REMAINS'
  | 'ANCHOR_WINDOW_CAPPED'

export type DiscoveryCoverageRiskSeverity = 'HIGH' | 'MEDIUM'

export interface DiscoveryCoverageRisk {
  source_id: string
  source_name: string
  code: DiscoveryCoverageRiskCode
  severity: DiscoveryCoverageRiskSeverity
  reason: string
  recommended_action: string
  continuation_candidate: boolean
}

export interface DiscoveryCoverageRiskSummary {
  affected_source_count: number
  total_risk_count: number
  high_risk_source_count: number
  partial_source_count: number
  deep_pagination_source_count: number
  anchor_cap_source_count: number
  continuation_candidate_source_count: number
}

function risk(
  result: DiscoveryRadarResult,
  code: DiscoveryCoverageRiskCode,
  severity: DiscoveryCoverageRiskSeverity,
  reason: string,
  recommendedAction: string,
  continuationCandidate: boolean,
): DiscoveryCoverageRisk {
  return {
    source_id: result.source_id,
    source_name: result.source_name,
    code,
    severity,
    reason,
    recommended_action: recommendedAction,
    continuation_candidate: continuationCandidate,
  }
}

/**
 * Coverage risk is deliberately separate from discovery quality/score.
 * A channel can have strong AI recall while still having an incomplete public-page window.
 */
export function discoveryCoverageRisks(result: DiscoveryRadarResult): DiscoveryCoverageRisk[] {
  const risks: DiscoveryCoverageRisk[] = []

  if (result.coverage_partial) {
    risks.push(risk(
      result,
      'OPTIONAL_PAGE_INCOMPLETE',
      'HIGH',
      '后续分页本轮读取失败，当前检查窗口不完整。',
      '优先重试当前渠道；有可信历史时继续沿用上次完整结果，不把本轮局部页面当成完整覆盖。',
      false,
    ))
  }

  if (result.coverage_page_limit_applied) {
    risks.push(risk(
      result,
      'DEEP_PAGINATION_REMAINS',
      'MEDIUM',
      `已安全检查 ${result.coverage_page_count} 页，但官方页面仍明确存在下一页。`,
      '需要独立续扫段继续向后检查；续扫结果只能追加到账本，不能覆盖根入口的增量快照。',
      true,
    ))
  }

  if (result.anchor_cap_applied) {
    risks.push(risk(
      result,
      'ANCHOR_WINDOW_CAPPED',
      'MEDIUM',
      '当前官方页面窗口超过单次 80 条去重链接分析上限。',
      '优先改用更具体的官方栏目入口；仍需补扫时使用独立续扫段，不把截断窗口标记为完整覆盖。',
      true,
    ))
  }

  return risks
}

export function summarizeDiscoveryCoverageRisks(
  results: DiscoveryRadarResult[],
): DiscoveryCoverageRiskSummary {
  const risks = results.flatMap(discoveryCoverageRisks)
  const affectedSourceIds = new Set(risks.map((item) => item.source_id))
  const highRiskSourceIds = new Set(
    risks.filter((item) => item.severity === 'HIGH').map((item) => item.source_id),
  )
  const continuationSourceIds = new Set(
    risks.filter((item) => item.continuation_candidate).map((item) => item.source_id),
  )

  return {
    affected_source_count: affectedSourceIds.size,
    total_risk_count: risks.length,
    high_risk_source_count: highRiskSourceIds.size,
    partial_source_count: results.filter((item) => item.coverage_partial).length,
    deep_pagination_source_count: results.filter((item) => item.coverage_page_limit_applied).length,
    anchor_cap_source_count: results.filter((item) => item.anchor_cap_applied).length,
    continuation_candidate_source_count: continuationSourceIds.size,
  }
}
