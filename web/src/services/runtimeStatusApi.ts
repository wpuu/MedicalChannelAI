import type { SnapshotMeta } from '@/types'

export type RuntimeSnapshotSourceMode =
  | 'DATABASE'
  | 'BUNDLED'
  | 'RUNTIME_CACHE'
  | 'REMOTE'
  | 'BUNDLED_FALLBACK'
  | 'UNAVAILABLE'

export interface RuntimeStatus {
  schema_version: '0.1'
  service: 'MedicalChannelAI'
  ready: boolean
  degraded: boolean
  degraded_reason?: string | null
  collection?: {
    available: boolean
    outcome: 'UNKNOWN' | 'RUNNING' | 'FAILED' | 'BLOCKED' | 'COMPLETED' | 'NOT_STARTED'
    attempted_at: string | null
    completed_at: string | null
    failures: Array<{
      source_id: string
      market_code: string | null
      stage: string
      category: string
      error_code: string
    }>
    warnings?: Array<{
      source_id: string
      market_code: string | null
      stage: string
      category: string
      error_code: string
    }>
  }
  production_ready: false
  ai: {
    configured: boolean
  }
  snapshot: {
    available: boolean
    source_mode: RuntimeSnapshotSourceMode
    runtime_origin?: 'PUBLISHED' | 'BUNDLED' | null
    snapshot_as_of: string | null
    freshness: 'FRESH' | 'STALE' | 'INVALID' | 'UNAVAILABLE'
    age_minutes: number | null
    stale_after_minutes: number
    degraded?: boolean
    degraded_reason?: string | null
    collection_coverage?: SnapshotMeta['collection_coverage']
    today_card_count: number
    opportunity_pool_count: number
  }
}

const STATUS_URL = '/api/status'
const CACHE_TTL_MS = 60_000
const MAX_STALE_AFTER_MINUTES = 30 * 60
const SNAPSHOT_SOURCE_MODES = new Set<RuntimeSnapshotSourceMode>([
  'DATABASE',
  'BUNDLED',
  'RUNTIME_CACHE',
  'REMOTE',
  'BUNDLED_FALLBACK',
  'UNAVAILABLE',
])

function snapshotClockLabel(value: string | null | undefined): string | null {
  if (!value || !Number.isFinite(Date.parse(value))) return null
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value))
}

function collectorFailureLabel(status: RuntimeStatus | null): string | null {
  const failure = status?.collection?.failures[0]
  if (!failure) return null
  const location = [failure.market_code, failure.source_id, failure.stage].filter(Boolean).join(' / ')
  return `最近一次采集未完整完成：${location} / ${failure.category} / ${failure.error_code}`
}

let cached: { expiresAt: number; value: RuntimeStatus } | null = null
let inFlight: Promise<RuntimeStatus | null> | null = null
let requestGeneration = 0

function isRuntimeStatus(value: unknown): value is RuntimeStatus {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const row = value as Record<string, unknown>
  const ai = row.ai as Record<string, unknown> | undefined
  const snapshot = row.snapshot as Record<string, unknown> | undefined
  const collection = row.collection as Record<string, unknown> | undefined
  const validCollection = collection === undefined || (
    typeof collection.available === 'boolean' &&
    ['UNKNOWN', 'RUNNING', 'FAILED', 'BLOCKED', 'COMPLETED', 'NOT_STARTED'].includes(String(collection.outcome)) &&
    (collection.attempted_at === null || typeof collection.attempted_at === 'string') &&
    (collection.completed_at === null || typeof collection.completed_at === 'string') &&
    Array.isArray(collection.failures) && collection.failures.every((failure) => {
      if (!failure || typeof failure !== 'object' || Array.isArray(failure)) return false
      const item = failure as Record<string, unknown>
      return typeof item.source_id === 'string' &&
        (item.market_code === null || typeof item.market_code === 'string') &&
        typeof item.stage === 'string' && typeof item.category === 'string' && typeof item.error_code === 'string'
    })
    && (collection.warnings === undefined || (Array.isArray(collection.warnings) && collection.warnings.every((failure) => {
      if (!failure || typeof failure !== 'object' || Array.isArray(failure)) return false
      const item = failure as Record<string, unknown>
      return typeof item.source_id === 'string' &&
        (item.market_code === null || typeof item.market_code === 'string') &&
        typeof item.stage === 'string' && typeof item.category === 'string' && typeof item.error_code === 'string'
    })))
  )
  return (
    row.schema_version === '0.1' &&
    row.service === 'MedicalChannelAI' &&
    typeof row.ready === 'boolean' &&
    typeof row.degraded === 'boolean' &&
    (row.degraded_reason === undefined || row.degraded_reason === null || typeof row.degraded_reason === 'string') &&
    validCollection &&
    row.production_ready === false &&
    Boolean(ai) &&
    typeof ai?.configured === 'boolean' &&
    Boolean(snapshot) &&
    typeof snapshot?.available === 'boolean' &&
    SNAPSHOT_SOURCE_MODES.has(String(snapshot?.source_mode) as RuntimeSnapshotSourceMode) &&
    (snapshot?.runtime_origin === undefined || snapshot?.runtime_origin === null || ['PUBLISHED', 'BUNDLED'].includes(String(snapshot?.runtime_origin))) &&
    (snapshot?.snapshot_as_of === null || typeof snapshot?.snapshot_as_of === 'string') &&
    ['FRESH', 'STALE', 'INVALID', 'UNAVAILABLE'].includes(String(snapshot?.freshness)) &&
    (snapshot?.age_minutes === null || (typeof snapshot?.age_minutes === 'number' && Number.isFinite(snapshot.age_minutes))) &&
    typeof snapshot?.stale_after_minutes === 'number' &&
    typeof snapshot?.today_card_count === 'number' &&
    typeof snapshot?.opportunity_pool_count === 'number'
  )
}

async function fetchRuntimeStatus(): Promise<RuntimeStatus | null> {
  try {
    const response = await fetch(STATUS_URL, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!response.ok) return null
    const payload: unknown = await response.json()
    if (!isRuntimeStatus(payload)) return null
    return payload
  } catch {
    return null
  }
}

export function runtimeSnapshotWarning(
  status: RuntimeStatus | null,
  checked = true,
  displayed?: SnapshotMeta | null,
): string | null {
  if (!checked) return null
  if (!displayed) return '当前商机卡片没有可确认的快照版本。联系或报价前请先核对官方依据。'
  const displayedMs = displayed.snapshot_as_of ? Date.parse(displayed.snapshot_as_of) : Number.NaN
  if (!Number.isFinite(displayedMs) || displayedMs > Date.now() + 15 * 60_000) {
    return '当前商机快照时间缺失或异常，不能确认数据新鲜度。请先核对官方依据。'
  }
  if (displayed.source === 'EXTERNAL' || displayed.source === 'UNKNOWN' || displayed.source === 'UNAVAILABLE') {
    return '当前商机快照来源无法确认，页面数据可能来自未核验来源。请先核对官方依据。'
  }
  if (displayed.degraded) {
    if (displayed.reason === 'REMOTE_REFRESH_FAILED' || displayed.reason === 'DURABLE_READ_FAILED') {
      return '刷新读取失败，页面保留最近一次已核验快照；请核对官方依据。'
    }
    if (displayed.reason === 'COLLECTION_COVERAGE_PARTIAL') {
      const failure = collectorFailureLabel(status)
      const lastComplete = snapshotClockLabel(displayed.collection_coverage?.last_complete_as_of)
      const anchor = lastComplete ? `上次完整覆盖截至 ${lastComplete}。` : '尚无可确认的完整覆盖时间。'
      return `${failure ? `${failure}。` : ''}当前数据版本只覆盖部分来源；${anchor}页面仍可查看已核验事实，但可能遗漏其他来源的新项目。`
    }
    if (displayed.reason === 'COLLECTION_COVERAGE_UNKNOWN') {
      const failure = collectorFailureLabel(status)
      return `${failure ? `${failure}。` : ''}当前数据版本的全量覆盖状态未知；页面仍可查看已核验事实，请核对官方依据。`
    }
    return '当前快照处于降级状态；页面保留已核验事实，请核对官方依据。'
  }
  if (!status) {
    return '当前无法确认公开商机快照状态。联系或报价前请先核对官方依据。'
  }
  const statusMs = status.snapshot.snapshot_as_of ? Date.parse(status.snapshot.snapshot_as_of) : Number.NaN
  const sourceMismatch = displayed.source !== status.snapshot.source_mode ||
    (displayed.source === 'RUNTIME_CACHE' && displayed.runtime_origin !== (status.snapshot.runtime_origin ?? null))
  if (!Number.isFinite(statusMs) || displayedMs !== statusMs || sourceMismatch) {
    return '当前页面商机版本或来源与服务端状态不一致，不能确认页面数据新鲜度；请刷新页面并核对官方依据。'
  }
  if (!status.collection?.available || status.collection.outcome !== 'COMPLETED') {
    const failure = collectorFailureLabel(status)
    if (failure) {
      return `${failure}。当前快照仍可查看，请核对官方依据。`
    }
    return '最近一次采集状态未知或尚未完成；当前快照仍可查看，请核对官方依据。'
  }
  if (status.snapshot.collection_coverage?.complete !== true) {
    return status.snapshot.collection_coverage?.complete === false
      ? `当前数据版本只覆盖部分来源；${snapshotClockLabel(status.snapshot.collection_coverage.last_complete_as_of) ? `上次完整覆盖截至 ${snapshotClockLabel(status.snapshot.collection_coverage.last_complete_as_of)}。` : '尚无可确认的完整覆盖时间。'}页面仍可查看已核验事实，但可能遗漏其他来源的新项目。`
      : '当前数据版本的全量覆盖状态未知；页面仍可查看已核验事实，请核对官方依据。'
  }
  if (status.snapshot.source_mode === 'BUNDLED_FALLBACK') {
    return '实时数据读取异常，当前使用最近一次内置已核验快照。联系或报价前请先打开官方依据再次核对。'
  }
  const staleAfterMinutes = Number.isFinite(status.snapshot.stale_after_minutes)
    ? Math.min(MAX_STALE_AFTER_MINUTES, Math.max(0, status.snapshot.stale_after_minutes))
    : 0
  const displayedAgeMinutes = Math.max(0, (Date.now() - displayedMs) / 60_000)
  if (status.snapshot.freshness === 'STALE' || displayedAgeMinutes > staleAfterMinutes) {
    const hours = Math.max(1, Math.floor(displayedAgeMinutes / 60))
    return `公开商机快照已约 ${hours} 小时未成功刷新。联系或报价前请先打开官方依据再次核对。`
  }
  if (status.snapshot.freshness === 'INVALID') {
    return '公开商机快照时间异常，当前结果不应作为最新商机判断。请先核对官方依据。'
  }
  if (status.snapshot.freshness === 'UNAVAILABLE' || !status.snapshot.available) {
    return '当前无法确认公开商机快照状态。联系或报价前请先核对官方依据。'
  }
  if (status.degraded || status.snapshot.degraded) return '公开商机快照处于降级状态，请核对官方依据。'
  return null
}

export function runtimeAutomationUnavailableReason(
  status: RuntimeStatus | null,
  checked = true,
  displayed?: SnapshotMeta | null,
): string | null {
  if (!checked) return '正在确认公开商机快照状态，自动分析与沟通草稿暂不可用。'
  if (!status) return '暂时无法确认商机数据新鲜度，已暂停自动分析与沟通草稿。'
  const warning = runtimeSnapshotWarning(status, checked, displayed)
  if (warning) return `${warning} 已暂停自动分析与沟通草稿。`
  if (!status.snapshot.available || status.snapshot.freshness === 'UNAVAILABLE') {
    return '当前无法确认公开商机快照，已暂停自动分析与沟通草稿。'
  }
  if (status.snapshot.freshness === 'INVALID') {
    return '公开商机快照时间异常，已暂停自动分析与沟通草稿。'
  }
  if (status.snapshot.freshness === 'STALE') {
    return '公开商机快照已超过正常刷新窗口，已暂停自动分析与沟通草稿；请先核对官方依据。'
  }
  return null
}

export async function getRuntimeStatus(force = false): Promise<RuntimeStatus | null> {
  const now = Date.now()
  if (!force && cached && cached.expiresAt > now) return cached.value
  if (!force && inFlight) return inFlight

  const generation = ++requestGeneration
  const request = fetchRuntimeStatus().then((value) => {
    if (generation !== requestGeneration) return null
    if (value) {
      cached = { expiresAt: Date.now() + CACHE_TTL_MS, value }
    }
    return value
  })
  inFlight = request
  try {
    return await request
  } finally {
    if (inFlight === request) inFlight = null
  }
}

export function clearRuntimeStatusCacheForTests(): void {
  cached = null
  inFlight = null
  requestGeneration += 1
}
