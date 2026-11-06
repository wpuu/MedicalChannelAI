import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { webcrypto } from 'node:crypto'
import vm from 'node:vm'
import ts from 'typescript'
import { marketDefinition } from '../src/config/marketPreference.ts'
import { marketCodeForOpportunity } from '../src/utils/opportunityMarket.ts'
import { archiveResearchEventCard, researchEventWindowClosed } from '../src/utils/researchEventWindow.ts'
import { researchEventWindowClosed as apiEventClosed } from '../api/_runtimeOpportunityTime.js'

const eventAt = '2026-11-04T09:30:00+08:00'
const eventMs = Date.parse(eventAt)
let now = eventMs - 1
const NativeDate = Date
class ClockDate extends NativeDate {
  constructor(...args) { super(...(args.length ? args : [now])) }
  static now() { return now }
}
const eventClosed = (facts, at = now) => researchEventWindowClosed(facts, at)
const eventFacts = {
  research_event_at: eventAt,
  research_event_text: '携带资料及样品，现场讲解产品。时间：2026年11月4日9:30',
  product_use: '检验科、病理科、产前诊断、实验室等使用。',
}
for (const [facts, at, expected] of [
  [{}, eventMs, false],
  [eventFacts, eventMs - 1, false],
  [eventFacts, eventMs, true],
  [eventFacts, eventMs + 1, true],
  [{ research_event_at: '2026-11-04T09:30:00' }, eventMs - 1, true],
  [{ research_event_at: 'invalid' }, eventMs - 1, true],
  [{ research_event_text: eventFacts.research_event_text }, eventMs - 1, true],
  [{ research_event_at: '2027-02-30T09:30:00+08:00' }, eventMs - 1, true],
  [{ research_event_at: '2027-11-04T24:00:00+08:00' }, eventMs - 1, true],
]) {
  assert.equal(researchEventWindowClosed(facts, at), expected)
  assert.equal(apiEventClosed(facts, at), expected, 'Browser/API event semantics must agree')
}

function loadService(name, bindings = {}, append = '') {
  const source = readFileSync(new URL(`../src/services/${name}.ts`, import.meta.url), 'utf8')
  const parsed = ts.createSourceFile(`${name}.ts`, source, ts.ScriptTarget.Latest, true)
  const statements = parsed.statements.filter((statement) => !ts.isImportDeclaration(statement))
  const output = ts.transpileModule(ts.createPrinter().printFile(ts.factory.updateSourceFile(parsed, statements)), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText
  const context = {
    exports: {}, Date: ClockDate, structuredClone, crypto: webcrypto,
    researchEventWindowClosed: eventClosed, archiveResearchEventCard, marketCodeForOpportunity,
    ...bindings,
  }
  vm.createContext(context)
  vm.runInContext(output + append, context)
  return context
}

const bundled = JSON.parse(readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'))
const rawCard = structuredClone((bundled.opportunity_pool ?? bundled.cards)[0])
Object.assign(rawCard, {
  opportunity_id: 'tjzxfc_research_event_browser_regression',
  model_decision_status: 'AWAITING_MODEL', decision: null, recommendation_mode: 'PUBLIC_OPPORTUNITY',
})
Object.assign(rawCard.facts, {
  ...eventFacts, region: '天津市', market_code: 'TJ', lifecycle_state: 'MARKET_RESEARCH',
  published_at: '2026-11-02', registration_deadline: null,
  registration_deadline_date: null, registration_deadline_precision: null, bid_deadline: null,
})
rawCard.priority.components = rawCard.priority.components.map((component) =>
  component.code === 'DEADLINE_URGENCY' ? { ...component, points: 0 } : component,
)
const payload = { ...bundled, cards: [rawCard], opportunity_pool: [rawCard], matched_count: 1, opportunity_pool_count: 1 }
const publicBindings = {
  verifiedSnapshotUrl: '/fixture/snapshot', loadVerifiedSnapshotPayload: async () => payload,
  backfillLocalFollowupSnapshots() {}, hydrateLocalFollowups: (cards) => cards,
  personalizeTrialCards: (cards) => cards, persistLocalFollowup() {},
}
const staticModule = loadService('StaticSnapshotTodayActionsService', publicBindings)
const service = new staticModule.exports.StaticSnapshotTodayActionsService('/fixture/snapshot')
const futureToday = await service.getTodayActions()
const futureCard = futureToday.cards[0]
for (const key of Object.keys(eventFacts)) assert.equal(futureCard.facts[key], eventFacts[key])
assert.equal(futureCard.facts.registration_deadline, null)
const futureDraft = await service.requestOutreachDraft(rawCard.opportunity_id)
assert(futureDraft.draft.includes(eventFacts.research_event_text))
assert(futureDraft.draft.includes('不是报名截止时间'))
assert(!futureDraft.draft.includes('报名截止2026'))

const poolModule = loadService('verifiedOpportunityPool', { ...publicBindings, marketDefinition, marketCodeForOpportunity })
assert.equal((await poolModule.exports.getVerifiedOpportunityPool()).cards.length, 1)
const runtimeModule = loadService('RuntimeTrialTodayActionsService', { outreachBudgetFactText: () => null })
const temporal = runtimeModule.exports.refreshTrialTemporalPriority(futureCard, now)
assert.equal(temporal.priority.components.DEADLINE_URGENCY, 0, 'A future research event must not add deadline urgency')
assert.equal(temporal.facts.registration_deadline, null)

// Keep the exact snapshot that was actionable at publication, then cross the
// event while the SPA remains open. Every service must reassess browser time.
now = eventMs
assert.equal((await service.getTodayActions()).cards.length, 0)
assert.equal((await poolModule.exports.getVerifiedOpportunityPool()).cards.length, 0)
const archived = await service.getOpportunity(rawCard.opportunity_id)
assert.equal(archived.recommendation_mode, 'ARCHIVE')
assert.equal(archived.model_decision_status, 'NOT_ELIGIBLE')
assert.equal(archived.decision, null)
await assert.rejects(service.requestOutreachDraft(rawCard.opportunity_id))
const runtime = new runtimeModule.exports.RuntimeTrialTodayActionsService({
  getTodayActions: async () => futureToday,
  getOpportunity: async () => futureCard,
  requestOutreachDraft: async () => futureDraft,
})
assert.equal((await runtime.getTodayActions()).cards.length, 0)
assert.equal((await runtime.getOpportunity(rawCard.opportunity_id)).recommendation_mode, 'ARCHIVE')
await assert.rejects(runtime.requestOutreachDraft(rawCard.opportunity_id), /OPPORTUNITY_WINDOW_CLOSED/)

const followupState = { opportunity_id: rawCard.opportunity_id, current_status: 'CONTACTED', remind_at: null, history: [] }
const apiModule = loadService('ApiTodayActionsService', {
  fetch: async (url) => ({ ok: true, json: async () => String(url).includes('/followup/') ? followupState : String(url).endsWith('/today') ? payload : rawCard }),
})
const apiService = new apiModule.exports.ApiTodayActionsService('/api')
now = eventMs - 1
assert.equal((await apiService.getTodayActions()).cards[0].facts.product_use, eventFacts.product_use)
await apiService.getOpportunity(rawCard.opportunity_id)
await apiService.updateFollowup(rawCard.opportunity_id, { status: 'CONTACTED' })
now = eventMs
assert.equal((await apiService.getTodayActions()).cards.length, 0, 'Mutation response reuse must not reopen the event')
assert.equal((await apiService.getOpportunity(rawCard.opportunity_id)).model_decision_status, 'NOT_ELIGIBLE')

const storage = new Map()
const localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) }
const local = loadService('localFollowupStore', { localStorage }).exports
local.persistLocalFollowup({ ...futureCard, followup_status: 'CONTACTED' })
const historical = local.getStoredHistoricalOpportunityCard(rawCard.opportunity_id)
for (const key of Object.keys(eventFacts)) assert.equal(historical.facts[key], eventFacts[key])
assert.equal(historical.followup_status, 'CONTACTED')
assert.equal(historical.model_decision_status, 'NOT_ELIGIBLE')

const followed = loadService('followedApi', { isStableOpportunityId: () => true }, '\nexports.validateItemForTest = validateItem').exports
const followedItem = {
  opportunity_id: rawCard.opportunity_id, followup_status: 'CONTACTED', remind_at: null,
  latest_note: null, followup_updated_at: eventAt, evidence_source_urls: rawCard.evidence_source_urls,
  facts: {
    project_number: null, project_name: rawCard.facts.project_name, buyer_name: null, hospital_name: null,
    department: null, region: '天津市', lifecycle_state: 'MARKET_RESEARCH', notice_type: null,
    published_at: '2026-11-02', registration_deadline: null, registration_deadline_date: null,
    bid_deadline: null, expected_procurement_at: null, budget_cny: null, procurement_method: null,
    product_categories: [], product_items: [], public_contact: null, verification_status: 'VERIFIED', coverage_status: 'PARTIAL',
    ...eventFacts,
  },
}
assert.equal(followed.validateItemForTest(followedItem).facts.research_event_at, eventAt)
const legacyFollowed = structuredClone(followedItem)
for (const key of Object.keys(eventFacts)) delete legacyFollowed.facts[key]
assert.equal(followed.validateItemForTest(legacyFollowed).facts.research_event_at, null)
assert.throws(() => followed.validateItemForTest({ ...followedItem, facts: { ...followedItem.facts, research_event_at: {} } }))
assert.throws(() => followed.validateItemForTest({ ...followedItem, facts: { ...followedItem.facts, tenant_id: 'forbidden' } }))

const decision = { action: '核对公开调研安排', reasons: ['仅使用公告事实'], risks: [], needs_human_confirmation: ['执行前核对原文'] }
let providerCalls = 0
let crossOnResponse = false
let aiBusy = false
const aiModule = loadService('aiDecisionApi', {
  localStorage, verifiedSnapshotUrl: '/fixture/snapshot', isApiMode: false,
  beginAiRequest: () => aiBusy ? false : (aiBusy = true), endAiRequest: () => { aiBusy = false },
  getVerifiedSnapshotAsOf: async () => payload.snapshot_as_of,
  setTimeout: (callback) => { now = eventMs; queueMicrotask(callback) },
  fetch: async (_url, init) => {
    providerCalls++
    const input = JSON.parse(init.body)
    return { ok: true, status: 200, json: async () => {
      if (crossOnResponse) now = eventMs
      return input.opportunity_ids
        ? { items: input.opportunity_ids.map((id) => ({ opportunity_id: id, status: 'READY', decision })) }
        : { decision }
    } }
  },
})
const ai = aiModule.exports
storage.clear()
now = eventMs - 1
assert.equal((await ai.requestAiDecision(futureCard)).action, decision.action)
assert.equal(providerCalls, 1)
const changedEventCard = { ...futureCard, facts: { ...futureCard.facts, research_event_at: new NativeDate(eventMs + 60_000).toISOString() } }
await ai.requestAiDecision(changedEventCard)
assert.equal(providerCalls, 2, 'Changing the event must invalidate the browser decision fingerprint')
now = eventMs
await assert.rejects(ai.requestAiDecision(futureCard), (error) => error.code === 'OPPORTUNITY_WINDOW_CLOSED')
assert.equal(providerCalls, 2, 'Closed events must not read through to a provider or cached READY')
const staleReady = { ...futureCard, model_decision_status: 'READY', decision }
assert.equal((await ai.hydrateCachedAiDecisions([staleReady]))[0].model_decision_status, 'NOT_ELIGIBLE')

now = eventMs - 1
aiModule.getVerifiedSnapshotAsOf = async () => { now = eventMs; return payload.snapshot_as_of }
await assert.rejects(ai.requestAiDecision(futureCard), (error) => error.code === 'OPPORTUNITY_WINDOW_CLOSED')
aiModule.getVerifiedSnapshotAsOf = async () => payload.snapshot_as_of
storage.clear()
crossOnResponse = true
now = eventMs - 1
await assert.rejects(ai.requestAiDecision(futureCard), (error) => error.code === 'OPPORTUNITY_WINDOW_CLOSED')
assert.equal(storage.size, 0, 'An in-flight response after the event must not be written to localStorage')
assert.equal(aiBusy, false)
for (const cacheOnly of [false, true]) {
  now = eventMs - 1
  const batch = await ai.requestAiDecisionBatch([futureCard], { cacheOnly })
  assert.equal(Object.keys(batch.decisions).length, 0)
  assert.equal(batch.errors[futureCard.opportunity_id], 'OPPORTUNITY_WINDOW_CLOSED')
}
now = eventMs - 1
assert.equal((await ai.hydrateSharedAiDecisions([futureCard]))[0].recommendation_mode, 'ARCHIVE')
assert.equal(aiBusy, false)

console.log('Research event browser window and AI cache boundaries: PASS')
