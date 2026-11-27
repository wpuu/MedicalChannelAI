import { privateDatabaseConfigured, privateDb } from './_privateDb.js'

// Kept behind the existing authenticated public-snapshot function to preserve
// the spare serverless slot on Hobby; no new scheduler, table, or secret.
const STAGES = new Set([
  'trigger', 'ccgp', 'event1', 'event2', 'event3', 'event4',
  'event5', 'event6', 'tjmugh', 'tjnothop', 'teda', 'tjfch',
  'tjzyefy_intent', 'regional_bj', 'regional_bj_fallback',
  'regional_he', 'regional_he_fallback', 'regional_ln',
  'regional_ln_fallback', 'regional_jl', 'regional_jl_fallback',
  'regional_hl', 'regional_hl_fallback', 'publish',
])
const STATUSES = new Set(['RUNNING', 'COMPLETED', 'FAILED'])
const CYCLE_ID = /^prod:\d{4}-\d{2}-\d{2}(?::(?:hospital-recovery-v1|recovery-v\d+))?$/
const SAFE_CODE = /^[A-Z][A-Z0-9_]{0,63}$/

export function validateCollectorAuditEvent(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('COLLECTOR_AUDIT_BODY_INVALID')
  }
  if (JSON.stringify(raw).length > 1600 || raw.schema_version !== '0.1') {
    throw new Error('COLLECTOR_AUDIT_SCHEMA_INVALID')
  }
  if (typeof raw.cycle_id !== 'string' || !CYCLE_ID.test(raw.cycle_id)) {
    throw new Error('COLLECTOR_AUDIT_CYCLE_ID_INVALID')
  }
  if (typeof raw.cycle_as_of !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T/.test(raw.cycle_as_of) ||
      !/(?:Z|[+-]\d{2}:\d{2})$/.test(raw.cycle_as_of) ||
      !Number.isFinite(Date.parse(raw.cycle_as_of))) {
    throw new Error('COLLECTOR_AUDIT_CLOCK_INVALID')
  }
  if (!STAGES.has(raw.stage)) throw new Error('COLLECTOR_AUDIT_STAGE_INVALID')
  if (!STATUSES.has(raw.status)) throw new Error('COLLECTOR_AUDIT_STATUS_INVALID')
  if (typeof raw.outcome !== 'string' || !SAFE_CODE.test(raw.outcome)) {
    throw new Error('COLLECTOR_AUDIT_OUTCOME_INVALID')
  }
  const errorCode = raw.error_code ?? null
  if (errorCode !== null && (typeof errorCode !== 'string' || !SAFE_CODE.test(errorCode))) {
    throw new Error('COLLECTOR_AUDIT_ERROR_CODE_INVALID')
  }
  const attempts = raw.attempt_count ?? null
  if (attempts !== null && (!Number.isInteger(attempts) || attempts < 0 || attempts > 20)) {
    throw new Error('COLLECTOR_AUDIT_ATTEMPTS_INVALID')
  }
  const verified = raw.new_verified_record_count ?? null
  if (verified !== null && (!Number.isInteger(verified) || verified < 0 || verified > 100000)) {
    throw new Error('COLLECTOR_AUDIT_VERIFIED_COUNT_INVALID')
  }
  return {
    id: raw.cycle_id + ':' + raw.stage,
    cycle_id: raw.cycle_id, cycle_as_of: raw.cycle_as_of,
    stage: raw.stage, status: raw.status,
    outcome: raw.outcome, error_code: errorCode,
    attempt_count: attempts, new_verified_record_count: verified,
  }
}

export async function persistCollectorAuditEvent(event) {
  if (!privateDatabaseConfigured()) throw new Error('COLLECTOR_AUDIT_DATABASE_UNAVAILABLE')
  const sql = privateDb()
  const now = new Date().toISOString()
  const summary = {
    cycle_id: event.cycle_id,
    cycle_as_of: event.cycle_as_of,
    outcome: event.outcome,
    error_code: event.error_code,
    attempt_count: event.attempt_count,
    new_verified_record_count: event.new_verified_record_count,
    reported_at: now,
  }
  // Existing table. A completed stage is immutable to duplicate Queue delivery;
  // FAILED -> RUNNING -> COMPLETED remains possible on a permitted retry.
  const query = [
    'INSERT INTO public_collector_runs',
    '(id, region_code, source_id, status, started_at, completed_at, summary)',
    'VALUES ($1, $2, $3, $4, $5::timestamptz, $6::timestamptz, $7::jsonb)',
    'ON CONFLICT (id) DO UPDATE SET',
    "status = CASE WHEN public_collector_runs.status = 'COMPLETED'",
    'THEN public_collector_runs.status ELSE EXCLUDED.status END,',
    "completed_at = CASE WHEN public_collector_runs.status = 'COMPLETED'",
    'THEN public_collector_runs.completed_at ELSE EXCLUDED.completed_at END,',
    "summary = CASE WHEN public_collector_runs.status = 'COMPLETED'",
    'THEN public_collector_runs.summary ELSE EXCLUDED.summary END',
    'RETURNING id, source_id, status',
  ].join(' ')
  const rows = await sql.unsafe(query, [
    event.id, 'CN-MULTI', event.stage, event.status, now,
    event.status === 'RUNNING' ? null : now, JSON.stringify(summary),
  ])
  if (!rows?.[0] || rows[0].id !== event.id) {
    throw new Error('COLLECTOR_AUDIT_WRITE_UNCONFIRMED')
  }
  return {
    id: rows[0].id,
    stage: rows[0].source_id,
    status: rows[0].status,
  }
}
