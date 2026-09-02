import { beginAiRequest, endAiRequest } from './aiRequestGate'
import {
  DiscoveryRadarError,
  type DiscoveryAnchorSnapshot,
  type DiscoveryRadarCandidate,
  type DiscoveryRadarResult,
  type DiscoverySourceInput,
} from './discoveryRadarApi'

export interface DiscoveryContinuationSegment {
  schema_version: '0.1'
  mode: 'AI_DISCOVERY_CONTINUATION_SHADOW'
  analysis_version: 'agnes-discovery-continuation-v1'
  segment_id: string
  segment_index: number
  source_id: string
  source_name: string
  source_url: string
  root_content_fingerprint: string
  checked_at: string
  analyzed_at: string | null
  resume_from_page_url: string
  page_urls: string[]
  next_resume_from_page_url: string | null
  exhausted: boolean
  partial: false
  error_code: null
  content_fingerprint: string
  anchor_snapshot: DiscoveryAnchorSnapshot[]
  analyzed_anchor_count: number
  ai_called: boolean
  raw_candidate_count: number
  candidate_count: number
  rejected_ungrounded_count: number
  rejected_invalid_count: number
  production_data_mutated: false
  candidates: DiscoveryRadarCandidate[]
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

async function continuationError(response: Response): Promise<DiscoveryRadarError> {
  try {
    const body = asRecord(await response.json())
    if (body && typeof body.error === 'string') return new DiscoveryRadarError(body.error, response.status)
  } catch {
    // Use status fallback.
  }
  return new DiscoveryRadarError(`HTTP_${response.status}`, response.status)
}

export function discoveryContinuationErrorMessage(error: unknown): string {
  if (!(error instanceof DiscoveryRadarError)) return '续扫暂时不可用，请稍后重试'
  if (error.code === 'AI_CLIENT_BUSY') return '已有AI任务正在执行，请稍候'
  if (error.code === 'AI_RADAR_CONTINUATION_NOT_ELIGIBLE') return '当前渠道不满足安全续扫条件，请先重新检查根入口'
  if (error.code === 'AI_RADAR_CONTINUATION_LEDGER_INVALID') return '续扫账本与当前根扫描不一致，请重新检查根入口后再续扫'
  if (error.code === 'AI_RADAR_CONTINUATION_LIMIT_REACHED') return '当前根扫描已达到安全续扫段上限，请改用更具体的官方栏目入口'
  if (error.code === 'AI_RADAR_CONTINUATION_EXHAUSTED') return '该续扫链已经到达末页'
  if (error.code === 'AI_RADAR_NOT_CONFIGURED') return 'AI情报雷达尚未配置运行密钥'
  if (error.code === 'AI_RADAR_RATE_LIMITED') return '续扫较频繁，请稍后再试'
  if (error.code === 'SOURCE_TIMEOUT') return '官方续扫页面本次响应超时，请稍后重试'
  if (error.code.startsWith('SOURCE_')) return '续扫页面未通过公开来源安全检查，请重新检查官方入口'
  if (error.code === 'AI_RADAR_RESPONSE_INVALID') return '续扫AI返回内容未通过安全校验，请重试'
  return '续扫暂时不可用，请稍后重试'
}

function rootScanPayload(root: DiscoveryRadarResult) {
  return {
    analysis_version: root.analysis_version,
    source_id: root.source_id,
    source_url: root.source_url,
    content_fingerprint: root.content_fingerprint,
    anchor_cap_applied: root.anchor_cap_applied,
    anchor_snapshot: root.anchor_snapshot,
    coverage_page_urls: root.coverage_page_urls,
    coverage_page_limit_applied: root.coverage_page_limit_applied,
    coverage_partial: root.coverage_partial,
  }
}

function previousSegmentPayload(segment: DiscoveryContinuationSegment) {
  return {
    analysis_version: segment.analysis_version,
    segment_index: segment.segment_index,
    source_id: segment.source_id,
    source_url: segment.source_url,
    root_content_fingerprint: segment.root_content_fingerprint,
    resume_from_page_url: segment.resume_from_page_url,
    page_urls: segment.page_urls,
    next_resume_from_page_url: segment.next_resume_from_page_url,
    exhausted: segment.exhausted,
    partial: segment.partial,
    content_fingerprint: segment.content_fingerprint,
    anchor_snapshot: segment.anchor_snapshot,
  }
}

function validSegmentResponse(
  body: DiscoveryContinuationSegment,
  source: DiscoverySourceInput,
  root: DiscoveryRadarResult,
  previousSegments: DiscoveryContinuationSegment[],
) {
  return (
    body?.mode === 'AI_DISCOVERY_CONTINUATION_SHADOW' &&
    body?.schema_version === '0.1' &&
    body?.analysis_version === 'agnes-discovery-continuation-v1' &&
    body?.source_id === source.id &&
    body?.source_url === source.url &&
    body?.root_content_fingerprint === root.content_fingerprint &&
    body?.segment_index === previousSegments.length + 1 &&
    typeof body?.segment_id === 'string' && body.segment_id.length >= 12 &&
    typeof body?.checked_at === 'string' && Number.isFinite(Date.parse(body.checked_at)) &&
    (body?.analyzed_at === null || (typeof body?.analyzed_at === 'string' && Number.isFinite(Date.parse(body.analyzed_at))) ) &&
    typeof body?.resume_from_page_url === 'string' && body.resume_from_page_url.startsWith('https://') &&
    Array.isArray(body?.page_urls) && body.page_urls.length >= 1 && body.page_urls.length <= 3 &&
    body.page_urls.every((item) => typeof item === 'string' && item.startsWith('https://')) &&
    (body?.next_resume_from_page_url === null || (typeof body?.next_resume_from_page_url === 'string' && body.next_resume_from_page_url.startsWith('https://'))) &&
    typeof body?.exhausted === 'boolean' &&
    body?.partial === false &&
    body?.error_code === null &&
    typeof body?.content_fingerprint === 'string' && body.content_fingerprint.length >= 16 &&
    Array.isArray(body?.anchor_snapshot) && body.anchor_snapshot.length <= 80 &&
    body.anchor_snapshot.every((item) => item && typeof item.title === 'string' && typeof item.url === 'string' && item.url.startsWith('https://')) &&
    body?.analyzed_anchor_count === body.anchor_snapshot.length &&
    typeof body?.ai_called === 'boolean' &&
    typeof body?.raw_candidate_count === 'number' &&
    typeof body?.candidate_count === 'number' &&
    Array.isArray(body?.candidates) && body.candidate_count === body.candidates.length &&
    typeof body?.rejected_ungrounded_count === 'number' &&
    typeof body?.rejected_invalid_count === 'number' &&
    body?.production_data_mutated === false &&
    (body.exhausted ? body.next_resume_from_page_url === null : body.next_resume_from_page_url !== null)
  )
}

export async function scanDiscoveryContinuation(
  source: DiscoverySourceInput,
  root: DiscoveryRadarResult,
  previousSegments: DiscoveryContinuationSegment[],
): Promise<DiscoveryContinuationSegment> {
  if (!beginAiRequest()) throw new DiscoveryRadarError('AI_CLIENT_BUSY', 409)
  try {
    const response = await fetch('/api/ai/discover-continuation', {
      method: 'POST',
      credentials: 'include',
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        source,
        root_scan: rootScanPayload(root),
        previous_segments: previousSegments.map(previousSegmentPayload),
      }),
    })
    if (!response.ok) throw await continuationError(response)
    const body = await response.json() as DiscoveryContinuationSegment
    if (!validSegmentResponse(body, source, root, previousSegments)) {
      throw new DiscoveryRadarError('AI_RADAR_RESPONSE_INVALID', 502)
    }
    return body
  } finally {
    endAiRequest()
  }
}
