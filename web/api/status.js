import { loadVerifiedSnapshotWithMetadata, loadCollectorCollectionStatus } from './_verifiedSnapshot.js'

const APP_VERSION = '0.5.0'
const SNAPSHOT_STALE_AFTER_MINUTES = 30 * 60
const SNAPSHOT_FUTURE_TOLERANCE_MINUTES = 15

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.status(status).json(payload)
}
function aiConfigured() {
  const raw = process.env.AGNES_API_KEYS || process.env.AGNES_API_KEY || ''
  return raw.split(/[\n,;]+/).map((value) => value.trim()).some(Boolean)
}
function buildCommit() {
  const value = String(process.env.VERCEL_GIT_COMMIT_SHA || '').trim()
  return value ? value.slice(0, 7) : null
}
function remoteConfigured() {
  const raw = (process.env.VERIFIED_SNAPSHOT_URL || process.env.VITE_VERIFIED_SNAPSHOT_URL || '').trim()
  if (!raw) return false
  try {
    const url = new URL(raw)
    return url.protocol === 'https:' || (process.env.NODE_ENV !== 'production' &&
      (url.hostname === 'localhost' || url.hostname === '127.0.0.1') && url.protocol === 'http:')
  } catch {
    return false
  }
}
export function snapshotFreshness(snapshotAsOf, nowMs = Date.now()) {
  const parsed = Date.parse(snapshotAsOf || '')
  if (Number.isNaN(parsed)) return { freshness: 'INVALID', age_minutes: null, degraded: true }
  const rawAgeMinutes = (nowMs - parsed) / 60_000
  if (rawAgeMinutes < -SNAPSHOT_FUTURE_TOLERANCE_MINUTES) return { freshness: 'INVALID', age_minutes: null, degraded: true }
  const ageMinutes = Math.max(0, Math.floor(rawAgeMinutes))
  if (ageMinutes > SNAPSHOT_STALE_AFTER_MINUTES) return { freshness: 'STALE', age_minutes: ageMinutes, degraded: true }
  return { freshness: 'FRESH', age_minutes: ageMinutes, degraded: false }
}

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  const base = {
    schema_version: '0.1', service: 'MedicalChannelAI', version: APP_VERSION,
    commit: buildCommit(), production_ready: false, ai: { configured: aiConfigured() },
  }
  try {
    const loaded = await loadVerifiedSnapshotWithMetadata()
    const snapshot = loaded.snapshot
    const sourceMode = loaded.sourceMode
    const runtimeOrigin = loaded.runtimeOrigin
    const collection = await loadCollectorCollectionStatus()
    const pool = Array.isArray(snapshot.opportunity_pool) ? snapshot.opportunity_pool : snapshot.cards
    const freshness = snapshotFreshness(snapshot.snapshot_as_of)
    const collectionHealthy = collection.available && collection.outcome === 'COMPLETED'
    const coverage = snapshot.collection_coverage && typeof snapshot.collection_coverage.complete === 'boolean'
      ? snapshot.collection_coverage
      : null
    const coverageDegraded = coverage?.complete !== true
    const collectorDegraded = !collectionHealthy
    const degraded = freshness.degraded || loaded.degraded || coverageDegraded || collectorDegraded
    const degradedReason = loaded.reason || (coverageDegraded ? 'COLLECTION_COVERAGE_UNKNOWN' : null) ||
      (collection.outcome === 'FAILED' || collection.outcome === 'BLOCKED' ? `COLLECTION_${collection.outcome}` : !collectionHealthy ? 'COLLECTION_STATUS_UNKNOWN' : null)
    return sendJson(response, freshness.freshness === 'INVALID' ? 503 : 200, {
      ...base,
      ready: freshness.freshness !== 'INVALID',
      degraded,
      degraded_reason: degradedReason,
      collection,
      snapshot: {
        available: true, source_mode: sourceMode,
        runtime_origin: sourceMode === 'RUNTIME_CACHE' ? runtimeOrigin : null,
        snapshot_as_of: snapshot.snapshot_as_of ?? null,
        freshness: freshness.freshness, age_minutes: freshness.age_minutes,
        degraded: loaded.degraded || coverageDegraded,
        degraded_reason: loaded.reason || (coverageDegraded ? 'COLLECTION_COVERAGE_UNKNOWN' : null),
        collection_coverage: coverage,
        stale_after_minutes: SNAPSHOT_STALE_AFTER_MINUTES,
        today_card_count: Array.isArray(snapshot.cards) ? snapshot.cards.length : 0,
        opportunity_pool_count: Array.isArray(pool) ? pool.length : 0,
      },
    })
  } catch {
    const failureMode = remoteConfigured() ? 'REMOTE' : 'UNAVAILABLE'
    const collection = await loadCollectorCollectionStatus()
    return sendJson(response, 503, {
      ...base, ready: false, degraded: true, degraded_reason: 'SNAPSHOT_LOAD_FAILED', collection,
      snapshot: {
        available: false, source_mode: failureMode, runtime_origin: null, snapshot_as_of: null,
        freshness: 'UNAVAILABLE', age_minutes: null, stale_after_minutes: SNAPSHOT_STALE_AFTER_MINUTES,
        today_card_count: 0, opportunity_pool_count: 0,
      },
    })
  }
}
