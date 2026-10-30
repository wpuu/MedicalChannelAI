import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  COLLECTOR_AUDIT_DDL,
  validateCollectorFailureEvent,
  persistCollectorFailureEvent,
  listCollectorFailureAudit,
} from '../api/_collectorFailureAudit.js'
import { authenticatedCollectorAuditRequest, collectorAuditHandler } from '../api/_collectorAuditHandler.js'


const vercelConfig = JSON.parse(
  readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'),
)
const auditRewrite = (vercelConfig.rewrites || []).find(x => x.source === '/api/collector-audit')
assert.equal(auditRewrite?.destination, '/api/public-snapshot?route=collector-audit')
assert.equal(vercelConfig.git.deploymentEnabled['fix/c05-durable-failure-audit-20261031'], false)

const token = 'audit-only-collector-permission-secret-00001'
const cycle = 'prod:2026-10-31:morning:twice-daily-v1'
const now = new Date('2026-10-31T00:30:00Z')
const input = {
  cycle_id: cycle,
  stage_id: 'ccgp',
  event_kind: 'CRON_QUEUE_FAILED',
  error_code: 'COLLECTOR_QUEUE_START_FAILED',
  occurred_at: '2026-10-31T00:20:00.000Z',
}
const result = validateCollectorFailureEvent(input, now)
assert.equal(result.event_id.length, 64)
assert.equal(result.cycle_id, cycle)
assert.equal(validateCollectorFailureEvent(input, now).event_id, result.event_id)
assert.equal(COLLECTOR_AUDIT_DDL.length, 3)
assert.ok(COLLECTOR_AUDIT_DDL[0].includes('CREATE TABLE IF NOT EXISTS public_collector_audit_events'))
assert.ok(COLLECTOR_AUDIT_DDL[0].includes('event_id TEXT PRIMARY KEY'))

const bad = (change, expected) => {
  assert.throws(
    () => validateCollectorFailureEvent({ ...input, ...change }, now),
    new RegExp(expected),
  )
}
bad({ error_code: 'HTTP 403 https://private.example?token=SECRET' }, 'ERROR_CODE_INVALID')
bad({ stage_id: 'test/../../secrets' }, 'STAGE_INVALID')
bad({ event_kind: 'SNAPSHOT_CONFIRMED' }, 'KIND_INVALID')
bad({ occurred_at: '2026-09-01T16:20:00Z' }, 'TIME_OUT_OF_RANGE')
bad({ occurred_at: '2026-10-31T00:55:00Z' }, 'TIME_OUT_OF_RANGE')
bad({ cycle_id: 'prod:2026-10-29:morning:twice-daily-v1' }, 'CYCLE_DATE_MISMATCH')
assert.throws(
  () => validateCollectorFailureEvent({ ...input, customer_name: 'Hospital Relationship' }, now),
  /FIELDS_INVALID/,
)

const incorrect = { headers: { authorization: 'Bearer badtoken' } }
const authorized = { headers: { authorization: 'Bearer ' + token } }
assert.equal(authenticatedCollectorAuditRequest(incorrect, { COLLECTOR_AUDIT_TOKEN: token }), false)
assert.equal(authenticatedCollectorAuditRequest(authorized, { COLLECTOR_AUDIT_TOKEN: token }), true)

function response() {
  const headers = {}
  return {
    headers,
    code: null,
    payload: null,
    setHeader(k, v) { headers[k] = v },
    status(code) { this.code = code; return this },
    json(payload) { this.payload = payload; return this },
  }
}
const env = { COLLECTOR_AUDIT_TOKEN: token, COLLECTOR_AUDIT_ENABLED: 'true' }
const oldDb = process.env.DATABASE_URL
process.env.DATABASE_URL = 'postgres://user:password@unreachable.invalid/test'

try {
  const first = response()
  let stored = false
  await collectorAuditHandler(
    { method: 'POST', body: input, headers: { authorization: 'Bearer ' + token } },
    first,
    { env: { ...env, COLLECTOR_AUDIT_ENABLED: 'false' }, store: async () => { stored = true } },
  )
  assert.equal(first.code, 503)
  assert.equal(stored, false)

  const denied = response()
  await collectorAuditHandler(
    { method: 'POST', body: input, headers: incorrect.headers }, denied,
    { env, store: async () => { stored = true } },
  )
  assert.equal(denied.code, 401)
  assert.equal(stored, false)

  const ok = response()
  await collectorAuditHandler(
    { method: 'POST', body: input, headers: authorized.headers }, ok,
    { env, store: async () => ({ event_id: result.event_id }) },
  )
  assert.equal(ok.code, 200)
  assert.equal(ok.payload.event_id, result.event_id)
  assert.equal(ok.headers['Cache-Control'], 'no-store, max-age=0')

  const invalidBody = response()
  await collectorAuditHandler(
    { method: 'POST', body: { ...input, api_key: 'SECRETS' }, headers: authorized.headers },
    invalidBody,
    {
      env,
      store: async x => {
        validateCollectorFailureEvent(x, now)
        return { event_id: result.event_id }
      },
    },
  )
  assert.equal(invalidBody.code, 400)
  assert.equal(JSON.stringify(invalidBody.payload).includes('SECRETS'), false)

  const readDenied = response()
  await collectorAuditHandler(
    { method: 'GET', url: '/api/collector-audit?days=7', headers: incorrect.headers },
    readDenied, { env, list: async () => [] },
  )
  assert.equal(readDenied.code, 401)

  const auditRead = response()
  await collectorAuditHandler(
    { method: 'GET', url: '/api/collector-audit?days=7&limit=100', headers: authorized.headers },
    auditRead,
    { env, list: async options => {
      assert.equal(options.days, 7)
      assert.equal(options.limit, 100)
      return [{ event_id: result.event_id }]
    } },
  )
  assert.equal(auditRead.code, 200)
  assert.equal(auditRead.payload.events.length, 1)

  // Simulate parameterized SQL, not a real network database. Exact same input
  // may be written twice with only one identity; validation must read back
  // durable contents, not treat ON CONFLICT as sufficient.
  const storedEvents = new Map()
  const sql = async (strings, ...params) => {
    const query = strings.join('?')
    if (query.includes('INSERT INTO public_collector_audit_events')) {
      const [id, cycle_id, stage_id, event_kind, error_code, occurred_at] = params
      if (!storedEvents.has(id)) storedEvents.set(id, {
        event_id: id, cycle_id, stage_id, event_kind, error_code, occurred_at,
      })
      return []
    }
    if (query.includes('FROM public_collector_audit_events WHERE event_id')) {
      return storedEvents.has(params[0]) ? [storedEvents.get(params[0])] : []
    }
    return []
  }
  sql.unsafe = async query => {
    assert.match(query, /^(CREATE TABLE|CREATE INDEX)/)
    return []
  }
  const persisted = await persistCollectorFailureEvent(input, { sql, now })
  assert.equal(persisted.accepted, true)
  await persistCollectorFailureEvent(input, { sql, now })
  assert.equal(storedEvents.size, 1)

  const readbackErrorSql = Object.assign(async () => [], { unsafe: async () => [] })
  await assert.rejects(
    persistCollectorFailureEvent(input, { sql: readbackErrorSql, now }),
    /DURABLE_READBACK_FAILED/,
  )
  await assert.rejects(
    listCollectorFailureAudit({ sql: readbackErrorSql, days: 0 }),
    /QUERY_INVALID/,
  )
} finally {
  if (oldDb === undefined) delete process.env.DATABASE_URL
  else process.env.DATABASE_URL = oldDb
}

const py = readFileSync(new URL('../collector_durable_audit.py', import.meta.url), 'utf8')
assert.match(py, /COLLECTOR_AUDIT_ENABLED/)
assert.match(py, /timeout=2\.0/)
assert.doesNotMatch(py, /VERIFIED_SNAPSHOT_PUBLISH_TOKEN/)
console.log('C05 collector failure audit: validation, disabled endpoint, auth, immutable SQL and readback PASS')
