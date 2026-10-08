// MCAI-PERF-001: warm-instance snapshot memo + authenticated AI prewarm route.
import { readFileSync } from 'node:fs'
import {
  clearVerifiedSnapshotCacheForTests,
  loadVerifiedSnapshot,
  setDurableSnapshotSourceForTests,
  verifiedSnapshotSourceMode,
} from '../api/_verifiedSnapshot.js'
import { marketCodeForSnapshotCard, normalizePageBriefMarkets } from '../api/ai/_analyzeCore.js'
import handler from '../api/ai/analyze.js'

const raw = JSON.parse(
  readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'),
)

const saved = {
  remote: process.env.VERIFIED_SNAPSHOT_URL,
  publicRemote: process.env.VITE_VERIFIED_SNAPSHOT_URL,
  prewarm: process.env.AI_PREWARM_TOKEN,
  publish: process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN,
  db: process.env.DATABASE_URL,
  pg: process.env.POSTGRES_URL,
  now: Date.now,
}
process.env.VERIFIED_SNAPSHOT_URL = ''
process.env.VITE_VERIFIED_SNAPSHOT_URL = ''

function restoreEnv(name, value) {
  if (value === undefined) delete process.env[name]
  else process.env[name] = value
}

function mockResponse() {
  return {
    headers: {},
    statusCode: null,
    body: null,
    setHeader(name, value) { this.headers[String(name).toLowerCase()] = value },
    status(code) { this.statusCode = code; return this },
    json(payload) { this.body = payload; return this },
  }
}

async function invoke({ method = 'POST', authorization, body = {} } = {}) {
  const response = mockResponse()
  const headers = { host: 'trial.example' }
  if (authorization) headers.authorization = authorization
  await handler({ method, headers, body, query: { route: 'prewarm' } }, response)
  return response
}

try {
  // ---- Snapshot memo -------------------------------------------------------
  const calls = []
  let revision = { snapshot_hash: 'a'.repeat(64), payload: structuredClone(raw) }
  setDurableSnapshotSourceForTests(async (knownHash) => {
    calls.push(knownHash)
    if (knownHash === revision.snapshot_hash) return { snapshot_hash: revision.snapshot_hash, payload: null }
    return structuredClone(revision)
  })

  let fakeNow = saved.now()
  Date.now = () => fakeNow

  const first = await loadVerifiedSnapshot()
  if (verifiedSnapshotSourceMode() !== 'DATABASE') throw new Error(`MEMO_FIRST_SOURCE:${verifiedSnapshotSourceMode()}`)
  if (calls.length !== 1 || calls[0] !== null) throw new Error(`MEMO_FIRST_CALL:${JSON.stringify(calls)}`)

  // Within the recheck window: no database round trip at all.
  const second = await loadVerifiedSnapshot()
  if (calls.length !== 1) throw new Error(`MEMO_WITHIN_WINDOW_HIT_DB:${calls.length}`)

  // Every caller gets a private copy; mutation cannot leak across requests.
  if (first === second || first.cards === second.cards) throw new Error('MEMO_SHARED_REFERENCE')
  const expectedCards = second.cards.length
  first.cards.length = 0
  first.snapshot_as_of = 'mutated'
  const third = await loadVerifiedSnapshot()
  if (third.cards.length !== expectedCards || third.snapshot_as_of === 'mutated') {
    throw new Error('MEMO_MUTATION_LEAKED')
  }

  // After the window: cheap revision probe with the known hash, payload skipped.
  fakeNow += 20_000
  await loadVerifiedSnapshot()
  if (calls.length !== 2 || calls[1] !== 'a'.repeat(64)) throw new Error(`MEMO_REVISION_PROBE:${JSON.stringify(calls)}`)
  if (verifiedSnapshotSourceMode() !== 'DATABASE') throw new Error('MEMO_PROBE_SOURCE')

  // New revision: payload fetched and memo replaced.
  const newer = structuredClone(raw)
  revision = { snapshot_hash: 'b'.repeat(64), payload: newer }
  fakeNow += 20_000
  await loadVerifiedSnapshot()
  if (calls.length !== 3 || calls[2] !== 'a'.repeat(64)) throw new Error('MEMO_NEW_REVISION_PROBE')
  fakeNow += 20_000
  await loadVerifiedSnapshot()
  if (calls[3] !== 'b'.repeat(64)) throw new Error(`MEMO_NEW_REVISION_NOT_ADOPTED:${calls[3]}`)

  // Concurrent cold requests share one database read.
  clearVerifiedSnapshotCacheForTests()
  calls.length = 0
  await Promise.all([loadVerifiedSnapshot(), loadVerifiedSnapshot(), loadVerifiedSnapshot()])
  if (calls.length !== 1) throw new Error(`MEMO_COLD_STAMPEDE:${calls.length}`)

  // Database unavailable: fall back exactly as before (never DATABASE mode).
  setDurableSnapshotSourceForTests(async () => null)
  const fallback = await loadVerifiedSnapshot()
  if (!Array.isArray(fallback.cards)) throw new Error('MEMO_FALLBACK_INVALID')
  if (verifiedSnapshotSourceMode() === 'DATABASE') throw new Error('MEMO_FALLBACK_REPORTED_DATABASE')

  // Invalid durable payload is rejected (validation still runs on new revisions).
  setDurableSnapshotSourceForTests(async () => ({ snapshot_hash: 'c'.repeat(64), payload: { bogus: true } }))
  await loadVerifiedSnapshot()
  if (verifiedSnapshotSourceMode() === 'DATABASE') throw new Error('MEMO_INVALID_PAYLOAD_ACCEPTED')

  Date.now = saved.now
  setDurableSnapshotSourceForTests(null)
  clearVerifiedSnapshotCacheForTests()

  // ---- Page-brief market scoping (prewarm target) ------------------------
  if (marketCodeForSnapshotCard({ opportunity_id: 'ccgp_hl_x', facts: {} }) !== 'HL') throw new Error('BRIEF_MARKET_PREFIX')
  if (marketCodeForSnapshotCard({ opportunity_id: 'tjzyefy_intent_1', facts: {} }) !== 'TJ') throw new Error('BRIEF_MARKET_LEGACY_TJ')
  if (marketCodeForSnapshotCard({ opportunity_id: 'ccgp_hl_x', facts: { market_code: 'bj' } }) !== 'BJ') throw new Error('BRIEF_MARKET_EXPLICIT')
  if (JSON.stringify(normalizePageBriefMarkets(['tj', 'BJ'])) !== JSON.stringify(['BJ', 'TJ'])) throw new Error('BRIEF_MARKETS_NORMALIZE')
  if (normalizePageBriefMarkets(['TJ', 'XX']) !== null) throw new Error('BRIEF_MARKETS_UNKNOWN_ACCEPTED')
  if (normalizePageBriefMarkets([]) !== null || normalizePageBriefMarkets('TJ') !== null) throw new Error('BRIEF_MARKETS_SHAPE')

  // ---- Prewarm route auth boundary ----------------------------------------
  delete process.env.AI_PREWARM_TOKEN
  delete process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN
  let response = await invoke({ authorization: 'Bearer anything' })
  if (response.statusCode !== 503 || response.body?.error !== 'PREWARM_NOT_CONFIGURED') {
    throw new Error(`PREWARM_UNCONFIGURED:${response.statusCode}:${response.body?.error}`)
  }

  process.env.AI_PREWARM_TOKEN = 'prewarm-secret-token-value'
  response = await invoke({ method: 'GET', authorization: 'Bearer prewarm-secret-token-value' })
  if (response.statusCode !== 405) throw new Error(`PREWARM_GET:${response.statusCode}`)

  for (const authorization of [undefined, 'Bearer wrong', 'Bearer prewarm-secret-token-valuX', 'prewarm-secret-token-value']) {
    response = await invoke({ authorization })
    if (response.statusCode !== 401) throw new Error(`PREWARM_AUTH_BYPASS:${authorization}:${response.statusCode}`)
  }

  // Publisher secret fallback is accepted when no dedicated token exists.
  delete process.env.AI_PREWARM_TOKEN
  process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = 'publisher-secret-token'
  process.env.DATABASE_URL = ''
  process.env.POSTGRES_URL = ''
  response = await invoke({ authorization: 'Bearer publisher-secret-token' })
  // Authorized: without a durable cache (or with a stale test snapshot) prewarm
  // must refuse with 409 rather than generate non-durable results.
  if (response.statusCode !== 409) throw new Error(`PREWARM_AUTHORIZED_NO_DB:${response.statusCode}:${response.body?.error}`)
  if (!['PREWARM_REQUIRES_DURABLE_CACHE', 'VERIFIED_SNAPSHOT_NOT_FRESH', 'VERIFIED_SNAPSHOT_UNAVAILABLE'].includes(response.body?.error)) {
    throw new Error(`PREWARM_AUTHORIZED_NO_DB_CODE:${response.body?.error}`)
  }
  if (JSON.stringify(response.body).includes('publisher-secret-token')) throw new Error('PREWARM_TOKEN_LEAK')

  // Internal prewarm must bypass the per-IP visitor budget, and only prewarm.
  const core = readFileSync(new URL('../api/ai/_analyzeCore.js', import.meta.url), 'utf8')
  if (!core.includes('if (!request?.__mcaiInternalPrewarm && await warmRateLimitExceeded(request))')) {
    throw new Error('PREWARM_RATE_LIMIT_BYPASS_MISSING')
  }
  const analyze = readFileSync(new URL('../api/ai/analyze.js', import.meta.url), 'utf8')
  if ((analyze.match(/__mcaiInternalPrewarm/g) || []).length !== 0) {
    throw new Error('PREWARM_FLAG_MUST_ONLY_BE_SET_IN_CORE')
  }

  console.log('Snapshot memo + AI prewarm boundary: PASS')
} finally {
  Date.now = saved.now
  setDurableSnapshotSourceForTests(null)
  clearVerifiedSnapshotCacheForTests()
  restoreEnv('VERIFIED_SNAPSHOT_URL', saved.remote)
  restoreEnv('VITE_VERIFIED_SNAPSHOT_URL', saved.publicRemote)
  restoreEnv('AI_PREWARM_TOKEN', saved.prewarm)
  restoreEnv('VERIFIED_SNAPSHOT_PUBLISH_TOKEN', saved.publish)
  restoreEnv('DATABASE_URL', saved.db)
  restoreEnv('POSTGRES_URL', saved.pg)
}
