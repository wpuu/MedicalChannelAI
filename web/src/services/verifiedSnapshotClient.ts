import { verifiedSnapshotUrl } from '@/config/snapshotConfig'
import { normalizeAwardEvidenceSnapshot } from '../../shared/awardEvidence.js'

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

interface CacheEntry {
  url: string
  loadedAt: number
  payload: Promise<unknown>
}

let entry: CacheEntry | null = null

function isFresh(current: CacheEntry | null, url: string, now: number): current is CacheEntry {
  return !!current && current.url === url && now - current.loadedAt < SNAPSHOT_CLIENT_TTL_MS
}

export function loadVerifiedSnapshotPayload(url: string = verifiedSnapshotUrl): Promise<unknown> {
  const now = Date.now()
  if (isFresh(entry, url, now)) return entry.payload
  const payload = fetch(url, {
    headers: { Accept: 'application/json' },
    // Revalidate with the server's ETag rather than bypassing the HTTP cache.
    cache: 'no-cache',
  }).then(async (response) => {
    if (!response.ok) throw new Error(`SNAPSHOT_HTTP_${response.status}`)
    return normalizeAwardEvidenceSnapshot((await response.json()) as unknown)
  })
  const created: CacheEntry = { url, loadedAt: now, payload }
  entry = created
  // Failed loads must not be memoized; the next caller retries immediately.
  payload.catch(() => {
    if (entry === created) entry = null
  })
  return payload
}

export async function getVerifiedSnapshotAsOf(url: string = verifiedSnapshotUrl): Promise<string | null> {
  try {
    const payload = await loadVerifiedSnapshotPayload(url)
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
