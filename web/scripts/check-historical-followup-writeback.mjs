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
let now = Date.parse('2026-10-05T00:20:00Z')
Date.now = () => now
const memory = new Map()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k),
}})
const base = JSON.parse(readFileSync(new URL('./fixtures/pr77-legacy-award-snapshot.json', import.meta.url), 'utf8'))
const id = 'synthetic_historical_writeback'
function snapshot(include = true, name = '合成历史项目初版') {
  const card = structuredClone(base.cards[0])
  card.opportunity_id = id
  Object.assign(card.facts, { project_number: 'SYNTHETIC-HISTORY-001', project_name: name,
    hospital_name: '合成医院', buyer_name: '合成医院', market_code: 'TJ', market_name: '天津', region: '合成地区',
    published_at: '2026-10-04', registration_deadline: '2026-10-20T09:00:00+08:00', bid_deadline: '2026-10-30T09:00:00+08:00',
    public_contact: null, product_items: [{ raw_name: '合成医疗器械', category: '合成器械', quantity: '1', specification: null }] })
  card.evidence_source_urls = ['https://official.invalid/synthetic/historical/A']
  card.official_notices = []; card.legal_windows = []; card.decision = null
  card.model_decision_status = 'AWAITING_MODEL'; card.model_block_reason = null
  return { ...structuredClone(base), snapshot_as_of: new Date(now).toISOString(), cards: include ? [card] : [], opportunity_pool: include ? [card] : [],
    card_count: include ? 1 : 0, opportunity_pool_count: include ? 1 : 0, matched_count: include ? 1 : 0,
    award_ledger: [], awarded_project_count: 0, award_price_reference: null }
}
let server, failure = false, requests = 0
globalThis.fetch = async url => {
  assert.equal(String(url), '/api/public-snapshot')
  requests++
  return { ok: !failure, status: failure ? 503 : 200, json: async () => structuredClone(server) }
}
const failures = [], checks = []
async function check(name, fn) {
  try { await fn(); checks.push(name); console.log(name + ': PASS') }
  catch (e) { failures.push(name); console.error(name + ': FAIL: ' + e.message) }
}
try {
  const client = await import('../src/services/verifiedSnapshotClient.ts')
  const { StaticSnapshotTodayActionsService } = await import('../src/services/StaticSnapshotTodayActionsService.ts')
  const store = await import('../src/services/localFollowupStore.ts')
  const { todayActionsService } = await import('../src/services/index.ts')
  const reminders = await import('../src/services/reminderApi.ts')
  async function savedAndWithdrawn(service = new StaticSnapshotTodayActionsService('/api/public-snapshot')) {
    client.resetVerifiedSnapshotClient(); memory.clear(); failure = false; requests = 0; server = snapshot()
    await service.updateFollowup(id, { status: 'REVIEWING', note: '合成初始记录', remind_at: '2026-10-01' })
    const entry = structuredClone(store.readLocalFollowups()[id])
    now += client.SNAPSHOT_CLIENT_TTL_MS + 1; server = snapshot(false)
    assert.equal(await service.getOpportunity(id), null)
    assert.equal(store.getStoredHistoricalOpportunityCard(id).model_decision_status, 'NOT_ELIGIBLE')
    return { service, entry }
  }
  function frozen(entry) { assert.deepEqual(store.readLocalFollowups()[id].public_snapshot, entry.public_snapshot) }
  await check('withdrawn saved card accepts CONTACTED while keeping frozen public facts', async () => {
    const { service, entry } = await savedAndWithdrawn()
    await service.updateFollowup(id, { status: 'CONTACTED', note: '合成历史联系' })
    const saved = store.readLocalFollowups()[id]
    assert.equal(saved.status, 'CONTACTED'); assert.equal(saved.history.length, 2)
    assert.equal(saved.history[0].note, '合成历史联系'); assert.deepEqual(saved.history[1], entry.history[0]); frozen(entry)
    assert.equal(saved.remind_at, entry.remind_at)
  })
  await check('historical note appends once without changing status or reminder', async () => {
    const { service, entry } = await savedAndWithdrawn()
    await service.updateFollowup(id, { status: entry.status, note: '合成历史备注' })
    const saved = store.readLocalFollowups()[id]
    assert.equal(saved.status, entry.status); assert.equal(saved.remind_at, entry.remind_at)
    assert.equal(saved.history[0].note, '合成历史备注'); assert.equal(saved.history.length, 2); frozen(entry)
  })
  await check('historical reminder sets date independently; later note retains it; due inbox can acknowledge', async () => {
    const { service, entry } = await savedAndWithdrawn()
    await service.updateFollowup(id, { status: 'REVIEWING', remind_at: '2026-10-02', note: '合成下一步' })
    await service.updateFollowup(id, { status: 'REVIEWING', note: '合成提醒后备注' })
    const saved = store.readLocalFollowups()[id]
    assert.equal(saved.status, 'REVIEWING'); assert.equal(saved.remind_at, '2026-10-02')
    assert.equal(saved.history.length, 3); frozen(entry)
    const due = await reminders.getDueReminders()
    assert(due.some(item => item.opportunity_id === id))
    await reminders.acknowledgeDueReminder(store.localReminderId(id))
    assert.equal(store.readLocalFollowups()[id].status, 'REVIEWING')
    assert.equal(store.readLocalFollowups()[id].remind_at, null); frozen(entry)
  })
  await check('unknown ID rejected without creating or changing a local record', async () => {
    const { service } = await savedAndWithdrawn()
    const before = memory.get('medopp.pipeline-followups.v1')
    await assert.rejects(() => service.updateFollowup('synthetic_unknown', { status: 'CONTACTED', note: '无效合成记录' }), /未找到对应商机/)
    assert.equal(memory.get('medopp.pipeline-followups.v1'), before)
  })
  await check('missing or mismatched frozen snapshot is not a historical write target', async () => {
    const { service, entry } = await savedAndWithdrawn()
    for (const value of [{ ...entry, public_snapshot: undefined }, { ...entry, public_snapshot: { ...entry.public_snapshot, opportunity_id: 'synthetic_other' } }]) {
      memory.set('medopp.pipeline-followups.v1', JSON.stringify({ [id]: value }))
      const before = memory.get('medopp.pipeline-followups.v1')
      await assert.rejects(() => service.updateFollowup(id, { status: 'CONTACTED' }), /未找到对应商机/)
      assert.equal(memory.get('medopp.pipeline-followups.v1'), before)
    }
  })
  await check('historical writes never reintroduce public cards or outreach eligibility', async () => {
    const { service, entry } = await savedAndWithdrawn()
    await service.updateFollowup(id, { status: 'CONTACTED', note: '合成私有记录' })
    assert.equal(await service.getOpportunity(id), null)
    assert.equal((await service.getTodayActions()).opportunity_pool.length, 0)
    const historic = store.getStoredHistoricalOpportunityCard(id)
    assert.equal(historic.model_decision_status, 'NOT_ELIGIBLE'); assert.equal(historic.match_status, 'ARCHIVE'); assert.equal(historic.decision, null)
    await assert.rejects(() => service.requestOutreachDraft(id), /OUTREACH_GROUNDING_INSUFFICIENT/); frozen(entry)
  })
  await check('reentry uses newly verified facts with historical status/history/reminder preserved', async () => {
    const { service, entry } = await savedAndWithdrawn()
    await service.updateFollowup(id, { status: 'CONTACTED', note: '合成历史联系', remind_at: '2026-10-12' })
    const privateEntry = structuredClone(store.readLocalFollowups()[id]); frozen(entry)
    now += client.SNAPSHOT_CLIENT_TTL_MS + 1; server = snapshot(true, '合成历史项目重新核验版')
    const current = await service.getOpportunity(id)
    assert.equal(current.facts.project_name, '合成历史项目重新核验版'); assert.equal(current.followup_status, 'CONTACTED')
    assert.equal(current.remind_at, '2026-10-12'); assert.deepEqual(current.followup_history, privateEntry.history)
    frozen(entry)
    await service.updateFollowup(id, { status: 'CONTACTED', note: '合成当前池备注' })
    const active = store.readLocalFollowups()[id]
    assert.equal(active.history.length, privateEntry.history.length + 1); assert.equal(active.remind_at, '2026-10-12')
    assert.equal(active.public_snapshot.facts.project_name, '合成历史项目重新核验版')
  })
  await check('historical terminal status clears reminder without rewriting public evidence', async () => {
    const { service, entry } = await savedAndWithdrawn()
    await service.updateFollowup(id, { status: 'ARCHIVED', note: '合成历史归档' })
    assert.equal(store.readLocalFollowups()[id].status, 'ARCHIVED'); assert.equal(store.readLocalFollowups()[id].remind_at, null)
    assert.deepEqual(store.readLocalFollowups()[id].history[1], entry.history[0]); frozen(entry)
  })
  await check('snapshot HTTP/invalid failures stay fail-closed even with a saved historical entry', async () => {
    const { service } = await savedAndWithdrawn()
    const before = memory.get('medopp.pipeline-followups.v1')
    now += client.SNAPSHOT_CLIENT_TTL_MS + 1; failure = true
    await assert.rejects(() => service.updateFollowup(id, { status: 'CONTACTED' }), /SNAPSHOT_HTTP_503/)
    assert.equal(memory.get('medopp.pipeline-followups.v1'), before)
    failure = false; server = { ...snapshot(false), mode: 'INVALID' }
    await assert.rejects(() => service.updateFollowup(id, { status: 'CONTACTED' }), /SNAPSHOT_RESPONSE_INVALID/)
    assert.equal(memory.get('medopp.pipeline-followups.v1'), before)
  })
  await check('real deferred/market/runtime singleton delegates historical writes', async () => {
    const { entry } = await savedAndWithdrawn(todayActionsService)
    await todayActionsService.updateFollowup(id, { status: 'CONTACTED', note: '合成单例历史备注' })
    assert.equal(store.readLocalFollowups()[id].status, 'CONTACTED'); frozen(entry)
    assert.equal(await todayActionsService.getOpportunity(id), null)
  })
} finally {
  globalThis.fetch = oldFetch; Date.now = oldNow; hooks.deregister()
  if (oldStorage) Object.defineProperty(globalThis, 'localStorage', oldStorage)
  else delete globalThis.localStorage
}
console.log(`Historical writeback: ${checks.length + failures.length} checks, ${failures.length} failures`)
assert.equal(failures.length, 0, failures.join('; '))
