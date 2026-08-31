import {
  loadVerifiedSnapshot,
  verifiedSnapshotSourceMode,
} from './_verifiedSnapshot.js'

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.status(status).json(payload)
}

function aiConfigured() {
  const raw = process.env.AGNES_API_KEYS || process.env.AGNES_API_KEY || ''
  return raw
    .split(/[\n,;]+/)
    .map((value) => value.trim())
    .some(Boolean)
}

function safeSourceMode() {
  try {
    return verifiedSnapshotSourceMode()
  } catch {
    return 'UNAVAILABLE'
  }
}

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }

  const base = {
    schema_version: '0.1',
    service: 'MedicalChannelAI',
    production_ready: false,
    ai: {
      configured: aiConfigured(),
    },
  }

  try {
    const snapshot = await loadVerifiedSnapshot()
    const pool = Array.isArray(snapshot.opportunity_pool)
      ? snapshot.opportunity_pool
      : snapshot.cards
    return sendJson(response, 200, {
      ...base,
      ready: true,
      snapshot: {
        available: true,
        source_mode: safeSourceMode(),
        snapshot_as_of: snapshot.snapshot_as_of ?? null,
        today_card_count: Array.isArray(snapshot.cards) ? snapshot.cards.length : 0,
        opportunity_pool_count: Array.isArray(pool) ? pool.length : 0,
      },
    })
  } catch {
    return sendJson(response, 503, {
      ...base,
      ready: false,
      snapshot: {
        available: false,
        source_mode: safeSourceMode(),
        snapshot_as_of: null,
        today_card_count: 0,
        opportunity_pool_count: 0,
      },
    })
  }
}
