import type { DiscoveryContinuationSegment } from './discoveryContinuationApi'
import type { DiscoveryFinding, DiscoveryWorkspace } from './discoveryRadarStore'

function findingKey(sourceId: string, url: string) {
  return `${sourceId}\u0000${url}`
}

function timestamp(value: string) {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY
}

/**
 * Merge one continuation observation into the cumulative discovery ledger.
 * The operation is idempotent for a previously persisted segment: replaying the
 * same checked_at does not increment times_seen again.
 */
export function mergeDiscoveryContinuationFindings(
  current: Record<string, DiscoveryFinding>,
  segment: DiscoveryContinuationSegment,
): Record<string, DiscoveryFinding> {
  if (segment.candidates.length === 0) return current

  let next = current
  const observedAt = timestamp(segment.checked_at)
  for (const candidate of segment.candidates) {
    const key = findingKey(segment.source_id, candidate.url)
    const existing = next[key]
    if (existing) {
      const existingAt = timestamp(existing.last_seen_at)
      if (existing.last_seen_at === segment.checked_at || existingAt > observedAt) continue
    }

    if (next === current) next = { ...current }
    const previous = next[key]
    next[key] = {
      ...candidate,
      finding_key: key,
      source_id: segment.source_id,
      source_name: segment.source_name,
      source_url: segment.source_url,
      first_seen_at: previous?.first_seen_at ?? segment.analyzed_at ?? segment.checked_at,
      last_seen_at: segment.checked_at,
      times_seen: (previous?.times_seen ?? 0) + 1,
      active_in_latest_scan: true,
    }
  }
  return next
}

export function mergeDiscoveryContinuationIntoWorkspace(
  workspace: DiscoveryWorkspace,
  segment: DiscoveryContinuationSegment,
): DiscoveryWorkspace {
  const sourceStillExists = workspace.sources.some(
    (source) => source.id === segment.source_id && source.url === segment.source_url,
  )
  if (!sourceStillExists) return workspace

  const findings = mergeDiscoveryContinuationFindings(workspace.findings, segment)
  return findings === workspace.findings ? workspace : { ...workspace, findings }
}
