import { verifiedSnapshotUrl } from '@/config/snapshotConfig'

/**
 * Shared, read-only loader for the public verified snapshot (~1.5 MB JSON).
 *
 * Several demo-mode consumers (Today service, opportunity pool, AI decision
 * cache keying) previously downloaded and parsed the full snapshot
 * independently — including once per AI click just to read `snapshot_as_of`.
 * This module dedupes concurrent requests and reuses the parsed payload for a
 * short TTL so one page view costs at most one snapshot download.
 *
 * The returned payload is shared: callers must treat it as immutable and map
 * it into their own objects (all current consumers do).
 */
export const SNAPSHOT_CLIENT_TTL_MS = 60_000
const SAFE_SOURCE_ID = /^(?:[a-zA-Z0-9_.-]{1,80}|[a-zA-Z0-9_.-]{1,77}:[a-z]{2})$/

interface CacheEntry {
  url: string
  loadedAt: number
  payload: Promise<VerifiedSnapshotEnvelope>
}

export interface VerifiedSnapshotMeta {
  snapshot_as_of: string | null
  /** Source header from this exact response, or EXTERNAL/UNKNOWN when unavailable. */
  source: string
  runtime_origin?: 'PUBLISHED' | 'BUNDLED' | null
  degraded: boolean
  reason: string | null
  collection_coverage: {
    complete: boolean | null
    last_complete_as_of: string | null
    updated_source_ids: string[]
    failed_source_ids: string[]
  } | null
}

export interface VerifiedSnapshotEnvelope {
  payload: unknown
  meta: VerifiedSnapshotMeta
}

let entry: CacheEntry | null = null

function isFresh(current: CacheEntry | null, url: string, now: number): current is CacheEntry {
  return !!current && current.url === url && now - current.loadedAt < SNAPSHOT_CLIENT_TTL_MS
}

function sourceForResponse(response: Response, url: string): string {
  try {
    const requestOrigin = new URL(url, window.location.origin).origin
    const finalOrigin = response.url ? new URL(response.url, window.location.origin).origin : requestOrigin
    if (requestOrigin !== window.location.origin || finalOrigin !== window.location.origin) return 'EXTERNAL'
  } catch {
    return 'UNKNOWN'
  }
  const declared = response.headers.get('X-MedicalChannelAI-Snapshot-Source')?.trim().toUpperCase()
  if (declared) return declared
  return 'UNKNOWN'
}

export function loadVerifiedSnapshot(url: string = verifiedSnapshotUrl): Promise<VerifiedSnapshotEnvelope> {
  const now = Date.now()
  if (isFresh(entry, url, now)) return entry.payload
  const request = fetch(url, {
    headers: { Accept: 'application/json' },
    // Revalidate with the server's ETag rather than bypassing the HTTP cache.
    cache: 'no-cache',
  }).then(async (response) => {
    if (!response.ok) throw new Error(`SNAPSHOT_HTTP_${response.status}`)
    const payload = (await response.json()) as unknown
    const row = payload && typeof payload === 'object' ? payload as Record<string, unknown> : null
    const snapshotAsOf = typeof row?.snapshot_as_of === 'string' ? row.snapshot_as_of : null
    const source = sourceForResponse(response, url)
    const runtimeOriginHeader = response.headers.get('X-MedicalChannelAI-Snapshot-Runtime-Origin')?.trim().toUpperCase()
    const runtimeOrigin: VerifiedSnapshotMeta['runtime_origin'] = runtimeOriginHeader === 'PUBLISHED'
      ? 'PUBLISHED'
      : runtimeOriginHeader === 'BUNDLED'
        ? 'BUNDLED'
        : null
    const declaredDegraded = response.headers.get('X-MedicalChannelAI-Snapshot-Degraded') === 'true'
    const declaredReason = response.headers.get('X-MedicalChannelAI-Snapshot-Degraded-Reason')?.trim() || null
    const sourceKnown = ['DATABASE', 'BUNDLED', 'RUNTIME_CACHE', 'REMOTE', 'BUNDLED_FALLBACK'].includes(source)
    const validTime = snapshotAsOf !== null && !Number.isNaN(Date.parse(snapshotAsOf))
    const sourceFallback = source === 'BUNDLED_FALLBACK'
    const rawCoverage = row?.collection_coverage
    const coverageRow = rawCoverage && typeof rawCoverage === 'object' && !Array.isArray(rawCoverage)
      ? rawCoverage as Record<string, unknown>
      : null
    const headerComplete = response.headers.get('X-MedicalChannelAI-Snapshot-Coverage-Complete')
    const headerLastComplete = response.headers.get('X-MedicalChannelAI-Snapshot-Coverage-Last-Complete-As-Of')
    const coverageComplete = typeof coverageRow?.complete === 'boolean'
      ? coverageRow.complete
      : headerComplete === 'true'
        ? true
        : headerComplete === 'false'
          ? false
          : null
    const coverage = coverageComplete !== null
      ? {
          complete: coverageComplete,
          last_complete_as_of: typeof coverageRow?.last_complete_as_of === 'string'
            ? coverageRow.last_complete_as_of
            : headerLastComplete,
          updated_source_ids: Array.isArray(coverageRow?.updated_source_ids)
            ? coverageRow.updated_source_ids.filter((value): value is string => typeof value === 'string' && SAFE_SOURCE_ID.test(value)).slice(0, 20)
            : [],
          failed_source_ids: Array.isArray(coverageRow?.failed_source_ids)
            ? coverageRow.failed_source_ids.filter((value): value is string => typeof value === 'string' && SAFE_SOURCE_ID.test(value)).slice(0, 20)
            : [],
        }
      : null
    const partialCoverage = coverage?.complete === false
    const unknownCoverage = coverage === null
    return {
      payload,
      meta: {
        snapshot_as_of: snapshotAsOf,
        source,
        runtime_origin: runtimeOrigin,
        degraded: declaredDegraded || !sourceKnown || !validTime || sourceFallback || partialCoverage || unknownCoverage,
        reason: declaredReason || (!sourceKnown ? 'SNAPSHOT_SOURCE_UNKNOWN' : !validTime ? 'SNAPSHOT_CLOCK_INVALID' : sourceFallback ? 'SNAPSHOT_SOURCE_FALLBACK' : partialCoverage ? 'COLLECTION_COVERAGE_PARTIAL' : unknownCoverage ? 'COLLECTION_COVERAGE_UNKNOWN' : null),
        collection_coverage: coverage,
      },
    }
  })
  const created: CacheEntry = { url, loadedAt: now, payload: request }
  entry = created
  // Failed loads must not be memoized; the next caller retries immediately.
  request.catch(() => {
    if (entry === created) entry = null
  })
  return request
}

export async function loadVerifiedSnapshotPayload(url: string = verifiedSnapshotUrl): Promise<unknown> {
  return (await loadVerifiedSnapshot(url)).payload
}

export async function getVerifiedSnapshotAsOf(url: string = verifiedSnapshotUrl): Promise<string | null> {
  try {
    const payload = (await loadVerifiedSnapshot(url)).payload
    const value = payload && typeof payload === 'object' ? (payload as Record<string, unknown>).snapshot_as_of : null
    return typeof value === 'string' && !Number.isNaN(Date.parse(value)) ? value : null
  } catch {
    return null
  }
}

/** Test/refresh hook: forget the memoized payload. */
export function resetVerifiedSnapshotClient(): void {
  entry = null
}
