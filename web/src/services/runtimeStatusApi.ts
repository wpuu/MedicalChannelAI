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
    today_card_count: number
    opportunity_pool_count: number
  }
}

const STATUS_URL = '/api/status'
const CACHE_TTL_MS = 60_000
const SNAPSHOT_SOURCE_MODES = new Set<RuntimeSnapshotSourceMode>([
  'DATABASE',
  'BUNDLED',
  'RUNTIME_CACHE',
  'REMOTE',
  'BUNDLED_FALLBACK',
  'UNAVAILABLE',
])

let cached: { expiresAt: number; value: RuntimeStatus } | null = null
let inFlight: Promise<RuntimeStatus | null> | null = null

function isRuntimeStatus(value: unknown): value is RuntimeStatus {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const row = value as Record<string, unknown>
  const ai = row.ai as Record<string, unknown> | undefined
  const snapshot = row.snapshot as Record<string, unknown> | undefined
  return (
    row.schema_version === '0.1' &&
    row.service === 'MedicalChannelAI' &&
    typeof row.ready === 'boolean' &&
    typeof row.degraded === 'boolean' &&
    row.production_ready === false &&
    Boolean(ai) &&
    typeof ai?.configured === 'boolean' &&
    Boolean(snapshot) &&
    typeof snapshot?.available === 'boolean' &&
    SNAPSHOT_SOURCE_MODES.has(String(snapshot?.source_mode) as RuntimeSnapshotSourceMode) &&
    (snapshot?.runtime_origin === undefined || snapshot?.runtime_origin === null || ['PUBLISHED', 'BUNDLED'].includes(String(snapshot?.runtime_origin))) &&
    (snapshot?.snapshot_as_of === null || typeof snapshot?.snapshot_as_of === 'string') &&
    ['FRESH', 'STALE', 'INVALID', 'UNAVAILABLE'].includes(String(snapshot?.freshness)) &&
    (snapshot?.age_minutes === null || typeof snapshot?.age_minutes === 'number') &&
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
    const payload: unknown = await response.json()
    if (!isRuntimeStatus(payload)) return null
    return payload
  } catch {
    return null
  }
}

function displayedSnapshotWarning(status: RuntimeStatus, snapshotAsOf: string | null): string | null {
  const displayedAt = Date.parse(snapshotAsOf ?? '')
  const statusAt = Date.parse(status.snapshot.snapshot_as_of ?? '')
  const ageMinutes = (Date.now() - displayedAt) / 60_000
  if (!Number.isFinite(displayedAt) || ageMinutes < -15) {
    return '当前展示的商机快照时间无法确认。请刷新页面并核对官方依据。'
  }
  const staleAfter = status.snapshot.stale_after_minutes
  if (!Number.isFinite(staleAfter) || staleAfter <= 0 || ageMinutes > staleAfter) {
    return '当前展示的商机快照已超过正常刷新窗口。请刷新页面并核对官方依据。'
  }
  if (!Number.isFinite(statusAt) || displayedAt !== statusAt) {
    return '当前展示的商机快照与服务当前版本不一致。请刷新页面并核对官方依据。'
  }
  return null
}

export function runtimeSnapshotWarning(
  status: RuntimeStatus | null,
  checked = true,
  displayedSnapshotAsOf?: string | null,
): string | null {
  if (!checked) return null
  if (!status) {
    return '当前无法确认公开商机快照状态。联系或报价前请先核对官方依据。'
  }
  if (status.snapshot.source_mode === 'BUNDLED_FALLBACK') {
    return '实时数据读取异常，当前使用最近一次内置已核验快照。联系或报价前请先打开官方依据再次核对。'
  }
  if (status.snapshot.freshness === 'STALE') {
    const hours = status.snapshot.age_minutes === null
      ? null
      : Math.max(1, Math.floor(status.snapshot.age_minutes / 60))
    return hours === null
      ? '公开商机快照已超过正常刷新窗口。联系或报价前请先打开官方依据再次核对。'
      : `公开商机快照已约 ${hours} 小时未成功刷新。联系或报价前请先打开官方依据再次核对。`
  }
  if (status.snapshot.freshness === 'INVALID') {
    return '公开商机快照时间异常，当前结果不应作为最新商机判断。请先核对官方依据。'
  }
  if (status.snapshot.freshness === 'UNAVAILABLE' || !status.snapshot.available) {
    return '当前无法确认公开商机快照状态。联系或报价前请先核对官方依据。'
  }
  return displayedSnapshotAsOf === undefined ? null : displayedSnapshotWarning(status, displayedSnapshotAsOf)
}

export function runtimeAutomationUnavailableReason(
  status: RuntimeStatus | null,
  checked = true,
  displayedSnapshotAsOf?: string | null,
): string | null {
  if (!checked) return '正在确认公开商机快照状态，自动分析与沟通草稿暂不可用。'
  if (!status) return '暂时无法确认商机数据新鲜度，已暂停自动分析与沟通草稿。'
  if (!status.snapshot.available || status.snapshot.freshness === 'UNAVAILABLE') {
    return '当前无法确认公开商机快照，已暂停自动分析与沟通草稿。'
  }
  if (status.snapshot.freshness === 'INVALID') {
    return '公开商机快照时间异常，已暂停自动分析与沟通草稿。'
  }
  if (status.snapshot.freshness === 'STALE') {
    return '公开商机快照已超过正常刷新窗口，已暂停自动分析与沟通草稿；请先核对官方依据。'
  }
  const warning = displayedSnapshotAsOf === undefined ? null : displayedSnapshotWarning(status, displayedSnapshotAsOf)
  return warning ? `${warning}已暂停自动分析与沟通草稿。` : null
}

export async function getRuntimeStatus(force = false): Promise<RuntimeStatus | null> {
  const now = Date.now()
  if (!force && cached && cached.expiresAt > now) return cached.value
  if (!force && inFlight) return inFlight

  const request = fetchRuntimeStatus().then((value) => {
    if (value) {
      cached = {
        expiresAt: Date.now() + CACHE_TTL_MS,
        value,
      }
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
}
