import { validateCollectorAuditEvent } from '../api/_collectorAudit.js'
import snapshotHandler from '../api/public-snapshot.js'

function expect(value, code) {
  if (!value) throw new Error(code)
}
function response() {
  return {
    statusCode: null, body: null, headers: {},
    setHeader(k, v) { this.headers[k.toLowerCase()] = v },
    status(v) { this.statusCode = v; return this },
    json(v) { this.body = v; return this },
  }
}
const valid = {
  schema_version: '0.1', cycle_id: 'prod:2026-11-27',
  cycle_as_of: '2026-11-27T00:27:29.158Z',
  stage: 'ccgp', status: 'FAILED', outcome: 'SOURCE_UNAVAILABLE',
  error_code: 'SOURCE_UNAVAILABLE', attempt_count: 1,
  new_verified_record_count: 0,
}
const good = validateCollectorAuditEvent(valid)
expect(good.id === 'prod:2026-11-27:ccgp', 'AUDIT_STABLE_STAGE_ID')
expect(good.new_verified_record_count === 0, 'AUDIT_ZERO_IS_FACT')
for (const invalid of [
  { ...valid, stage: 'invalid' }, { ...valid, status: 'SKIPPED' },
  { ...valid, cycle_id: 'prod:bad' }, { ...valid, outcome: 'https://secret.example/token' },
  { ...valid, error_code: 'bad token' }, { ...valid, new_verified_record_count: -1 },
  { ...valid, extra: 'x'.repeat(1600) },
]) {
  let rejected = false
  try { validateCollectorAuditEvent(invalid) } catch { rejected = true }
  expect(rejected, 'AUDIT_INVALID_PAYLOAD_ACCEPTED')
}
const oldEnv = process.env.VERCEL_ENV
const oldToken = process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN
try {
  process.env.VERCEL_ENV = 'preview'
  process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = 'synthetic-audit-test-token-123456'
  let res = response()
  await snapshotHandler({ method: 'PATCH', body: valid,
    headers: { authorization: 'Bearer synthetic-audit-test-token-123456' } }, res)
  expect(res.statusCode === 403, 'AUDIT_PREVIEW_REJECTED')
  process.env.VERCEL_ENV = 'production'
  res = response()
  await snapshotHandler({ method: 'PATCH', body: valid,
    headers: { authorization: 'Bearer invalid' } }, res)
  expect(res.statusCode === 401, 'AUDIT_INVALID_BEARER_REJECTED')
  res = response()
  await snapshotHandler({ method: 'PATCH', body: valid, headers: {} }, res)
  expect(res.statusCode === 401, 'AUDIT_MISSING_BEARER_REJECTED')
} finally {
  if (oldEnv === undefined) delete process.env.VERCEL_ENV
  else process.env.VERCEL_ENV = oldEnv
  if (oldToken === undefined) delete process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN
  else process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = oldToken
}
console.log('Collector audit contracts: PASS')
