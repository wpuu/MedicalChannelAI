// Source clocks belong to the committed snapshot. Collector candidates and the
// time of an unrelated source's publish are never evidence of a successful scan.
export const REQUIRED_SOURCE_IDS = Object.freeze([
  'ccgp', 'tjmugh', 'tjnothop', 'teda', 'tjfch', 'tjfch_test',
  'tjzyefy', 'tjzyefy_intent', 'tjzxfc',
  'regional_bj', 'regional_he', 'regional_ln', 'regional_jl', 'regional_hl',
])
const REQUIRED_SOURCE_SET = new Set(REQUIRED_SOURCE_IDS)
export const SOURCE_STALE_AFTER_SECONDS = Object.freeze(Object.fromEntries(
  REQUIRED_SOURCE_IDS.map((id) => [id, (id === 'ccgp' || id.startsWith('regional_') ? 48 : 24) * 60 * 60]),
))
const FUTURE_TOLERANCE_MS = 15 * 60 * 1000

function object(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function timestamp(value, nowMs) {
  if (typeof value !== 'string' || !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) && parsed <= nowMs + FUTURE_TOLERANCE_MS ? parsed : null
}

function evaluateSource(sourceId, raw, nowMs) {
  const row = object(raw)
  const success = timestamp(row?.last_successful_scan_at, nowMs)
  const attempt = timestamp(row?.last_attempt_at, nowMs)
  const threshold = row?.stale_after_seconds
  const thresholdValid = Number.isInteger(threshold) && threshold > 0 && threshold <= SOURCE_STALE_AFTER_SECONDS[sourceId]
  const failed = typeof row?.failure_reason === 'string' && row.failure_reason.trim().length > 0
  const failureReason = failed
    ? (/^[A-Z][A-Z0-9_]{0,79}$/.test(row.failure_reason) ? row.failure_reason : 'SOURCE_SCAN_FAILED')
    : null
  const ageSeconds = success === null ? null : Math.max(0, Math.floor((nowMs - success) / 1000))
  let status = 'UNKNOWN'
  if (row && thresholdValid && Number.isFinite(nowMs)) {
    const invalidAttempt = row.last_attempt_at != null && attempt === null
    if (!invalidAttempt && failed && attempt !== null && (success === null || attempt >= success)) status = 'FAILING'
    else if (!invalidAttempt && success !== null && !failed) status = ageSeconds > threshold ? 'STALE' : 'HEALTHY'
  }
  return {
    last_successful_scan_at: success === null ? null : row.last_successful_scan_at,
    last_attempt_at: attempt === null ? null : row.last_attempt_at,
    stale_after_seconds: thresholdValid ? threshold : SOURCE_STALE_AFTER_SECONDS[sourceId],
    failure_reason: failureReason,
    status,
    age_seconds: ageSeconds,
  }
}

export function evaluateSourceHealth(snapshot, nowMs = Date.now()) {
  const metadata = object(snapshot?.source_health)
  const rawSources = metadata?.schema_version === '0.1' ? object(metadata.sources) : null
  const sources = Object.fromEntries(REQUIRED_SOURCE_IDS.map((id) => [id, evaluateSource(id, rawSources?.[id], nowMs)]))
  const statuses = Object.values(sources).map((row) => row.status)
  const status = ['FAILING', 'STALE', 'UNKNOWN'].find((value) => statuses.includes(value)) || 'HEALTHY'
  return {
    schema_version: '0.1',
    status,
    required_source_count: REQUIRED_SOURCE_IDS.length,
    healthy_source_count: statuses.filter((value) => value === 'HEALTHY').length,
    sources,
  }
}

export function sourceIdsForOpportunity(card) {
  const explicit = card?.source_id ?? card?.facts?.source_id
  if (explicit != null) return REQUIRED_SOURCE_SET.has(explicit) ? [explicit] : []
  const id = String(card?.opportunity_id ?? card?.opportunityId ?? '').toLowerCase()
  const regional = /^ccgp_(bj|he|ln|jl|hl)_/.exec(id)
  if (regional) return [`regional_${regional[1]}`]
  if (id.startsWith('ccgp_')) return ['ccgp']
  if (id.startsWith('tjzyefy_intent_')) return ['tjzyefy_intent']
  // Legacy first-central IDs do not distinguish the two official feeds.
  if (id.startsWith('tjfch_')) return ['tjfch', 'tjfch_test']
  for (const sourceId of ['tjmugh', 'tjnothop', 'teda', 'tjzyefy', 'tjzxfc']) {
    if (id.startsWith(`${sourceId}_`)) return [sourceId]
  }
  return []
}
