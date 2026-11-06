import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import assert from 'node:assert/strict'

const read = (name) => readFileSync(new URL(name, import.meta.url))
const json = (name) => JSON.parse(read(name))
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex')
const canonical = (value) => Array.isArray(value) ? value.map(canonical)
  : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
    : value
const hash = (value) => sha(JSON.stringify(canonical(value)))

const manifest = json('manifest.json')
for (const file of manifest.files) {
  const bytes = read(file.path)
  assert.equal(bytes.length, file.bytes, file.path)
  assert.equal(sha(bytes), file.sha256, file.path)
}
assert.equal(sha(read('../../../../' + manifest.official_fixture.path)), manifest.official_fixture.sha256)
const base = json('base-snapshot-row.json').payload
const payload = json('repair-payload.json')
const database = json('database-readback.json')
const browser = json('browser-report.json')
const targetId = 'ccgp_5184fb1beae01ab6'
const baseById = new Map(base.opportunity_pool.map(card => [card.opportunity_id, card]))
const repairedById = new Map(payload.opportunity_pool.map(card => [card.opportunity_id, card]))
assert.equal(repairedById.size, 16)
assert.deepEqual([...repairedById.keys()].sort(), [...baseById.keys()].sort())
for (const card of payload.opportunity_pool) {
  if (card.opportunity_id !== targetId) assert.deepEqual(card.facts, baseById.get(card.opportunity_id).facts)
}
for (const card of payload.cards) assert.deepEqual(card, repairedById.get(card.opportunity_id))
assert.deepEqual(payload.source_health, base.source_health)
assert.deepEqual(repairedById.get(targetId).facts.product_items, json('after.json').facts.product_items)
assert.equal(repairedById.get(targetId).facts.product_items.length, 10)
assert.equal(hash(payload), database.snapshot_hash)
assert.equal(hash(payload), json('authority-readback.json').full_payload_sha256)
assert.equal(hash(payload), browser.sha256)
assert.equal(database.precise, true)
assert.equal(browser.pass, true)
assert.equal(browser.checks.length, 6)
assert.equal(json('repair-publish.json').response.durable_committed, true)
assert.equal(json('access-cleanup.json').task_owned_share_revoked, true)
assert.equal(json('access-cleanup.json').private_credential_file_removed, true)
assert.equal(json('production-boundary.json').deployment[0].sha, '3216fd940dabfa7714383b6436908f9b72ff8a9c')
console.log('PASS: manifest, official bytes, exact products, 15 unchanged facts, source clocks, serving hashes, SQL precision, browser and boundaries')
