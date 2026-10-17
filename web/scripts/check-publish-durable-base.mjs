import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

// Keep the actual persistence transaction and its ordering; replace only its
// database transport so concurrent-publication cases never reach a real DB.
const directory = await mkdtemp(join(tmpdir(), 'medical-durable-base-'))
const registryName = '__medicalDurableBaseTest'
const previousRegistry = globalThis[registryName]
const previousFetch = globalThis.fetch
const state = { latest: null, insertAttempts: 0, locked: false, readError: null, inTransaction: false }
const sql = async (strings, ...parameters) => {
  const query = strings.join('?').replace(/\s+/g, ' ').trim()
  if (query.includes("to_regclass('public_schema_meta')")) return [{ table_name: 'public_schema_meta' }]
  if (query.includes('FROM public_schema_meta')) return [{ schema_version: '2026-09-27-public-intelligence-v2' }]
  if (query.includes('pg_advisory_xact_lock')) {
    if (query.includes('public-verified-snapshot-publish')) state.locked = true
    return []
  }
  if (query.startsWith('SELECT') && query.includes('FROM public_verified_snapshots')) {
    if (state.inTransaction) assert.equal(state.locked, true, 'Read the durable base after acquiring the publication lock')
    if (state.readError) throw state.readError
    if (query.includes('WHERE snapshot_as_of')) return []
    return state.latest ? [structuredClone(state.latest)] : []
  }
  if (query.startsWith('INSERT INTO public_verified_snapshots')) {
    assert.equal(state.locked, true, 'Insert must occur under the publication lock')
    state.insertAttempts += 1
    state.latest = { snapshot_hash: parameters[0], snapshot_as_of: parameters[1] }
    return [{ snapshot_hash: parameters[0] }]
  }
  throw new Error(`Unexpected SQL in offline check: ${query}`)
}
sql.json = (value) => value
sql.begin = async (callback) => {
  state.locked = false
  state.inTransaction = true
  const previous = structuredClone(state.latest)
  try { return await callback(sql) } catch (error) { state.latest = previous; throw error }
  finally { state.inTransaction = false }
}
sql.unsafe = async () => { throw new Error('Unexpected schema writes in offline check') }

try {
  globalThis.fetch = async () => { throw new Error('Real network requests forbidden in offline check') }
  globalThis[registryName] = { privateDatabaseConfigured: () => true, privateDb: () => sql }
  let source = await readFile(new URL('../api/_publicIntelligenceDb.js', import.meta.url), 'utf8')
  const importPattern = /import \{ privateDatabaseConfigured, privateDb \} from '\.\/_privateDb\.js'/
  assert.match(source, importPattern)
  source = source.replace(importPattern, `const { privateDatabaseConfigured, privateDb } = globalThis.${registryName}`)
  const modulePath = join(directory, 'durable.mjs')
  await writeFile(modulePath, source)
  const { persistPublicVerifiedSnapshot, latestPublicVerifiedSnapshotForPublish } = await import(pathToFileURL(modulePath).href)
  const base = { snapshot_hash: 'a'.repeat(64), snapshot_as_of: '2026-10-03T01:00:00Z' }
  const concurrent = { snapshot_hash: 'c'.repeat(64), snapshot_as_of: '2026-10-03T02:00:00Z' }
  const candidate = { snapshot_as_of: '2026-10-03T03:00:00Z', cards: [], collection_coverage: { complete: false } }

  // B used A during preflight, but C inserted before B acquired the DB lock.
  state.latest = concurrent
  await assert.rejects(persistPublicVerifiedSnapshot(candidate, {
    requireBaseMatch: true, expectedBaseHash: base.snapshot_hash, expectedBaseAsOf: base.snapshot_as_of,
  }), /PUBLIC_SNAPSHOT_BASE_CHANGED/)
  assert.equal(state.insertAttempts, 0)
  assert.deepEqual(state.latest, concurrent)

  // Two first publishers must not both treat the durable store as empty.
  await assert.rejects(persistPublicVerifiedSnapshot(candidate, {
    requireBaseMatch: true, expectedBaseHash: null, expectedBaseAsOf: null,
  }), /PUBLIC_SNAPSHOT_BASE_CHANGED/)
  assert.equal(state.insertAttempts, 0)

  state.latest = base
  const accepted = await persistPublicVerifiedSnapshot(candidate, {
    requireBaseMatch: true, expectedBaseHash: base.snapshot_hash, expectedBaseAsOf: base.snapshot_as_of,
  })
  assert.equal(accepted.persisted, true)
  assert.equal(state.insertAttempts, 1)

  state.latest = null
  state.insertAttempts = 0
  await persistPublicVerifiedSnapshot(candidate, {
    requireBaseMatch: true, expectedBaseHash: null, expectedBaseAsOf: null,
  })
  assert.equal(state.insertAttempts, 1)

  state.latest = concurrent
  state.insertAttempts = 0
  await persistPublicVerifiedSnapshot({ ...candidate, collection_coverage: { complete: true } }, { requireBaseMatch: false })
  assert.equal(state.insertAttempts, 1)

  state.readError = Object.assign(new Error('missing table'), { code: '42P01' })
  assert.equal(await latestPublicVerifiedSnapshotForPublish(), null)
  state.readError = Object.assign(new Error('database unavailable'), { code: '08006' })
  await assert.rejects(latestPublicVerifiedSnapshotForPublish(), /database unavailable/)
} finally {
  globalThis.fetch = previousFetch
  if (previousRegistry === undefined) delete globalThis[registryName]
  else globalThis[registryName] = previousRegistry
  await rm(directory, { recursive: true, force: true })
}
console.log('Durable publication base: PASS (transaction rejects stale partial base before insert; empty/matching/full and read errors covered)')
