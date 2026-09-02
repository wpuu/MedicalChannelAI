import type {
  DiscoveryRadarCandidate,
  DiscoveryRadarResult,
  DiscoverySourceInput,
  DiscoverySourceKind,
} from './discoveryRadarApi'

const STORAGE_KEY = 'medicalchannelai.discovery.workspace.bootstrap.v4'
const V3_STORAGE_KEY = 'medicalchannelai.discovery.workspace.v3'
const LEGACY_STORAGE_KEY = 'medicalchannelai.discovery.workspace.v2'
const DB_NAME = 'medicalchannelai.discovery.local'
const DB_VERSION = 1
const DB_STORE = 'workspace'
const DB_KEY = 'current'
const LOCAL_WARNING_BYTES = 25 * 1024 * 1024

export interface SavedDiscoverySource extends DiscoverySourceInput {
  scope: string
  enabled: boolean
  origin: 'USER'
  created_at: string
  updated_at: string
}

export interface DiscoverySourceStats {
  scan_count: number
  ai_call_count: number
  cache_hit_count: number
  total_candidate_count: number
  total_novel_candidate_count: number
  consecutive_failure_count: number
  consecutive_zero_candidate_count: number
  last_checked_at: string | null
  last_error: string | null
}

export interface DiscoveryFinding extends DiscoveryRadarCandidate {
  finding_key: string
  source_id: string
  source_name: string
  source_url: string
  first_seen_at: string
  last_seen_at: string
  times_seen: number
  active_in_latest_scan: boolean
}

export interface DiscoveryWorkspace {
  schema_version: 4
  sources: SavedDiscoverySource[]
  results: Record<string, DiscoveryRadarResult>
  stats: Record<string, DiscoverySourceStats>
  findings: Record<string, DiscoveryFinding>
}

export interface DiscoveryStorageStatus {
  mode: 'INDEXED_DB' | 'LOCAL_STORAGE_FALLBACK'
  workspace_bytes: number
  origin_usage_bytes: number | null
  origin_quota_bytes: number | null
  persistent: boolean | null
  warning: 'LOCAL_DATA_LARGE' | 'ORIGIN_QUOTA_HIGH' | 'INDEXED_DB_UNAVAILABLE' | null
}

function nowIso() {
  return new Date().toISOString()
}

function cleanScope(value: unknown) {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim().slice(0, 40) : ''
}

function blankStats(): DiscoverySourceStats {
  return {
    scan_count: 0,
    ai_call_count: 0,
    cache_hit_count: 0,
    total_candidate_count: 0,
    total_novel_candidate_count: 0,
    consecutive_failure_count: 0,
    consecutive_zero_candidate_count: 0,
    last_checked_at: null,
    last_error: null,
  }
}

function emptyWorkspace(): DiscoveryWorkspace {
  return {
    schema_version: 4,
    sources: [],
    results: {},
    stats: {},
    findings: {},
  }
}

function isKind(value: unknown): value is DiscoverySourceKind {
  return [
    'HOSPITAL_OFFICIAL',
    'GOVERNMENT_PROCUREMENT',
    'PUBLIC_RESOURCE',
    'HEALTH_AUTHORITY',
    'OTHER_OFFICIAL',
  ].includes(String(value))
}

function normalizeSource(value: unknown): SavedDiscoverySource | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Partial<SavedDiscoverySource> & { origin?: string }
  if (
    typeof row.id !== 'string' || row.id.length === 0 || row.id.length > 96 ||
    typeof row.name !== 'string' || row.name.length === 0 || row.name.length > 100 ||
    typeof row.url !== 'string' || !row.url.startsWith('https://') || row.url.length > 1200 ||
    !isKind(row.kind) || typeof row.enabled !== 'boolean' || row.origin !== 'USER' ||
    typeof row.created_at !== 'string' || typeof row.updated_at !== 'string'
  ) return null
  return { ...row, scope: cleanScope(row.scope) } as SavedDiscoverySource
}

function findingKey(sourceId: string, url: string) {
  return `${sourceId}\u0000${url}`
}

function normalizeWorkspace(value: unknown): DiscoveryWorkspace | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const parsed = value as Partial<DiscoveryWorkspace> & { schema_version?: number }
  if (![3, 4].includes(Number(parsed.schema_version)) || !Array.isArray(parsed.sources)) return null
  const sources = parsed.sources.map(normalizeSource).filter(Boolean) as SavedDiscoverySource[]
  const allowedIds = new Set(sources.map((source) => source.id))
  const results = parsed.results && typeof parsed.results === 'object'
    ? Object.fromEntries(Object.entries(parsed.results).filter(([sourceId]) => allowedIds.has(sourceId)))
    : {}
  const stats = parsed.stats && typeof parsed.stats === 'object'
    ? Object.fromEntries(Object.entries(parsed.stats).filter(([sourceId]) => allowedIds.has(sourceId)))
    : {}
  const findings = parsed.findings && typeof parsed.findings === 'object'
    ? Object.fromEntries(Object.entries(parsed.findings).filter(([, item]) => {
        const sourceId = (item as Partial<DiscoveryFinding>)?.source_id
        return typeof sourceId === 'string' && allowedIds.has(sourceId)
      }))
    : {}
  return { schema_version: 4, sources, results, stats, findings }
}

function parseStored(raw: string | null) {
  if (!raw) return null
  try {
    return normalizeWorkspace(JSON.parse(raw))
  } catch {
    return null
  }
}

function migrateLegacyWorkspace(): DiscoveryWorkspace | null {
  if (typeof window === 'undefined') return null
  const v3 = parseStored(window.localStorage.getItem(V3_STORAGE_KEY))
  if (v3) return v3
  const raw = window.localStorage.getItem(LEGACY_STORAGE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as {
      sources?: Array<Partial<SavedDiscoverySource> & { origin?: string }>
      results?: Record<string, DiscoveryRadarResult>
      stats?: Record<string, DiscoverySourceStats>
    }
    const sources = (parsed.sources ?? [])
      .filter((source) => source.origin === 'USER')
      .map((source) => normalizeSource({ ...source, scope: cleanScope(source.scope) }))
      .filter(Boolean) as SavedDiscoverySource[]
    const allowedIds = new Set(sources.map((source) => source.id))
    const results = Object.fromEntries(
      Object.entries(parsed.results ?? {}).filter(([sourceId]) => allowedIds.has(sourceId)),
    )
    const stats = Object.fromEntries(
      Object.entries(parsed.stats ?? {}).filter(([sourceId]) => allowedIds.has(sourceId)),
    )
    let workspace: DiscoveryWorkspace = { schema_version: 4, sources, results, stats, findings: {} }
    for (const result of Object.values(results)) {
      workspace = { ...workspace, findings: mergeDiscoveryFindings(workspace.findings, result) }
    }
    return workspace
  } catch {
    return null
  }
}

export function loadDiscoveryWorkspace(): DiscoveryWorkspace {
  if (typeof window === 'undefined') return emptyWorkspace()
  const bootstrap = parseStored(window.localStorage.getItem(STORAGE_KEY))
  if (bootstrap) return bootstrap
  return migrateLegacyWorkspace() ?? emptyWorkspace()
}

function openDiscoveryDb(): Promise<IDBDatabase> {
  if (typeof indexedDB === 'undefined') return Promise.reject(new Error('INDEXED_DB_UNAVAILABLE'))
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(DB_STORE)) db.createObjectStore(DB_STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('INDEXED_DB_OPEN_FAILED'))
    request.onblocked = () => reject(new Error('INDEXED_DB_BLOCKED'))
  })
}

async function readIndexedWorkspace(): Promise<DiscoveryWorkspace | null> {
  const db = await openDiscoveryDb()
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readonly')
      const request = transaction.objectStore(DB_STORE).get(DB_KEY)
      request.onsuccess = () => resolve(normalizeWorkspace(request.result))
      request.onerror = () => reject(request.error ?? new Error('INDEXED_DB_READ_FAILED'))
    })
  } finally {
    db.close()
  }
}

async function writeIndexedWorkspace(workspace: DiscoveryWorkspace): Promise<void> {
  const db = await openDiscoveryDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readwrite')
      transaction.objectStore(DB_STORE).put(workspace, DB_KEY)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('INDEXED_DB_WRITE_FAILED'))
      transaction.onabort = () => reject(transaction.error ?? new Error('INDEXED_DB_WRITE_ABORTED'))
    })
  } finally {
    db.close()
  }
}

function workspaceBytes(workspace: DiscoveryWorkspace) {
  return new TextEncoder().encode(JSON.stringify(workspace)).byteLength
}

async function browserStorageStatus(workspace: DiscoveryWorkspace, mode: DiscoveryStorageStatus['mode']): Promise<DiscoveryStorageStatus> {
  const bytes = workspaceBytes(workspace)
  let usage: number | null = null
  let quota: number | null = null
  let persistent: boolean | null = null
  try {
    if (typeof navigator !== 'undefined' && navigator.storage?.estimate) {
      const estimate = await navigator.storage.estimate()
      usage = typeof estimate.usage === 'number' ? estimate.usage : null
      quota = typeof estimate.quota === 'number' ? estimate.quota : null
    }
    if (typeof navigator !== 'undefined' && navigator.storage?.persisted) {
      persistent = await navigator.storage.persisted()
    }
  } catch {
    // Storage estimate is informational only.
  }
  const ratio = usage !== null && quota ? usage / quota : 0
  return {
    mode,
    workspace_bytes: bytes,
    origin_usage_bytes: usage,
    origin_quota_bytes: quota,
    persistent,
    warning: mode === 'LOCAL_STORAGE_FALLBACK'
      ? 'INDEXED_DB_UNAVAILABLE'
      : bytes >= LOCAL_WARNING_BYTES
        ? 'LOCAL_DATA_LARGE'
        : ratio >= 0.75
          ? 'ORIGIN_QUOTA_HIGH'
          : null,
  }
}

function bootstrapWorkspace(workspace: DiscoveryWorkspace): DiscoveryWorkspace {
  return {
    schema_version: 4,
    sources: workspace.sources,
    results: {},
    stats: workspace.stats,
    findings: {},
  }
}

function writeBootstrap(workspace: DiscoveryWorkspace, full = false) {
  if (typeof window === 'undefined') return
  const value = full ? workspace : bootstrapWorkspace(workspace)
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
}

export async function loadDiscoveryWorkspaceDurable(
  fallback: DiscoveryWorkspace = loadDiscoveryWorkspace(),
): Promise<{ workspace: DiscoveryWorkspace; status: DiscoveryStorageStatus }> {
  try {
    const stored = await readIndexedWorkspace()
    const workspace = stored ?? fallback
    if (!stored) await writeIndexedWorkspace(workspace)
    writeBootstrap(workspace)
    return { workspace, status: await browserStorageStatus(workspace, 'INDEXED_DB') }
  } catch {
    try { writeBootstrap(fallback, true) } catch { /* Keep in-memory state if quota is exhausted. */ }
    return { workspace: fallback, status: await browserStorageStatus(fallback, 'LOCAL_STORAGE_FALLBACK') }
  }
}

let saveChain: Promise<DiscoveryStorageStatus> = Promise.resolve({
  mode: 'INDEXED_DB',
  workspace_bytes: 0,
  origin_usage_bytes: null,
  origin_quota_bytes: null,
  persistent: null,
  warning: null,
})

export function saveDiscoveryWorkspace(workspace: DiscoveryWorkspace): Promise<DiscoveryStorageStatus> {
  saveChain = saveChain.then(async () => {
    try {
      await writeIndexedWorkspace(workspace)
      try { writeBootstrap(workspace) } catch { /* IndexedDB remains authoritative. */ }
      return browserStorageStatus(workspace, 'INDEXED_DB')
    } catch {
      try { writeBootstrap(workspace, true) } catch { /* Surface fallback warning via status. */ }
      return browserStorageStatus(workspace, 'LOCAL_STORAGE_FALLBACK')
    }
  })
  return saveChain
}

export async function requestDiscoveryStoragePersistence() {
  if (typeof navigator === 'undefined' || !navigator.storage?.persist) return false
  try {
    return await navigator.storage.persist()
  } catch {
    return false
  }
}

export function newDiscoverySourceId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `src-${crypto.randomUUID()}`
  }
  return `src-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function mergeDiscoveryFindings(
  current: Record<string, DiscoveryFinding>,
  result: DiscoveryRadarResult,
): Record<string, DiscoveryFinding> {
  const next: Record<string, DiscoveryFinding> = {}
  for (const [key, item] of Object.entries(current)) {
    next[key] = item.source_id === result.source_id
      ? { ...item, active_in_latest_scan: false }
      : item
  }
  for (const candidate of result.candidates) {
    const key = findingKey(result.source_id, candidate.url)
    const existing = next[key]
    next[key] = {
      ...candidate,
      finding_key: key,
      source_id: result.source_id,
      source_name: result.source_name,
      source_url: result.source_url,
      first_seen_at: existing?.first_seen_at ?? result.analyzed_at,
      last_seen_at: result.checked_at,
      times_seen: (existing?.times_seen ?? 0) + 1,
      active_in_latest_scan: true,
    }
  }
  return next
}

export function recordDiscoverySuccess(
  current: DiscoverySourceStats | undefined,
  result: DiscoveryRadarResult,
): DiscoverySourceStats {
  const base = current ?? blankStats()
  const novel = result.candidates.filter((item) => item.verification_status === 'DISCOVERED_UNVERIFIED').length
  return {
    scan_count: base.scan_count + 1,
    ai_call_count: base.ai_call_count + (result.ai_called ? 1 : 0),
    cache_hit_count: base.cache_hit_count + (result.ai_called ? 0 : 1),
    total_candidate_count: base.total_candidate_count + result.candidate_count,
    total_novel_candidate_count: base.total_novel_candidate_count + novel,
    consecutive_failure_count: 0,
    consecutive_zero_candidate_count: result.candidate_count === 0 ? base.consecutive_zero_candidate_count + 1 : 0,
    last_checked_at: result.checked_at,
    last_error: null,
  }
}

export function recordDiscoveryFailure(
  current: DiscoverySourceStats | undefined,
  errorCode: string,
): DiscoverySourceStats {
  const base = current ?? blankStats()
  return {
    ...base,
    scan_count: base.scan_count + 1,
    consecutive_failure_count: base.consecutive_failure_count + 1,
    last_checked_at: nowIso(),
    last_error: errorCode,
  }
}

export type SourceHealth = 'HEALTHY' | 'LOW_YIELD' | 'REVIEW' | 'UNTESTED'

export function discoverySourceHealth(stats: DiscoverySourceStats | undefined): SourceHealth {
  if (!stats || stats.scan_count === 0) return 'UNTESTED'
  if (stats.consecutive_failure_count >= 2) return 'REVIEW'
  if (stats.consecutive_zero_candidate_count >= 3) return 'LOW_YIELD'
  return 'HEALTHY'
}

export function emptyDiscoveryStats(): DiscoverySourceStats {
  return blankStats()
}
