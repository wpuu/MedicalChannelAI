import assert from 'node:assert/strict'
import { createPublicSnapshotHandler } from '../api/public-snapshot.js'
import { persistPublicVerifiedSnapshot } from '../api/_publicIntelligenceDb.js'
import {
  loadVerifiedSnapshot,
  publishVerifiedSnapshotToRuntimeCache,
  setDurableSnapshotSourceForTests,
} from '../api/_verifiedSnapshot.js'
import { installSnapshotTestClock, makeVerifiedSnapshot, SNAPSHOT_TEST_NOW_MS } from './fixtures/verifiedSnapshot.mjs'

// An in-memory adapter for the actual tagged-SQL transaction. It implements
// isolation, rollback and the publication advisory lock; no connection is made.
function micros(v) {
  const fraction = (String(v).match(/\.(\d+)(?:Z|[+-])/)?.[1] || '').padEnd(6, '0')
  return BigInt(Date.parse(v)) * 1000n + BigInt(fraction.slice(3))
}
function memoryDatabase() {
  let rows = []
  let queue = Promise.resolve()
  const state = { insertCount: 0, transactionCount: 0, fail: false, failReadback: false }
  state.latest = () => rows.toSorted((a, b) => Number(micros(b.payload?.snapshot_as_of || b.snapshot_as_of) - micros(a.payload?.snapshot_as_of || a.snapshot_as_of)))[0] || null
  state.truncateLatestTimestamp = () => { const row = state.latest(); row.snapshot_as_of = new Date(row.snapshot_as_of).toISOString() }
  state.sql = {
    async begin(callback) {
      const previous = queue
      let unlock
      queue = new Promise((resolve) => { unlock = resolve })
      await previous
      state.transactionCount++
      try {
        if (state.fail) throw new Error('MOCK_DATABASE_UNAVAILABLE')
        const staged = structuredClone(rows)
        let inserted = 0
        const tx = async (parts, ...values) => {
          const text = parts.join('?').replace(/\s+/g, ' ').trim()
          if (text.includes('pg_advisory_xact_lock')) {
            assert.match(text, /public-verified-snapshot-publication/)
            return []
          }
          if (text.startsWith('SELECT snapshot_hash, snapshot_as_of')) {
            return staged.toSorted((a, b) => Number(micros(b.payload?.snapshot_as_of || b.snapshot_as_of) - micros(a.payload?.snapshot_as_of || a.snapshot_as_of))).slice(0, 1).map(row => ({ ...row, revision_as_of: row.payload.snapshot_as_of }))
          }
          if (text.startsWith('SELECT snapshot_hash, payload')) {
            if (state.failReadback) return []
            return staged.filter((row) => row.snapshot_hash === values[1]).map(row => ({ ...row, timestamp_matches: micros(row.snapshot_as_of) === micros(values[0]) }))
          }
          if (text.startsWith('SELECT snapshot_hash')) {
            return staged.filter((row) => Date.parse(row.snapshot_as_of) === Date.parse(values[0]))
          }
          if (text.startsWith('INSERT INTO public_verified_snapshots')) {
            const [snapshot_hash, snapshot_as_of, payload] = values
            const existing = staged.find((row) => row.snapshot_hash === snapshot_hash)
            if (existing) {
              if (micros(existing.snapshot_as_of) === micros(snapshot_as_of)) return []
              existing.snapshot_as_of = snapshot_as_of
              return [{ snapshot_hash }]
            }
            assert(!staged.some((row) => micros(row.snapshot_as_of) === micros(snapshot_as_of)))
            staged.push({ snapshot_hash, snapshot_as_of, payload: structuredClone(payload) })
            inserted++
            return [{ snapshot_hash }]
          }
          throw new Error(`UNEXPECTED_MOCK_SQL:${text}`)
        }
        tx.json = (value) => value
        const result = await callback(tx)
        rows = staged
        state.insertCount += inserted
        return result
      } finally { unlock() }
    },
  }
  return state
}

function fixture() {
  const database = memoryDatabase()
  const values = new Map()
  const cache = {
    writes: 0,
    fail: false,
    async get(key) { return values.get(key) },
    async set(key, value) {
      if (this.fail) throw new Error('MOCK_CACHE_UNAVAILABLE')
      this.writes++
      values.set(key, structuredClone(value))
    },
  }
  const persist = (snapshot) => persistPublicVerifiedSnapshot(snapshot, { sql: database.sql, ensureSchema: async () => {} })
  setDurableSnapshotSourceForTests(async (knownHash) => {
    const latest = database.latest()
    return latest ? { snapshot_hash: latest.snapshot_hash, payload: knownHash === latest.snapshot_hash ? null : latest.payload } : null
  })
  const handler = createPublicSnapshotHandler({
    persistSnapshot: persist,
    publishRuntimeSnapshot: (snapshot) => publishVerifiedSnapshotToRuntimeCache(snapshot, { cache }),
    loadSnapshot: loadVerifiedSnapshot,
    databaseConfigured: () => true,
    remoteReaderConfigured: () => false,
  })
  return { database, cache, persist, handler }
}

async function invoke(handler, body, { method = 'PUT', fresh = false } = {}) {
  const response = {
    headers: {}, statusCode: null, body: null,
    setHeader(key, value) { this.headers[key] = value },
    status(code) { this.statusCode = code; return this },
    json(value) { this.body = value; return this },
  }
  await handler({ method, body, query: fresh ? { fresh: '1' } : {}, headers: { authorization: `Bearer ${'p'.repeat(32)}` } }, response)
  return response
}

const restoreClock = installSnapshotTestClock()
const saved = Object.fromEntries(['VERIFIED_SNAPSHOT_PUBLISH_TOKEN', 'VERIFIED_SNAPSHOT_URL', 'VITE_VERIFIED_SNAPSHOT_URL', 'VERCEL_REGION'].map((key) => [key, process.env[key]]))
process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = 'p'.repeat(32)
delete process.env.VERIFIED_SNAPSHOT_URL
delete process.env.VITE_VERIFIED_SNAPSHOT_URL
delete process.env.VERCEL_REGION
const savedWarn = console.warn
console.warn = () => {}
try {
  // Validation errors have no authoritative side effects, including the case
  // which previously committed a future or oversized row before returning 4xx.
  for (const [name, mutate, expectedStatus] of [
    ['schema', (s) => { s.schema_version = 'invalid' }, 400],
    ['facts', (s) => { s.opportunity_pool[0].facts.verification_status = 'UNVERIFIED' }, 400],
    ['oversize', (s) => { s.padding = 'x'.repeat(2 * 1024 * 1024) }, 400],
    ['future', (s) => { s.snapshot_as_of = new Date(SNAPSHOT_TEST_NOW_MS + 15 * 60 * 1000 + 1).toISOString() }, 409],
    ['before-bundle', (s) => { s.snapshot_as_of = new Date(SNAPSHOT_TEST_NOW_MS - 60 * 60 * 1000 - 1).toISOString() }, 409],
  ]) {
    const { database, cache, handler } = fixture()
    const snapshot = makeVerifiedSnapshot()
    mutate(snapshot)
    const response = await invoke(handler, snapshot)
    assert.equal(response.statusCode, expectedStatus, name)
    assert.equal(database.transactionCount, 0, `${name}: started transaction`)
    assert.equal(database.latest(), null, `${name}: polluted authoritative read`)
    assert.equal(cache.writes, 0, `${name}: wrote fallback cache`)
  }

  {
    const { database, persist, cache } = fixture()
    const base = makeVerifiedSnapshot()
    const precise = (fraction, offset = 'Z') => ({ ...structuredClone(base), snapshot_as_of: base.snapshot_as_of.replace(/\.\d+Z$/, `.${fraction}${offset}`) })
    const first = precise('123456')
    await persist(first)
    database.truncateLatestTimestamp()
    assert.equal((await persist(first)).inserted, false, 'legacy replay repairs column without a new revision')
    assert.equal(database.latest().snapshot_as_of, first.snapshot_as_of)
    const newer = precise('123789')
    await persist(newer)
    await assert.rejects(persist(precise('123500')), /PUBLIC_SNAPSHOT_ROLLBACK_REJECTED/)
    await assert.rejects(persist({ ...newer, coverage_warning: 'same instant changed' }), /PUBLIC_SNAPSHOT_REVISION_CONFLICT/)
    await assert.rejects(persist(precise('1237891')), /PUBLIC_SNAPSHOT_AS_OF_INVALID/)
    assert.equal(database.insertCount, 2)
    await publishVerifiedSnapshotToRuntimeCache(first, { cache })
    await publishVerifiedSnapshotToRuntimeCache(newer, { cache })
    await assert.rejects(publishVerifiedSnapshotToRuntimeCache(precise('123500'), { cache }), /RUNTIME_SNAPSHOT_ROLLBACK_REJECTED/)
    await assert.rejects(publishVerifiedSnapshotToRuntimeCache({ ...newer, coverage_warning: 'conflict' }, { cache }), /RUNTIME_SNAPSHOT_REVISION_CONFLICT/)
  }

  for (const field of ['fail', 'failReadback']) {
    const { database, cache, handler } = fixture()
    database[field] = true
    const response = await invoke(handler, makeVerifiedSnapshot())
    assert.equal(response.statusCode, 503, field)
    assert.equal(database.latest(), null, `${field}: transaction did not roll back`)
    assert.equal(cache.writes, 0, `${field}: cache published an uncommitted row`)
  }

  {
    const { database, cache, handler } = fixture()
    const snapshot = makeVerifiedSnapshot()
    cache.fail = true
    let response = await invoke(handler, snapshot)
    assert.equal(response.statusCode, 200)
    assert.equal(response.body.durable_committed, true)
    assert.equal(response.body.cache_status, 'RETRY_REQUIRED')
    assert.equal(database.insertCount, 1)
    response = await invoke(handler, undefined, { method: 'GET', fresh: true })
    assert.equal(response.statusCode, 200)
    assert.equal(response.body.snapshot_as_of, snapshot.snapshot_as_of)
    cache.fail = false
    response = await invoke(handler, snapshot)
    assert.equal(response.body.cache_status, 'UPDATED')
    assert.equal(database.insertCount, 1, 'cache retry committed a second revision')
    assert.equal(cache.writes, 1)

    const conflicting = structuredClone(snapshot)
    conflicting.coverage_warning = 'different payload at the same revision'
    response = await invoke(handler, conflicting)
    assert.equal(response.statusCode, 409)
    assert.equal(response.body.error, 'PUBLIC_SNAPSHOT_REVISION_CONFLICT')
    assert.equal(database.insertCount, 1)
  }

  {
    const { database, handler, persist } = fixture()
    const older = makeVerifiedSnapshot({ asOfMs: SNAPSHOT_TEST_NOW_MS - 1000 })
    const newer = makeVerifiedSnapshot()
    const [first, second] = await Promise.all([invoke(handler, newer), invoke(handler, older)])
    assert.equal(first.statusCode, 200)
    assert.equal(second.statusCode, 409)
    assert.equal(second.body.error, 'PUBLIC_SNAPSHOT_ROLLBACK_REJECTED')
    assert.equal(database.latest().snapshot_as_of, newer.snapshot_as_of)
    assert.equal(database.insertCount, 1)

    // Simulate another warm instance committing after this reader memoized the
    // previous revision: ?fresh must bypass the 15-second in-process memo too.
    await invoke(handler, undefined, { method: 'GET', fresh: true })
    const next = makeVerifiedSnapshot({ asOfMs: SNAPSHOT_TEST_NOW_MS + 1000 })
    await persist(next)
    const readback = await invoke(handler, undefined, { method: 'GET', fresh: true })
    assert.equal(readback.body.snapshot_as_of, next.snapshot_as_of)
  }

  {
    const { database, handler } = fixture()
    const snapshot = makeVerifiedSnapshot()
    const responses = await Promise.all([invoke(handler, snapshot), invoke(handler, snapshot)])
    assert(responses.every((response) => response.statusCode === 200))
    assert.equal(database.insertCount, 1, 'concurrent exact retries inserted twice')
  }

  for (const options of [{ databaseConfigured: () => false }, { remoteReaderConfigured: () => true }]) {
    let writes = 0
    const handler = createPublicSnapshotHandler({
      databaseConfigured: () => true,
      remoteReaderConfigured: () => false,
      persistSnapshot: async () => { writes++; return { persisted: true } },
      ...options,
    })
    const response = await invoke(handler, makeVerifiedSnapshot())
    assert([409, 503].includes(response.statusCode))
    assert.equal(writes, 0)
  }
  console.log('P0 snapshot publication: PASS (validation, atomic commit/readback, rollback, concurrency, cache retry, fresh GET)')
} finally {
  restoreClock()
  setDurableSnapshotSourceForTests(null)
  console.warn = savedWarn
  for (const [key, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
}
