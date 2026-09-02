import { beginAiRequest, endAiRequest } from './aiRequestGate'

export type DiscoverySourceId = 'TMUGH' | 'TJNOTHOP' | 'TEDA'
export type DiscoveryVerificationStatus = 'KNOWN_VERIFIED' | 'DISCOVERED_UNVERIFIED'

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
  schema_version: '0.1'
  mode: 'AI_DISCOVERY_SHADOW'
  source_id: DiscoverySourceId
  source_name: string
  source_url: string
  scanned_at: string
  official_anchor_count: number
  analyzed_anchor_count: number
  anchor_cap_applied: boolean
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
  if (error.code === 'AI_RADAR_RATE_LIMITED') return '扫描较频繁，请约1分钟后再试'
  if (error.code === 'AI_RADAR_SOURCE_EMPTY') return '该官方入口暂未读取到可分析链接'
  if (error.code === 'SAME_ORIGIN_REQUIRED') return '请从正式演示站点打开AI情报雷达'
  if (error.code === 'AI_RADAR_RESPONSE_INVALID') return 'AI返回内容未通过安全校验，请重试'
  return 'AI情报雷达暂时不可用，请稍后重试'
}

export async function scanDiscoverySource(sourceId: DiscoverySourceId): Promise<DiscoveryRadarResult> {
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
      body: JSON.stringify({ source_id: sourceId }),
    })
    if (!response.ok) throw await radarError(response)
    const body = await response.json() as DiscoveryRadarResult
    if (
      body?.mode !== 'AI_DISCOVERY_SHADOW' ||
      body?.source_id !== sourceId ||
      body?.benchmark_scope !== 'CURRENT_ANALYZED_OFFICIAL_LINKS' ||
      !Array.isArray(body?.candidates) ||
      body?.production_data_mutated !== false
    ) {
      throw new DiscoveryRadarError('AI_RADAR_RESPONSE_INVALID', 502)
    }
    return body
  } finally {
    endAiRequest()
  }
}
