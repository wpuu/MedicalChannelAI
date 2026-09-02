import { beginAiRequest, endAiRequest } from './aiRequestGate'

export type DiscoverySourceId = string
export type DiscoverySourceKind =
  | 'HOSPITAL_OFFICIAL'
  | 'GOVERNMENT_PROCUREMENT'
  | 'PUBLIC_RESOURCE'
  | 'HEALTH_AUTHORITY'
  | 'OTHER_OFFICIAL'

export type DiscoveryVerificationStatus = 'KNOWN_VERIFIED' | 'DISCOVERED_UNVERIFIED'
export type DiscoveryCacheStatus =
  | 'FRESH_AI'
  | 'FRESH_DELTA_AI'
  | 'REUSED_UNCHANGED'
  | 'REUSED_NO_NEW_LINKS'

export interface DiscoverySourceInput {
  id: DiscoverySourceId
  name: string
  url: string
  kind: DiscoverySourceKind
}

export interface DiscoveryAnchorSnapshot {
  title: string
  url: string
}

export interface DiscoveryRadarCandidate {
  title: string
  url: string
  signal_type: string
  confidence: number
  reason: string
  verification_status: DiscoveryVerificationStatus
  opportunity_id: string | null
}

export interface DiscoveryRadarResult {
  schema_version: '0.3'
  mode: 'AI_DISCOVERY_SHADOW'
  analysis_version: string
  source_id: DiscoverySourceId
  source_name: string
  source_kind: DiscoverySourceKind
  source_url: string
  checked_at: string
  scanned_at: string
  analyzed_at: string
  cache_status: DiscoveryCacheStatus
  ai_called: boolean
  content_fingerprint: string
  official_anchor_count: number
  analyzed_anchor_count: number
  ai_analyzed_anchor_count: number
  new_anchor_count: number
  changed_anchor_count: number
  removed_anchor_count: number
  reused_anchor_count: number
  anchor_cap_applied: boolean
  anchor_snapshot: DiscoveryAnchorSnapshot[]
  coverage_page_count: number
  coverage_page_urls: string[]
  coverage_next_page_detected: boolean
  coverage_page_limit_applied: boolean
  raw_candidate_count: number
  candidate_count: number
  historical_known_verified_count: number
  known_verified_count: number
  known_verified_hit_count: number
  known_recall: number | null
  discovery_score: number | null
  benchmark_scope: 'CURRENT_ANALYZED_OFFICIAL_LINKS'
  rejected_ungrounded_count: number
  rejected_invalid_count: number
  production_data_mutated: false
  candidates: DiscoveryRadarCandidate[]
}

export class DiscoveryRadarError extends Error {
  constructor(public readonly code: string, public readonly status: number) {
    super(code)
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

async function radarError(response: Response): Promise<DiscoveryRadarError> {
  try {
    const body = asRecord(await response.json())
    if (body && typeof body.error === 'string') return new DiscoveryRadarError(body.error, response.status)
  } catch {
    // Use status fallback.
  }
  return new DiscoveryRadarError(`HTTP_${response.status}`, response.status)
}

export function discoveryRadarErrorMessage(error: unknown): string {
  if (!(error instanceof DiscoveryRadarError)) return 'AI情报雷达暂时不可用，请稍后重试'
  if (error.code === 'AI_CLIENT_BUSY') return '已有AI任务正在执行，请稍候'
  if (error.code === 'AI_RADAR_NOT_CONFIGURED') return 'AI情报雷达尚未配置运行密钥'
  if (error.code === 'AI_RADAR_RATE_LIMITED') return '扫描较频繁，请稍后再试'
  if (error.code === 'AI_RADAR_SOURCE_EMPTY') return '该公开渠道暂未读取到可分析链接，建议检查入口地址'
  if (error.code === 'AI_RADAR_SOURCE_INVALID') return '渠道信息无效，请检查名称、类型和 HTTPS 官方地址'
  if (error.code === 'SOURCE_HOST_REJECTED' || error.code === 'SOURCE_NETWORK_REJECTED') return '该地址未通过公网安全校验，请使用公开 HTTPS 官方网站'
  if (error.code === 'SOURCE_DNS_UNRESOLVED') return '该渠道域名暂时无法解析，请检查地址'
  if (error.code === 'SOURCE_REDIRECT_REJECTED') return '该渠道跳转到了未允许的域名，请直接填写最终官方入口'
  if (error.code === 'SOURCE_TOO_LARGE') return '该页面过大，不适合作为列表入口，请换成更具体的采购/公告栏目页'
  if (error.code === 'SAME_ORIGIN_REQUIRED') return '请从正式演示站点打开AI情报雷达'
  if (error.code === 'AI_RADAR_RESPONSE_INVALID') return 'AI返回内容未通过安全校验，请重试'
  return 'AI情报雷达暂时不可用，请稍后重试'
}

function previousScanPayload(result: DiscoveryRadarResult | undefined) {
  if (!result) return undefined
  return {
    analysis_version: result.analysis_version,
    source_url: result.source_url,
    content_fingerprint: result.content_fingerprint,
    analyzed_at: result.analyzed_at,
    raw_candidate_count: result.raw_candidate_count,
    anchor_snapshot: result.anchor_snapshot,
    candidates: result.candidates.map((item) => ({
      url: item.url,
      signal_type: item.signal_type,
      confidence: item.confidence,
      reason: item.reason,
    })),
  }
}

export async function scanDiscoverySource(
  source: DiscoverySourceInput,
  previousResult?: DiscoveryRadarResult,
  forceAi = false,
): Promise<DiscoveryRadarResult> {
  if (!beginAiRequest()) throw new DiscoveryRadarError('AI_CLIENT_BUSY', 409)
  try {
    const response = await fetch('/api/ai/discover', {
      method: 'POST',
      credentials: 'include',
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        source,
        previous_scan: forceAi ? undefined : previousScanPayload(previousResult),
        force_ai: forceAi || undefined,
      }),
    })
    if (!response.ok) throw await radarError(response)
    const body = await response.json() as DiscoveryRadarResult
    if (
      body?.mode !== 'AI_DISCOVERY_SHADOW' ||
      body?.schema_version !== '0.3' ||
      body?.source_id !== source.id ||
      body?.benchmark_scope !== 'CURRENT_ANALYZED_OFFICIAL_LINKS' ||
      !Array.isArray(body?.candidates) ||
      !Array.isArray(body?.anchor_snapshot) ||
      !Array.isArray(body?.coverage_page_urls) ||
      typeof body?.content_fingerprint !== 'string' ||
      typeof body?.ai_called !== 'boolean' ||
      typeof body?.new_anchor_count !== 'number' ||
      typeof body?.changed_anchor_count !== 'number' ||
      typeof body?.removed_anchor_count !== 'number' ||
      typeof body?.reused_anchor_count !== 'number' ||
      typeof body?.ai_analyzed_anchor_count !== 'number' ||
      typeof body?.coverage_page_count !== 'number' ||
      typeof body?.coverage_next_page_detected !== 'boolean' ||
      typeof body?.coverage_page_limit_applied !== 'boolean' ||
      body.coverage_page_count !== body.coverage_page_urls.length ||
      body?.production_data_mutated !== false
    ) {
      throw new DiscoveryRadarError('AI_RADAR_RESPONSE_INVALID', 502)
    }
    return body
  } finally {
    endAiRequest()
  }
}
