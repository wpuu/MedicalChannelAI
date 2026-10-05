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
const KEY = 'medopp.pipeline-followups.v1', a = 'synthetic_storage_saved', b = 'synthetic_storage_new'
let now = Date.parse('2026-10-05T00:00:00Z'), getFault = null, setFault = null, server
const memory = new Map();Date.now = () => now
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem(k) { if (k === KEY && getFault) throw new DOMException('Synthetic blocked read', getFault); return memory.get(k) ?? null },
  setItem(k,v) { if (k === KEY && setFault) throw new DOMException('Synthetic blocked write', setFault); memory.set(k,v) },
  removeItem(k) { memory.delete(k) },
}})
const base = JSON.parse(readFileSync(new URL('./fixtures/pr77-legacy-award-snapshot.json', import.meta.url), 'utf8'))
function card(id) {
  const c = structuredClone(base.cards[0]);c.opportunity_id = id
  Object.assign(c.facts, { project_number: id, project_name: id, hospital_name: '合成医院', buyer_name: '合成医院',
    market_code: 'TJ', market_name: '天津', published_at: '2026-10-04', public_contact: null,
    registration_deadline: '2026-10-20T00:00:00Z', registration_deadline_date: null, bid_deadline: '2026-10-30T00:00:00Z' })
  c.evidence_source_urls = ['https://official.invalid/synthetic/storage/' + id]
  c.legal_windows = [];c.official_notices = [];c.decision = null
  return c
}
function payload(cards) { return { ...structuredClone(base), cards, opportunity_pool: cards,
  snapshot_as_of: new Date(now).toISOString(), card_count: cards.length, opportunity_pool_count: cards.length,
  award_ledger: [], awarded_project_count: 0, award_price_reference: null } }
globalThis.fetch = async url => {
  assert.equal(String(url), '/api/public-snapshot')
  return { ok: true, status: 200, json: async () => structuredClone(server) }
}
const failed = [], passed = []
async function check(name, fn) {
  try { await fn();passed.push(name);console.log(name + ': PASS') }
  catch (e) { failed.push(name);console.error(name + ': FAIL: ' + e.message) }
}
let resetSnapshot
try {
  const client = await import('../src/services/verifiedSnapshotClient.ts');resetSnapshot = client.resetVerifiedSnapshotClient
  const { StaticSnapshotTodayActionsService } = await import('../src/services/StaticSnapshotTodayActionsService.ts')
  const { RuntimeTrialTodayActionsService } = await import('../src/services/RuntimeTrialTodayActionsService.ts')
  const store = await import('../src/services/localFollowupStore.ts')
  const pool = await import('../src/services/verifiedOpportunityPool.ts')
  const reminders = await import('../src/services/reminderApi.ts')
  const followed = await import('../src/services/followedApi.ts')
  async function setup(historical = false) {
    getFault = null;setFault = null;memory.clear();client.resetVerifiedSnapshotClient();server = payload([card(a),card(b)])
    const service = new RuntimeTrialTodayActionsService(new StaticSnapshotTodayActionsService('/api/public-snapshot'))
    await service.updateFollowup(a, { status: 'REVIEWING', note: '合成已有记录', remind_at: '2026-10-04T01:00:00.000Z' })
    const newCard = (await pool.getVerifiedOpportunityPool()).cards.find(x => x.opportunity_id === b)
    if (historical) { now += client.SNAPSHOT_CLIENT_TTL_MS + 1;server = payload([card(b)]);assert.equal(await service.getOpportunity(a),null) }
    return { service, newCard }
  }
  const faults = [
    ['quota-write', null, 'QuotaExceededError'], ['security-write', null, 'SecurityError'],
    ['security-read', 'SecurityError', null], ['security-read-write', 'SecurityError', 'SecurityError'],
  ]
  for (const [label, readFault, writeFault] of faults) {
    for (const action of ['status','note','join','remind','acknowledge','historical-note']) {
      await check(label + ' ' + action + ' rejects; original bytes unchanged; retry saves once', async () => {
        const { service, newCard } = await setup(action === 'historical-note')
        const original = memory.get(KEY), saved = structuredClone(store.readLocalFollowups()[a])
        const input = action === 'status' ? { status: 'CONTACTED', note: '合成状态更新' }
          : action === 'remind' ? { status: 'REVIEWING', note: '合成下一步', remind_at: '2026-10-03T01:00:00.000Z' }
          : { status: 'REVIEWING', note: '合成未保存备注' }
        const joined = { ...newCard, followup_status: 'REVIEWING', followup_history: [{ id: 'synthetic_once', status: 'REVIEWING', note: '合成加入跟进', at: new Date(now).toISOString(), actor: '合成用户' }] }
        const operation = () => action === 'join' ? Promise.resolve().then(() => store.persistLocalFollowup(joined))
          : action === 'acknowledge' ? reminders.acknowledgeDueReminder(store.localReminderId(a))
          : service.updateFollowup(a,input)
        getFault = readFault;setFault = writeFault
        await assert.rejects(operation, e => e.name === (readFault ?? writeFault))
        assert.equal(memory.get(KEY), original)
        getFault = null;setFault = null
        const unchanged = await service.getOpportunity(a)
        if (action !== 'historical-note') assert.equal(unchanged.followup_status,'REVIEWING')
        assert.deepEqual(store.readLocalFollowups()[a],saved)
        await operation();const after = store.readLocalFollowups()
        if (action === 'join') { assert.deepEqual(after[a],saved);assert.equal(after[b].history.length,1);assert.equal(after[b].history[0].id,'synthetic_once') }
        else if (action === 'acknowledge') { assert.equal(after[a].remind_at,null);assert.deepEqual(after[a].history,saved.history);assert.equal(after[a].status,saved.status) }
        else { assert.equal(after[a].history.length,saved.history.length+1);assert.equal(after[a].history.filter(x=>x.note===input.note).length,1);assert.equal(after[a].status,input.status) }
        if (action === 'remind') assert.equal(after[a].remind_at,input.remind_at)
        assert.deepEqual(after[a].public_snapshot,saved.public_snapshot)
        if (action === 'historical-note') { const history=store.getStoredHistoricalOpportunityCard(a);assert.equal(history.model_decision_status,'NOT_ELIGIBLE');assert.equal(history.priority.score,0) }
        else { const details=await service.getOpportunity(action==='join'?b:a);const verified=(await pool.getVerifiedOpportunityPool()).cards.find(x=>x.opportunity_id===details.opportunity_id);assert.equal(verified.followup_status,details.followup_status);assert.deepEqual(verified.followup_history,details.followup_history) }
      })
    }
  }
  await check('blocked storage reads reject current pool/detail/followed/inbox instead of returning empty success', async () => {
    const { service }=await setup();const before=memory.get(KEY);getFault='SecurityError'
    assert.throws(()=>store.readLocalFollowups(),e=>e.name==='SecurityError')
    for(const read of [()=>service.getTodayActions(),()=>service.getOpportunity(a),()=>pool.getVerifiedOpportunityPool(),()=>followed.getFollowedOpportunities(),()=>reminders.getDueReminders()])await assert.rejects(read,e=>e.name==='SecurityError')
    assert.equal(memory.get(KEY),before);getFault=null
    assert.equal(store.readLocalFollowups()[a].history.length,1)
  })
  await check('normal reads preserve prior score, followup snapshot and independent reminder semantics', async () => {
    const { service }=await setup();const before=memory.get(KEY)
    const today=(await service.getTodayActions()).opportunity_pool.find(x=>x.opportunity_id===a),detail=await service.getOpportunity(a),verified=(await pool.getVerifiedOpportunityPool()).cards.find(x=>x.opportunity_id===a)
    assert.deepEqual(today.priority,detail.priority);assert.deepEqual(verified.priority,detail.priority);assert.equal(memory.get(KEY),before)
    await service.updateFollowup(a,{status:'CONTACTED',note:'合成正常备注'})
    assert.equal(store.readLocalFollowups()[a].history.length,2);assert.equal(store.readLocalFollowups()[a].remind_at,'2026-10-04T01:00:00.000Z')
  })
} finally {
  getFault=null;setFault=null;resetSnapshot?.();globalThis.fetch=oldFetch;Date.now=oldNow;hooks.deregister()
  if(oldStorage)Object.defineProperty(globalThis,'localStorage',oldStorage)
  else delete globalThis.localStorage
}
console.log(`Followup storage failures: ${passed.length+failed.length} checks, ${failed.length} failures`)
assert.equal(failed.length,0,failed.join('; '))
