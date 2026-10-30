import { createHash } from 'node:crypto'
import { privateDatabaseConfigured, privateDb } from './_privateDb.js'

// C05: independent immutable audit events; NEVER authorizes a collector
// mutation or a verified snapshot. This code is dormant unless the private
// database, an explicit enabled flag and a separate 32+ char audit token exist.
// In particular, do not reuse the much more powerful snapshot publish token.
const ALLOWED_EVENTS = new Set([
  'CRON_QUEUE_FAILED',
  'STAGE_RETRY_ERROR',
  'STAGE_TERMINAL_FAILURE',
  'SOURCE_WINDOW_BLOCKED',
])
const CYCLE = /^prod:\d{4}-\d{2}-\d{2}:(morning|noon):twice-daily-v1$/
const STAGE = /^[a-z][a-z0-9_]{1,30}$/
const ERROR = /^[A-Z][A-Z0-9_]{2,79}$/
const ID64 = /^[a-f0-9]{64}$/
const MAX_AGE_MS = 8 * 24 * 3600_000
const FUTURE_TOLERANCE_MS = 10 * 60_000

export const COLLECTOR_AUDIT_DDL = [
  `CREATE TABLE IF NOT EXISTS public_collector_audit_events (
    event_id TEXT PRIMARY KEY CHECK (length(event_id) = 64),
    cycle_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN (
      'CRON_QUEUE_FAILED', 'STAGE_RETRY_ERROR',
      'STAGE_TERMINAL_FAILURE', 'SOURCE_WINDOW_BLOCKED'
    )),
    error_code TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
  )`,
  `CREATE INDEX IF NOT EXISTS public_collector_audit_events_cycle_idx
    ON public_collector_audit_events (cycle_id, occurred_at DESC)`,
  `CREATE INDEX IF NOT EXISTS public_collector_audit_events_recorded_idx
    ON public_collector_audit_events (recorded_at DESC)`,
]

export function collectorFailureAuditEnabled(env = process.env) {
  const enabled = String(env.COLLECTOR_AUDIT_ENABLED || '').trim() === 'true'
  const token = String(env.COLLECTOR_AUDIT_TOKEN || '').trim()
  return enabled && token.length >= 32 && privateDatabaseConfigured()
}

export function validateCollectorFailureEvent(input, now = new Date()) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error('COLLECTOR_AUDIT_BODY_INVALID')
  }
  if (Object.keys(input).sort().join('|') !==
    ['cycle_id', 'error_code', 'event_kind', 'occurred_at', 'stage_id'].sort().join('|')) {
    throw new Error('COLLECTOR_AUDIT_FIELDS_INVALID')
  }
  const { cycle_id, stage_id, event_kind, error_code, occurred_at } = input
  if (typeof cycle_id !== 'string' || !CYCLE.test(cycle_id)) {
    throw new Error('COLLECTOR_AUDIT_CYCLE_INVALID')
  }
  if (typeof stage_id !== 'string' || !STAGE.test(stage_id)) {
    throw new Error('COLLECTOR_AUDIT_STAGE_INVALID')
  }
  if (!ALLOWED_EVENTS.has(event_kind)) throw new Error('COLLECTOR_AUDIT_KIND_INVALID')
  if (typeof error_code !== 'string' || !ERROR.test(error_code)) {
    throw new Error('COLLECTOR_AUDIT_ERROR_CODE_INVALID')
  }
  if (typeof occurred_at !== 'string' || occurred_at.length > 45) {
    throw new Error('COLLECTOR_AUDIT_TIME_INVALID')
  }
  const occurredMs = Date.parse(occurred_at)
  const nowMs = now.getTime()
  if (!Number.isFinite(occurredMs) ||
    occurredMs < nowMs - MAX_AGE_MS || occurredMs > nowMs + FUTURE_TOLERANCE_MS) {
    throw new Error('COLLECTOR_AUDIT_TIME_OUT_OF_RANGE')
  }
  const datePart = cycle_id.split(':')[1]
  const occurredDate = new Date(occurredMs).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' })
  if (datePart !== occurredDate) throw new Error('COLLECTOR_AUDIT_CYCLE_DATE_MISMATCH')
  if (event_kind === 'CRON_QUEUE_FAILED' && stage_id !== 'ccgp') {
    throw new Error('COLLECTOR_AUDIT_TRIGGER_STAGE_INVALID')
  }
  const canonical = JSON.stringify([cycle_id, stage_id, event_kind, error_code, new Date(occurredMs).toISOString()])
  return {
    event_id: createHash('sha256').update(canonical).digest('hex'),
    cycle_id, stage_id, event_kind, error_code,
    occurred_at: new Date(occurredMs).toISOString(),
  }
}

export async function ensureCollectorFailureAuditSchema(sql) {
  // Explicitly opt-in and authenticated endpoint ONLY; no automatic
  // migration of existing public/schema tables from normal app traffic.
  for (const ddl of COLLECTOR_AUDIT_DDL) await sql.unsafe(ddl)
}

export async function persistCollectorFailureEvent(input, { sql = privateDb(), now = new Date() } = {}) {
  const evt = validateCollectorFailureEvent(input, now)
  await ensureCollectorFailureAuditSchema(sql)
  await sql`
    INSERT INTO public_collector_audit_events (
      event_id, cycle_id, stage_id, event_kind, error_code, occurred_at
    ) VALUES (
      ${evt.event_id}, ${evt.cycle_id}, ${evt.stage_id}, ${evt.event_kind},
      ${evt.error_code}, ${evt.occurred_at}
    )
    ON CONFLICT (event_id) DO NOTHING
  `
  const readback = await sql`
    SELECT event_id, cycle_id, stage_id, event_kind, error_code, occurred_at
    FROM public_collector_audit_events WHERE event_id = ${evt.event_id}
  `
  const row = readback?.[0]
  if (!row || row.event_id !== evt.event_id ||
    row.cycle_id !== evt.cycle_id || row.stage_id !== evt.stage_id ||
    row.event_kind !== evt.event_kind || row.error_code !== evt.error_code ||
    new Date(row.occurred_at).getTime() !== Date.parse(evt.occurred_at)) {
    throw new Error('COLLECTOR_AUDIT_DURABLE_READBACK_FAILED')
  }
  return { accepted: true, event_id: evt.event_id, occurred_at: evt.occurred_at }
}

export async function listCollectorFailureAudit({
  days = 7, limit = 250, cycle_id = null, sql = privateDb(),
} = {}) {
  if (!Number.isInteger(days) || days < 1 || days > 7 ||
    !Number.isInteger(limit) || limit < 1 || limit > 250) {
    throw new Error('COLLECTOR_AUDIT_QUERY_INVALID')
  }
  if (cycle_id !== null && (typeof cycle_id !== 'string' || !CYCLE.test(cycle_id))) {
    throw new Error('COLLECTOR_AUDIT_CYCLE_INVALID')
  }
  await ensureCollectorFailureAuditSchema(sql)
  // Read only the last 7 days; no organization names, raw URLs, request
  // bodies, tokens, or user data can ever be present in this table.
  const rows = cycle_id === null
    ? await sql`
      SELECT event_id, cycle_id, stage_id, event_kind, error_code, occurred_at, recorded_at
      FROM public_collector_audit_events
      WHERE occurred_at >= now() - make_interval(days => ${days})
      ORDER BY occurred_at DESC LIMIT ${limit}
    `
    : await sql`
      SELECT event_id, cycle_id, stage_id, event_kind, error_code, occurred_at, recorded_at
      FROM public_collector_audit_events
      WHERE occurred_at >= now() - make_interval(days => ${days})
      AND cycle_id = ${cycle_id}
      ORDER BY occurred_at DESC LIMIT ${limit}
    `
  return rows.map(row => ({
    event_id: row.event_id,
    cycle_id: row.cycle_id,
    stage_id: row.stage_id,
    event_kind: row.event_kind,
    error_code: row.error_code,
    occurred_at: new Date(row.occurred_at).toISOString(),
    recorded_at: new Date(row.recorded_at).toISOString(),
  }))
}
