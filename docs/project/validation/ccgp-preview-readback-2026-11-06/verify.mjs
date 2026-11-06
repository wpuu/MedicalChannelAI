import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import assert from 'node:assert/strict'

const bytes = name => readFileSync(new URL(name, import.meta.url))
const read = name => JSON.parse(bytes(name))
const sha = value => createHash('sha256').update(value).digest('hex')
const canonical = value => Array.isArray(value) ? value.map(canonical)
  : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value
const hash = value => sha(JSON.stringify(canonical(value)))
for (const item of read('manifest.json').files) {
  assert.equal(bytes(item.path).length, item.bytes, item.path)
  assert.equal(sha(bytes(item.path)), item.sha256, item.path)
}
const deployment = read('deployment.json')
assert.equal(deployment.state, 'READY')
assert.equal(deployment.target, 'preview')
assert.equal(deployment.source_sha, '82cc43f06c774969eab0fe44f0afc012f37cadac')
assert.equal(deployment.application_code_sha, '795ef5efa30b61dd47352c4fb888b02488f16855')
assert.equal(deployment.epoch, 'mcai-p0-20261106-d')
assert.equal(deployment.database, 'mcai_p0_epoch_20261106d')
assert.equal(deployment.new_environment_created, false)
assert.equal(deployment.env_changed, false)
assert.equal(deployment.schedule_changed, false)
const baseline = read('baseline-sql.json')[0]
const final = read('final-sql.json')[0]
const digest = hash(baseline.payload)
assert.equal(digest, baseline.snapshot_hash)
assert.equal(digest, final.snapshot_hash)
assert.equal(digest, hash(read('fresh.json').response))
assert.equal(digest, hash(read('ordinary.json').response))
assert.equal(digest, read('browser-report.json').sha256)
assert.equal(baseline.sql_as_of, final.sql_as_of)
assert.equal(final.precise, true)
assert.equal(baseline.opportunity_count, 16)
const status = read('status.json')
assert.equal(status.http, 200)
assert.equal(status.response.commit, '82cc43f')
assert.equal(status.response.preview_epoch, deployment.epoch)
assert.equal(status.response.snapshot.source_mode, 'DATABASE')
const collector = read('collector.json').response.collector
assert.equal(collector.active_cycle_id, null)
assert.equal(collector.completed_stage_count, 0)
assert.equal(collector.incremental.active_scan_id, null)
assert.equal(collector.incremental.chain, null)
const browser = read('browser-report.json')
assert.equal(browser.pass, true)
assert.equal(browser.checks.length, 6)
assert.equal(browser.baseline_full_payload_equal, true)
assert.deepEqual(browser.visibleCount, ['15', '15'])
assert.equal(browser.marketSelection, 'ALL')
assert.deepEqual(browser.pageErrors, [])
assert.deepEqual(browser.unexpectedRequests, [])
const pool = read('pool-reconciliation.json')
const closed = pool.closed_records[0]
assert.equal(pool.closed_records.length, 1)
assert.equal(closed.id, 'tjzyefy_20261104_030202660')
assert.equal(closed.bid_deadline, null)
assert(Date.parse(closed.registration_deadline) < Date.parse(pool.as_of))
const body = bytes('pool-body.txt').toString('utf8')
for (const card of baseline.payload.opportunity_pool) {
  assert.equal(body.includes(card.facts.project_name), card.opportunity_id !== closed.id)
}
assert.equal(read('access-cleanup.json').task_owned_share_revoked, true)
assert.equal(read('access-cleanup.json').private_access_file_removed, true)
assert.equal(read('production-boundary.json').commit, '3216fd940dabfa7714383b6436908f9b72ff8a9c')
assert.equal(read('completion.json').within_foreground_deadline, true)
console.log('PASS: Preview version/scope, unchanged SQL/API/browser payload,15active after real registration expiry,access cleanup and Production boundary')
