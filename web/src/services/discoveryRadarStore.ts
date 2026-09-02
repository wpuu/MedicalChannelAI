import type {
  DiscoveryRadarCandidate,
  DiscoveryRadarResult,
  DiscoverySourceInput,
  DiscoverySourceKind,
} from './discoveryRadarApi'

const STORAGE_KEY = 'medicalchannelai.discovery.workspace.v3'
const LEGACY_STORAGE_KEY = 'medicalchannelai.discovery.workspace.v2'

export interface SavedDiscoverySource extends DiscoverySourceInput {
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
  schema_version: 3
  sources: SavedDiscoverySource[]
  results: Record<string, DiscoveryRadarResult>
  stats: Record<string, DiscoverySourceStats>
  findings: Record<string, DiscoveryFinding>
}

function nowIso() {
  return new Date().toISOString()
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
    schema_version: 3,
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

function validSource(value: unknown): value is SavedDiscoverySource {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const row = value as Partial<SavedDiscoverySource> & { origin?: string }
  return (
    typeof row.id === 'string' && row.id.length > 0 && row.id.length <= 96 &&
    typeof row.name === 'string' && row.name.length > 0 && row.name.length <= 100 &&
    typeof row.url === 'string' && row.url.startsWith('https://') && row.url.length <= 1200 &&
    isKind(row.kind) &&
    typeof row.enabled === 'boolean' &&
    row.origin === 'USER' &&
    typeof row.created_at === 'string' &&
    typeof row.updated_at === 'string'
  )
}

function findingKey(sourceId: string, url: string) {
  return `${sourceId}\u0000${url}`
}

function migrateLegacyWorkspace(): DiscoveryWorkspace | null {
  if (typeof window === 'undefined') return null
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
      .filter(validSource)
    const allowedIds = new Set(sources.map((source) => source.id))
    const results = Object.fromEntries(
      Object.entries(parsed.results ?? {}).filter(([sourceId]) => allowedIds.has(sourceId)),
    )
    const stats = Object.fromEntries(
      Object.entries(parsed.stats ?? {}).filter(([sourceId]) => allowedIds.has(sourceId)),
    )
    const workspace: DiscoveryWorkspace = { schema_version: 3, sources, results, stats, findings: {} }
    for (const result of Object.values(results)) {
      workspace.findings = mergeDiscoveryFindings(workspace.findings, result)
    }
    return workspace
  } catch {
    return null
  }
}

export function loadDiscoveryWorkspace(): DiscoveryWorkspace {
  if (typeof window === 'undefined') return emptyWorkspace()
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    const migrated = migrateLegacyWorkspace()
    const fresh = migrated ?? emptyWorkspace()
    saveDiscoveryWorkspace(fresh)
    return fresh
  }
  try {
    const parsed = JSON.parse(raw) as Partial<DiscoveryWorkspace>
    if (parsed.schema_version !== 3 || !Array.isArray(parsed.sources)) throw new Error('WORKSPACE_INVALID')
    return {
      schema_version: 3,
      sources: parsed.sources.filter(validSource),
      results: parsed.results && typeof parsed.results === 'object' ? parsed.results : {},
      stats: parsed.stats && typeof parsed.stats === 'object' ? parsed.stats : {},
      findings: parsed.findings && typeof parsed.findings === 'object' ? parsed.findings : {},
    }
  } catch {
    const fresh = emptyWorkspace()
    saveDiscoveryWorkspace(fresh)
    return fresh
  }
}

export function saveDiscoveryWorkspace(workspace: DiscoveryWorkspace) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace))
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
