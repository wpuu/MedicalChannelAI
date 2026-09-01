import {
  loadVerifiedSnapshot,
  verifiedSnapshotSourceMode,
} from './_verifiedSnapshot.js'

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.setHeader('Cache-Control', 'public, max-age=0, s-maxage=60, stale-while-revalidate=120')
  response.status(status).json(payload)
}

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }

  try {
    const snapshot = await loadVerifiedSnapshot()
    response.setHeader('X-MedicalChannelAI-Snapshot-Source', verifiedSnapshotSourceMode())
    return sendJson(response, 200, snapshot)
  } catch {
    response.setHeader('Cache-Control', 'no-store, max-age=0')
    return sendJson(response, 503, { error: 'VERIFIED_SNAPSHOT_UNAVAILABLE' })
  }
}
