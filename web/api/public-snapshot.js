import { timingSafeEqual } from 'node:crypto'
import {
  loadVerifiedSnapshot,
  publishVerifiedSnapshotToRuntimeCache,
  verifiedSnapshotSourceMode,
} from './_verifiedSnapshot.js'

function sendJson(response, status, payload, { cacheable = false } = {}) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.setHeader(
    'Cache-Control',
    cacheable
      ? 'public, max-age=0, s-maxage=60, stale-while-revalidate=120'
      : 'no-store, max-age=0',
  )
  response.status(status).json(payload)
}

function headerValue(request, name) {
  const headers = request?.headers
  if (!headers) return ''
  if (typeof headers.get === 'function') return String(headers.get(name) || '').trim()
  const lower = name.toLowerCase()
  const value = headers[lower] ?? headers[name]
  return Array.isArray(value) ? String(value[0] || '').trim() : String(value || '').trim()
}

function configuredPublishToken() {
  return String(process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN || '').trim()
}

function authorizedPublisher(request, expectedToken) {
  const authorization = headerValue(request, 'authorization')
  if (!authorization.startsWith('Bearer ')) return false
  const supplied = authorization.slice('Bearer '.length).trim()
  if (!supplied || !expectedToken || supplied.length !== expectedToken.length) return false
  return timingSafeEqual(Buffer.from(supplied), Buffer.from(expectedToken))
}

async function requestBodyValue(request) {
  if (request?.body !== undefined && request?.body !== null) {
    if (Buffer.isBuffer(request.body)) return JSON.parse(request.body.toString('utf8'))
    if (typeof request.body === 'string') return JSON.parse(request.body)
    return request.body
  }

  if (!request || typeof request[Symbol.asyncIterator] !== 'function') {
    throw new Error('VERIFIED_SNAPSHOT_PUBLISH_BODY_REQUIRED')
  }
  const chunks = []
  for await (const chunk of request) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  if (chunks.length === 0) throw new Error('VERIFIED_SNAPSHOT_PUBLISH_BODY_REQUIRED')
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

function publishFailureStatus(error) {
  const code = String(error?.message || '')
  if (
    code === 'RUNTIME_SNAPSHOT_ROLLBACK_REJECTED' ||
    code === 'RUNTIME_SNAPSHOT_REVISION_CONFLICT' ||
    code === 'RUNTIME_SNAPSHOT_OLDER_THAN_BUNDLE' ||
    code === 'RUNTIME_SNAPSHOT_FUTURE_REJECTED'
  ) return 409
  if (
    code.startsWith('VERIFIED_SNAPSHOT_') ||
    code === 'RUNTIME_SNAPSHOT_TOO_LARGE' ||
    error instanceof SyntaxError
  ) return 400
  return 503
}

async function publishSnapshot(request, response) {
  const expectedToken = configuredPublishToken()
  if (expectedToken.length < 24) {
    return sendJson(response, 503, { error: 'VERIFIED_SNAPSHOT_PUBLISH_NOT_CONFIGURED' })
  }
  if (!authorizedPublisher(request, expectedToken)) {
    response.setHeader('WWW-Authenticate', 'Bearer')
    return sendJson(response, 401, { error: 'UNAUTHORIZED' })
  }

  try {
    const snapshot = await requestBodyValue(request)
    const published = await publishVerifiedSnapshotToRuntimeCache(snapshot)
    const pool = Array.isArray(published.opportunity_pool) ? published.opportunity_pool : published.cards
    return sendJson(response, 200, {
      ok: true,
      snapshot_as_of: published.snapshot_as_of,
      today_card_count: Array.isArray(published.cards) ? published.cards.length : 0,
      opportunity_pool_count: Array.isArray(pool) ? pool.length : 0,
    })
  } catch (error) {
    return sendJson(response, publishFailureStatus(error), {
      error: String(error?.message || 'VERIFIED_SNAPSHOT_PUBLISH_FAILED'),
    })
  }
}

export default async function handler(request, response) {
  if (request.method === 'PUT' || request.method === 'POST') {
    return publishSnapshot(request, response)
  }
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET, PUT, POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }

  try {
    const snapshot = await loadVerifiedSnapshot()
    response.setHeader('X-MedicalChannelAI-Snapshot-Source', verifiedSnapshotSourceMode())
    return sendJson(response, 200, snapshot, { cacheable: true })
  } catch {
    return sendJson(response, 503, { error: 'VERIFIED_SNAPSHOT_UNAVAILABLE' })
  }
}
