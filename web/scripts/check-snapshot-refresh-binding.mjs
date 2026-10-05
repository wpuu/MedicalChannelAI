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
let now = Date.parse('2026-10-04T23:20:00Z')
Date.now = () => now
const memory = new Map()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k),
}})
const base = JSON.parse(readFileSync(new URL('./fixtures/pr77-legacy-award-snapshot.json', import.meta.url), 'utf8'))
function snapshot(id, at = new Date(now).toISOString(), name = id) {
  const card = structuredClone(base.cards[0])
  card.opportunity_id = 'synthetic_refresh_' + id
  Object.assign(card.facts, { project_number: 'SYNTHETIC-' + id, project_name: '合成刷新 ' + name,
    hospital_name: '合成医院', buyer_name: '合成医院', market_code: 'TJ', market_name: '天津', region: '合成地区',
    published_at: '2026-10-04', registration_deadline: '2026-10-20T09:00:00+08:00', bid_deadline: '2026-10-30T09:00:00+08:00', public_contact: null })
  card.evidence_source_urls = ['https://official.invalid/synthetic/' + id]
  card.official_notices = []
  return { ...structuredClone(base), snapshot_as_of: at, cards: [card], opportunity_pool: [card],
    card_count: 1, opportunity_pool_count: 1, matched_count: 1, award_ledger: [], awarded_project_count: 0, award_price_reference: null }
}
let server = snapshot('A'), requests = 0, failure = null
globalThis.fetch = async url => {
  assert(['/api/public-snapshot', '/offline/today'].includes(String(url)), 'unexpected synthetic URL ' + url)
  requests++
  if (failure) return { ok: false, status: 503, json: async () => ({}) }
  const body = structuredClone(server)
  return { ok: true, status: 200, json: async () => body }
}
const errors = []
let checks = 0
async function check(name, fn) {
  checks++
  try { await fn(); console.log(name + ': PASS') }
  catch (e) { errors.push(name); console.error(name + ': FAIL: ' + e.message) }
}
try {
  const client = await import('../src/services/verifiedSnapshotClient.ts')
  const { StaticSnapshotTodayActionsService } = await import('../src/services/StaticSnapshotTodayActionsService.ts')
  const { todayActionsService } = await import('../src/services/index.ts')
  const { getVerifiedOpportunityPool } = await import('../src/services/verifiedOpportunityPool.ts')
  const guards = await import('../src/services/runtimeStatusApi.ts')
  const { ApiTodayActionsService } = await import('../src/services/ApiTodayActionsService.ts')
  function reset(value) { client.resetVerifiedSnapshotClient(); memory.clear(); server = value; failure = null; requests = 0 }
  await check('A -> server B -> shared TTL -> pool B -> real singleton Today/detail B; removed A absent', async () => {
    reset(snapshot('A'))
    assert.equal((await todayActionsService.getTodayActions()).cards[0].opportunity_id, 'synthetic_refresh_A')
    server = snapshot('B', new Date(now + 1000).toISOString())
    now += client.SNAPSHOT_CLIENT_TTL_MS + 1
    assert.equal((await getVerifiedOpportunityPool()).cards[0].opportunity_id, 'synthetic_refresh_B')
    assert.equal((await todayActionsService.getOpportunity('synthetic_refresh_B'))?.opportunity_id, 'synthetic_refresh_B', 'new B detail remains missing after pool switched to B')
    assert.equal(await todayActionsService.getOpportunity('synthetic_refresh_A'), null, 'withdrawn A detail remains actionable')
    assert.equal((await todayActionsService.getTodayActions()).cards[0].opportunity_id, 'synthetic_refresh_B')
    assert.equal(requests, 2, 'shared payload should avoid a third download')
  })
  await check('shared in-flight/TTL dedupe and exact payload reuse preserve local state without mutation', async () => {
    reset(snapshot('C'))
    const service = new StaticSnapshotTodayActionsService('/api/public-snapshot')
    const [data, card, pool] = await Promise.all([service.getTodayActions(), service.getOpportunity('synthetic_refresh_C'), getVerifiedOpportunityPool()])
    assert.equal(requests, 1)
    assert.equal(data.refreshed_at, server.snapshot_as_of)
    assert.equal(card.snapshot_as_of, server.snapshot_as_of)
    assert.equal(pool.cards[0].snapshot_as_of, server.snapshot_as_of)
    data.cards[0].facts.project_name = 'caller mutation'
    assert.equal((await service.getOpportunity('synthetic_refresh_C')).facts.project_name, '合成刷新 C')
    await service.updateFollowup('synthetic_refresh_C', { status: 'REVIEWING', note: '合成备注' })
    assert.equal((await service.getOpportunity('synthetic_refresh_C')).followup_status, 'REVIEWING')
    assert.equal(requests, 1)
  })
  await check('a new payload with the same clock is remapped, not reused solely by timestamp', async () => {
    reset(snapshot('D'))
    const service = new StaticSnapshotTodayActionsService('/api/public-snapshot')
    const first = await service.getTodayActions()
    server = snapshot('D', first.refreshed_at, 'D revised')
    now += client.SNAPSHOT_CLIENT_TTL_MS + 1
    assert.equal((await service.getTodayActions()).cards[0].facts.project_name, '合成刷新 D revised')
  })
  await check('expired HTTP failure rejects old Today/detail and failed fetch is immediately retryable', async () => {
    reset(snapshot('E'))
    const service = new StaticSnapshotTodayActionsService('/api/public-snapshot')
    await service.getTodayActions()
    now += client.SNAPSHOT_CLIENT_TTL_MS + 1; failure = true
    await assert.rejects(() => service.getTodayActions(), /SNAPSHOT_HTTP_503/)
    await assert.rejects(() => service.getOpportunity('synthetic_refresh_E'), /SNAPSHOT_HTTP_503/)
    failure = null; server = snapshot('F')
    assert.equal((await service.getTodayActions()).cards[0].opportunity_id, 'synthetic_refresh_F')
  })
  await check('new invalid payload cannot fall back to permanently cached valid cards', async () => {
    reset(snapshot('G'))
    const service = new StaticSnapshotTodayActionsService('/api/public-snapshot')
    await service.getTodayActions()
    now += client.SNAPSHOT_CLIENT_TTL_MS + 1; server = { ...snapshot('H'), mode: 'INVALID' }
    await assert.rejects(() => service.getTodayActions(), /SNAPSHOT_RESPONSE_INVALID/)
  })
  await check('market wrapper retains 24/72-hour warnings from the displayed snapshot', async () => {
    reset(snapshot('OLD24', new Date(now - 25 * 3600000).toISOString()))
    assert.match((await todayActionsService.getTodayActions()).coverage_warning, /超过24小时/)
    reset(snapshot('OLD72', new Date(now - 73 * 3600000).toISOString()))
    assert.match((await todayActionsService.getTodayActions()).coverage_warning, /超过72小时/)
  })
  function status(at, freshness = 'FRESH') {
    return { schema_version: '0.1', service: 'MedicalChannelAI', ready: true, degraded: false, production_ready: false, ai: { configured: true },
      snapshot: { available: true, source_mode: 'BUNDLED', snapshot_as_of: at, freshness, age_minutes: 0, stale_after_minutes: 1800, today_card_count: 1, opportunity_pool_count: 1 } }
  }
  await check('displayed old/mismatched/invalid version warns and blocks even with fresh service status', async () => {
    const current = new Date(now - 300000).toISOString(), fresh = status(current)
    for (const displayed of [new Date(now - 80 * 3600000).toISOString(), new Date(now - 600000).toISOString(), 'not-a-date', null, new Date(now + 3600000).toISOString()]) {
      assert(guards.runtimeSnapshotWarning(fresh, true, displayed), 'displayed unsafe version has no warning: ' + displayed)
      assert(guards.runtimeAutomationUnavailableReason(fresh, true, displayed), 'displayed unsafe version still enables automation: ' + displayed)
    }
    assert.equal(guards.runtimeSnapshotWarning(fresh, true, current), null)
    assert.equal(guards.runtimeAutomationUnavailableReason(fresh, true, current), null)
  })
  await check('existing STALE/unavailable protections and equivalent ISO clock remain compatible', async () => {
    const at = new Date(now - 300000).toISOString()
    assert.match(guards.runtimeSnapshotWarning(status(at, 'STALE'), true), /未成功刷新/)
    assert(guards.runtimeAutomationUnavailableReason(status(at, 'STALE'), true, at))
    assert(guards.runtimeAutomationUnavailableReason(null, true, at))
    assert.equal(guards.runtimeAutomationUnavailableReason(status(at), true, new Date(at).toISOString().replace('.000Z', 'Z')), null)
  })
  await check('API view-model card carries its source root version without changing wire fields', async () => {
    reset(snapshot('API'))
    const data = await new ApiTodayActionsService('/offline').getTodayActions()
    assert.equal(data.cards[0].snapshot_as_of, server.snapshot_as_of)
    assert.equal(data.opportunity_pool[0].snapshot_as_of, server.snapshot_as_of)
  })
} finally {
  globalThis.fetch = oldFetch; Date.now = oldNow; hooks.deregister()
  if (oldStorage) Object.defineProperty(globalThis, 'localStorage', oldStorage)
  else delete globalThis.localStorage
}
console.log(`Snapshot refresh/binding: ${checks} checks, ${errors.length} failures`)
assert.equal(errors.length, 0, errors.join('; '))
