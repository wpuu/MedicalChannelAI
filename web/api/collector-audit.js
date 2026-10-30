import { timingSafeEqual } from 'node:crypto'
import {
  collectorFailureAuditEnabled,
  listCollectorFailureAudit,
  persistCollectorFailureEvent,
} from './_collectorFailureAudit.js'

const MAX_REQUEST_BYTES = 1500

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.status(status).json(payload)
}

function bearerValue(request) {
  const raw = request?.headers?.authorization ?? request?.headers?.Authorization
  const str = Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
  return str.startsWith('Bearer ') ? str.slice(7).trim() : ''
}

export function authenticatedCollectorAuditRequest(request, env = process.env) {
  const expected = String(env.COLLECTOR_AUDIT_TOKEN || '').trim()
  const provided = bearerValue(request)
  if (expected.length < 32 || !provided || provided.length !== expected.length) return false
  const a = Buffer.from(provided, 'utf8')
  const b = Buffer.from(expected, 'utf8')
  return a.length === b.length && timingSafeEqual(a, b)
}

async function readBody(request) {
  if (request?.body !== undefined && request?.body !== null) {
    const raw = Buffer.isBuffer(request.body)
      ? request.body.toString('utf8')
      : typeof request.body === 'string'
        ? request.body
        : JSON.stringify(request.body)
    if (Buffer.byteLength(raw) > MAX_REQUEST_BYTES) throw new Error('COLLECTOR_AUDIT_BODY_TOO_LARGE')
    return JSON.parse(raw)
  }
  if (!request || typeof request[Symbol.asyncIterator] !== 'function') {
    throw new Error('COLLECTOR_AUDIT_BODY_MISSING')
  }
  const chunks = []
  let size = 0
  for await (const chunk of request) {
    const part = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    size += part.length
    if (size > MAX_REQUEST_BYTES) throw new Error('COLLECTOR_AUDIT_BODY_TOO_LARGE')
    chunks.push(part)
  }
  if (!chunks.length) throw new Error('COLLECTOR_AUDIT_BODY_MISSING')
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

export async function collectorAuditHandler(request, response, {
  env = process.env,
  store = persistCollectorFailureEvent,
  list = listCollectorFailureAudit,
} = {}) {
  // New endpoint is completely disabled until a separate audit-only token is
  // explicitly provisioned with the database on a future authorized release.
  if (!collectorFailureAuditEnabled(env)) {
    return sendJson(response, 503, { error: 'COLLECTOR_AUDIT_NOT_CONFIGURED' })
  }
  if (!authenticatedCollectorAuditRequest(request, env)) {
    response.setHeader('WWW-Authenticate', 'Bearer')
    return sendJson(response, 401, { error: 'UNAUTHORIZED' })
  }
  const method = String(request?.method || '').toUpperCase()
  if (method === 'POST') {
    let body
    try {
      body = await readBody(request)
    } catch {
      return sendJson(response, 400, { error: 'COLLECTOR_AUDIT_BAD_JSON' })
    }
    try {
      const receipt = await store(body)
      return sendJson(response, 200, { ok: true, event_id: receipt.event_id })
    } catch (error) {
      if (String(error?.message || '').startsWith('COLLECTOR_AUDIT_') &&
        !['COLLECTOR_AUDIT_DURABLE_READBACK_FAILED'].includes(error.message)) {
        return sendJson(response, 400, { error: 'COLLECTOR_AUDIT_INVALID_INPUT' })
      }
      return sendJson(response, 503, { error: 'COLLECTOR_AUDIT_PERSISTENCE_UNAVAILABLE' })
    }
  }
  if (method === 'GET') {
    try {
      const rawUrl = new URL(String(request?.url || ''), 'https://internal.invalid')
      const days = Number(rawUrl.searchParams.get('days') || '7')
      const limit = Number(rawUrl.searchParams.get('limit') || '250')
      const cycle_id = rawUrl.searchParams.get('cycle_id')
      const events = await list({ days, limit, cycle_id })
      return sendJson(response, 200, { ok: true, events, window_days: days })
    } catch (error) {
      if (String(error?.message || '').startsWith('COLLECTOR_AUDIT_QUERY_') ||
        String(error?.message || '').startsWith('COLLECTOR_AUDIT_CYCLE_')) {
        return sendJson(response, 400, { error: 'COLLECTOR_AUDIT_QUERY_INVALID' })
      }
      return sendJson(response, 503, { error: 'COLLECTOR_AUDIT_READ_UNAVAILABLE' })
    }
  }
  response.setHeader('Allow', 'GET, POST')
  return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
}

export default function handler(request, response) {
  return collectorAuditHandler(request, response)
}
