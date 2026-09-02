import type {
  DiscoveryRadarResult,
  DiscoverySourceInput,
  DiscoverySourceKind,
} from './discoveryRadarApi'

const STORAGE_KEY = 'medicalchannelai.discovery.workspace.v2'

export interface SavedDiscoverySource extends DiscoverySourceInput {
  enabled: boolean
  origin: 'STARTER' | 'USER'
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

export interface DiscoveryWorkspace {
  schema_version: 2
  sources: SavedDiscoverySource[]
  results: Record<string, DiscoveryRadarResult>
  stats: Record<string, DiscoverySourceStats>
}

const STARTER_SOURCES: Array<Pick<SavedDiscoverySource, 'id' | 'name' | 'url' | 'kind' | 'origin'>> = [
  {
    id: 'starter-tjmugh',
    name: '天津医科大学总医院',
    url: 'https://www.tjmugh.com.cn/cgxxtzgg/index.shtml',
    kind: 'HOSPITAL_OFFICIAL',
    origin: 'STARTER',
  },
  {
    id: 'starter-tjnothop',
    name: '天津市天津医院',
    url: 'https://www.tjnothop.cn/xwzx/index.shtml',
    kind: 'HOSPITAL_OFFICIAL',
    origin: 'STARTER',
  },
  {
    id: 'starter-teda',
    name: '天津泰达医院',
    url: 'https://www.tedahospital.com.cn/article/plist/9',
    kind: 'HOSPITAL_OFFICIAL',
    origin: 'STARTER',
  },
]

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

function starterWorkspace(): DiscoveryWorkspace {
  const now = nowIso()
  return {
    schema_version: 2,
    sources: STARTER_SOURCES.map((item) => ({
      ...item,
      enabled: true,
      created_at: now,
      updated_at: now,
    })),
    results: {},
    stats: {},
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
  const row = value as Partial<SavedDiscoverySource>
  return (
    typeof row.id === 'string' && row.id.length > 0 && row.id.length <= 96 &&
    typeof row.name === 'string' && row.name.length > 0 && row.name.length <= 100 &&
    typeof row.url === 'string' && row.url.startsWith('https://') && row.url.length <= 1200 &&
    isKind(row.kind) &&
    typeof row.enabled === 'boolean' &&
    (row.origin === 'STARTER' || row.origin === 'USER') &&
    typeof row.created_at === 'string' &&
    typeof row.updated_at === 'string'
  )
}

export function loadDiscoveryWorkspace(): DiscoveryWorkspace {
  if (typeof window === 'undefined') return starterWorkspace()
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    const fresh = starterWorkspace()
    saveDiscoveryWorkspace(fresh)
    return fresh
  }
  try {
    const parsed = JSON.parse(raw) as Partial<DiscoveryWorkspace>
    if (parsed.schema_version !== 2 || !Array.isArray(parsed.sources)) throw new Error('WORKSPACE_INVALID')
    return {
      schema_version: 2,
      sources: parsed.sources.filter(validSource),
      results: parsed.results && typeof parsed.results === 'object' ? parsed.results : {},
      stats: parsed.stats && typeof parsed.stats === 'object' ? parsed.stats : {},
    }
  } catch {
    const fresh = starterWorkspace()
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
