// Real TypeScript services run through a transpile hook. Only HTTP, clock and
// browser storage are synthetic; cache, mapping, market wrapper and guards are real.
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { registerHooks } from 'node:module'
import ts from 'typescript'

const web = fileURLToPath(new URL('..', import.meta.url))
const hooks = registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('@/') || (specifier.startsWith('.') && context.parentURL?.startsWith(pathToFileURL(web).href))) {
      const base = specifier.startsWith('@/') ? resolve(web, 'src', specifier.slice(2))
        : resolve(dirname(fileURLToPath(context.parentURL)), specifier)
      const file = [base, base + '.ts', base + '.js', resolve(base, 'index.ts')].find(p => existsSync(p) && /\.[cm]?[jt]s$/.test(p))
      if (file) return { url: pathToFileURL(file).href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.startsWith(pathToFileURL(resolve(web, 'src')).href) && url.endsWith('.ts')) {
      return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
      }).outputText }
    }
    return next(url, context)
  },
})
const oldFetch = globalThis.fetch, oldNow = Date.now
const oldStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
let now = Date.parse('2026-10-05T00:00:00Z')
Date.now = () => now
const memory = new Map()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k),
}})
const base = JSON.parse(readFileSync(new URL('./fixtures/pr77-legacy-award-snapshot.json', import.meta.url), 'utf8'))
let server
const failures = [], checks = []
async function check(name, fn) {
  try { await fn(); checks.push(name); console.log(name + ': PASS') }
  catch (e) { failures.push(name); console.error(name + ': FAIL: ' + e.message) }
}
function payload(cards) {
  return { ...structuredClone(base), cards: structuredClone(cards), opportunity_pool: structuredClone(cards),
    card_count: cards.length, opportunity_pool_count: cards.length, award_ledger: [], awarded_project_count: 0 }
}
function synthetic(id, registration, bid, published, score = 57) {
  const c = structuredClone(base.cards[0]);c.opportunity_id = id
  Object.assign(c.facts, { project_number: id, project_name: id, hospital_name: '合成医院', buyer_name: '合成医院',
    market_code: 'TJ', market_name: '天津', public_contact: null, published_at: published,
    registration_deadline: registration, registration_deadline_date: null, bid_deadline: bid })
  c.evidence_source_urls = ['https://official.invalid/synthetic/temporal/' + id]
  c.legal_windows = []; c.official_notices = [];c.decision = null;c.priority.score = score
  c.priority.components.find(x => x.code === 'DEADLINE_URGENCY').points = 10
  c.priority.components.find(x => x.code === 'PUBLICATION_FRESHNESS').points = 7
  return c
}
globalThis.fetch = async url => {
  assert.equal(String(url), '/api/public-snapshot')
  return { ok: true, status: 200, json: async () => structuredClone(server) }
}
try {
  const client = await import('../src/services/verifiedSnapshotClient.ts')
  const { StaticSnapshotTodayActionsService } = await import('../src/services/StaticSnapshotTodayActionsService.ts')
  const { RuntimeTrialTodayActionsService, refreshTrialTemporalPriority } = await import('../src/services/RuntimeTrialTodayActionsService.ts')
  const verified = await import('../src/services/verifiedOpportunityPool.ts')
  const store = await import('../src/services/localFollowupStore.ts')
  const profile = await import('../src/services/localCustomerProfile.ts')
  async function load(cards) {
    memory.clear(); client.resetVerifiedSnapshotClient();server = payload(cards)
    return new RuntimeTrialTodayActionsService(new StaticSnapshotTodayActionsService('/api/public-snapshot'))
  }
  async function compare(service, id, urgency, freshness) {
    const today = (await service.getTodayActions()).opportunity_pool.find(c => c.opportunity_id === id)
    const detail = await service.getOpportunity(id)
    const pool = (await verified.getVerifiedOpportunityPool()).cards.find(c => c.opportunity_id === id)
    assert(today && detail && pool)
    console.log(JSON.stringify({ id, now: new Date(now).toISOString(), today: today.priority, detail: detail.priority, pool: pool.priority }))
    assert.deepEqual(detail.priority, today.priority); assert.deepEqual(pool.priority, today.priority)
    if (urgency !== undefined) assert.equal(pool.priority.components.DEADLINE_URGENCY, urgency)
    if (freshness !== undefined) assert.equal(pool.priority.components.PUBLICATION_FRESHNESS, freshness)
    return { today, detail, pool }
  }
  await check('existing Sep29 fixture has one public score across today/detail/pool at Oct5', async () => {
    const c = base.cards[0], service = await load([c]);const actual = await compare(service, c.opportunity_id, 50, 43)
    assert.equal(actual.today.priority.score, 33);assert.equal(actual.pool.recommendation_mode, 'LATE_WINDOW')
  })
  const cases = [
    ['near', '2026-10-05T12:00:00Z', '2026-10-20T00:00:00Z', '2026-10-05', 100, 100],
    ['three-day', '2026-10-07T00:00:00Z', '2026-10-20T00:00:00Z', '2026-10-03', 90, 86],
    ['late-window', '2026-10-04T00:00:00Z', '2026-10-06T00:00:00Z', '2026-09-29', 100, 71],
    ['date-only', null, '2026-10-20T00:00:00Z', '2026-09-20', 100, 14],
    ['unknown', null, null, null, 0, 0],
    ['invalid', 'invalid', 'invalid', '2026-02-30', 0, 0],
    ['future-publication', '2026-10-20T00:00:00Z', '2026-10-30T00:00:00Z', '2026-10-06', 30, 0],
  ]
  for (const [id, registration, bid, published, urgency, freshness] of cases) {
    await check(id + ' temporal components and scores agree across three paths', async () => {
      const c = synthetic(id, registration, bid, published)
      if (id === 'date-only') c.facts.registration_deadline_date = '2026-10-05'
      await compare(await load([c]), id, urgency, freshness)
    })
  }
  await check('pool order follows refreshed score and same deadline tie-break as today', async () => {
    const a = synthetic('near-low-old-score', '2026-10-05T12:00:00Z', '2026-10-20T00:00:00Z', '2026-10-05', 57)
    const b = synthetic('far-high-old-score', '2026-11-20T00:00:00Z', '2026-11-30T00:00:00Z', '2026-08-01', 58)
    const c = synthetic('tie-later', '2026-10-05T18:00:00Z', '2026-10-20T00:00:00Z', '2026-10-05', 57)
    a.rank = 3;b.rank = 1;c.rank = 2
    const service = await load([b,c,a]);const today = (await service.getTodayActions()).opportunity_pool
    const pool = (await verified.getVerifiedOpportunityPool()).cards
    assert.deepEqual(today.map(x=>x.opportunity_id), ['near-low-old-score','tie-later','far-high-old-score'])
    assert.deepEqual(pool.map(x=>[x.opportunity_id,x.priority.score,x.rank]), today.map(x=>[x.opportunity_id,x.priority.score,x.rank]))
  })
  await check('repeat reads and pure refresh are idempotent; clock advance derives from unmodified snapshot', async () => {
    const c=base.cards[0],service=await load([c]);const before=JSON.stringify(server)
    const once=await service.getOpportunity(c.opportunity_id)
    assert.deepEqual(refreshTrialTemporalPriority(refreshTrialTemporalPriority(once,now),now),once)
    for(let i=0;i<3;i++)await compare(service,c.opportunity_id)
    assert.equal(JSON.stringify(server),before)
    now += 86400000;await compare(service,c.opportunity_id);assert.equal(JSON.stringify(server),before)
    now -= 86400000
  })
  await check('personalized cards refresh time after existing private score calculation', async () => {
    const c=synthetic('personalized', '2026-10-07T00:00:00Z','2026-10-20T00:00:00Z','2026-09-20'),service=await load([c])
    const p=profile.loadLocalCustomerProfile();p.can_find_manufacturer=true;profile.saveLocalCustomerProfile(p)
    const result=await compare(service,c.opportunity_id);assert.equal(result.pool.priority.score_scope,'PERSONALIZED')
  })
  await check('expired cards are filtered and withdrawn saved history stays non-eligible', async () => {
    const c=synthetic('historical','2026-10-05T12:00:00Z','2026-10-20T00:00:00Z','2026-10-05'), service=await load([c])
    await service.updateFollowup(c.opportunity_id,{status:'REVIEWING',note:'合成历史记录'})
    const saved=structuredClone(store.readLocalFollowups()[c.opportunity_id])
    c.facts.bid_deadline='2026-10-04T00:00:00Z';server=payload([c]);now+=client.SNAPSHOT_CLIENT_TTL_MS+1
    assert.equal((await service.getTodayActions()).opportunity_pool.length,0)
    assert.equal((await verified.getVerifiedOpportunityPool()).total,0)
    assert.equal((await service.getOpportunity(c.opportunity_id)).model_decision_status,'NOT_ELIGIBLE')
    server=payload([]);now+=client.SNAPSHOT_CLIENT_TTL_MS+1;assert.equal(await service.getOpportunity(c.opportunity_id),null)
    const history=store.getStoredHistoricalOpportunityCard(c.opportunity_id)
    assert.equal(history.priority.score,0);assert.equal(history.match_status,'ARCHIVE');assert.equal(history.model_decision_status,'NOT_ELIGIBLE')
    assert.equal(history.decision,null);assert.deepEqual(store.readLocalFollowups()[c.opportunity_id],saved)
    await assert.rejects(()=>service.requestOutreachDraft(c.opportunity_id),/OUTREACH_GROUNDING_INSUFFICIENT/)
    now=Date.parse('2026-10-05T00:00:00Z')
  })
} finally {
  globalThis.fetch = oldFetch; Date.now = oldNow; hooks.deregister()
  if (oldStorage) Object.defineProperty(globalThis, 'localStorage', oldStorage)
  else delete globalThis.localStorage
}
console.log(`Trial temporal consistency: ${checks.length + failures.length} checks, ${failures.length} failures`)
assert.equal(failures.length, 0, failures.join('; '))
