import { loadVerifiedSnapshot, verifiedSnapshotSourceMode } from './_verifiedSnapshot.js'

const APP_VERSION = '0.3.7'
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
  return Boolean((process.env.VERIFIED_SNAPSHOT_URL || process.env.VITE_VERIFIED_SNAPSHOT_URL || '').trim())
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
    const snapshot = await loadVerifiedSnapshot()
    const sourceMode = verifiedSnapshotSourceMode()
    const pool = Array.isArray(snapshot.opportunity_pool) ? snapshot.opportunity_pool : snapshot.cards
    const freshness = snapshotFreshness(snapshot.snapshot_as_of)
    const fallbackDegraded = sourceMode === 'BUNDLED_FALLBACK'
    return sendJson(response, freshness.freshness === 'INVALID' ? 503 : 200, {
      ...base,
      ready: freshness.freshness !== 'INVALID',
      degraded: freshness.degraded || fallbackDegraded,
      snapshot: {
        available: true, source_mode: sourceMode, snapshot_as_of: snapshot.snapshot_as_of ?? null,
        freshness: freshness.freshness, age_minutes: freshness.age_minutes,
        stale_after_minutes: SNAPSHOT_STALE_AFTER_MINUTES,
        today_card_count: Array.isArray(snapshot.cards) ? snapshot.cards.length : 0,
        opportunity_pool_count: Array.isArray(pool) ? pool.length : 0,
      },
    })
  } catch {
    const mode = verifiedSnapshotSourceMode()
    const failureMode = remoteConfigured() ? (mode === 'REMOTE' ? 'REMOTE' : 'UNAVAILABLE') : 'UNAVAILABLE'
    return sendJson(response, 503, {
      ...base, ready: false, degraded: true,
      snapshot: {
        available: false, source_mode: failureMode, snapshot_as_of: null,
        freshness: 'UNAVAILABLE', age_minutes: null, stale_after_minutes: SNAPSHOT_STALE_AFTER_MINUTES,
        today_card_count: 0, opportunity_pool_count: 0,
      },
    })
  }
}
