import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { marketDefinition, marketCodesForSelection } from '../src/config/marketPreference.ts'
import { marketCodeForOpportunity } from '../src/utils/opportunityMarket.ts'
import { researchEventWindowClosed } from '../src/utils/researchEventWindow.ts'

for (const [id, facts, expected] of [
  ['tjmugh_runtime', { region: '天津市' }, 'TJ'],
  ['runtime_jilin', { region: '吉林省长春市' }, 'JL'],
  ['runtime_beijing', { region: '北京市朝阳区' }, 'BJ'],
  ['runtime_hebei', { region: '河北' }, 'HE'],
  ['runtime_liaoning', { region: '辽宁省' }, 'LN'],
  ['runtime_heilongjiang', { region: '黑龙江省' }, 'HL'],
  ['ccgp_jl_legacy', {}, 'JL'],
  ['ccgp_hl_be17744f48e2bdc1', { region: '哈尔滨市' }, 'HL'],
  ['ccgp_hl_county', { region: '塔河县' }, 'HL'],
  ['ccgp_he_county', { region: '赵县' }, 'HE'],
  ['ccgp_jl_district', { region: '市辖区' }, 'JL'],
  ['ccgp_hl_explicit_province', { region: '河北省' }, 'HE'],
  ['tjmugh_legacy', {}, 'TJ'],
  ['unknown_opaque_id', {}, null],
  ['unknown_city_id', { region: '哈尔滨市' }, null],
  ['ccgp_hl_unknown_region', { region: '全国' }, null],
  ['tjmugh_unsupported_region', { region: '山东省' }, null],
  ['ccgp_hl_unsupported_province', { region: '山东省济南市' }, null],
  ['ccgp_hl_unsupported_bare_province', { region: '山东' }, null],
  ['ccgp_hl_unsupported_autonomous_region', { region: '广西壮族自治区南宁市' }, null],
  ['ccgp_hl_unsupported_shanghai', { region: '上海市浦东新区' }, null],
  ['ccgp_hl_unsupported_chongqing', { region: '重庆市' }, null],
  ['ccgp_hl_unsupported_hongkong', { region: '香港特别行政区' }, null],
  ['ccgp_hl_unsupported_macau', { region: '澳门特别行政区' }, null],
  ['tjmugh_explicit', { market_code: ' bj ', region: '天津市' }, 'BJ'],
  ['tjmugh_unsupported_code', { market_code: 'SD', region: '天津市' }, null],
]) {
  assert.equal(marketCodeForOpportunity({ opportunity_id: id, facts }), expected, id)
}

// Exercise the real pool loader/mapper with the shape produced by the Queue
// runtime builder: official region exists, but market metadata is absent.
const bundled = JSON.parse(readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'))
const base = (bundled.opportunity_pool ?? bundled.cards)[0]
assert(base, 'A verified public card is required as the mapper fixture')
const runtimeCard = (id, region) => ({
  ...base,
  opportunity_id: id,
  facts: {
    ...base.facts,
    region,
    market_code: undefined,
    market_name: undefined,
    market_admin_code: undefined,
    registration_deadline: null,
    registration_deadline_date: null,
    bid_deadline: null,
  },
})
const payload = {
  ...bundled,
  opportunity_pool: [runtimeCard('tjmugh_runtime', '天津市'), runtimeCard('ccgp_jl_runtime', '吉林省')],
}

const source = readFileSync(new URL('../src/services/verifiedOpportunityPool.ts', import.meta.url), 'utf8')
const parsed = ts.createSourceFile('verifiedOpportunityPool.ts', source, ts.ScriptTarget.Latest, true)
const withoutImports = ts.factory.updateSourceFile(parsed, parsed.statements.filter((statement) => !ts.isImportDeclaration(statement)))
const compiled = ts.transpileModule(ts.createPrinter().printFile(withoutImports), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText
const context = {
  exports: {},
  marketCodeForOpportunity,
  researchEventWindowClosed,
  marketDefinition,
  verifiedSnapshotUrl: '/fixture/public-snapshot',
  loadVerifiedSnapshotPayload: async () => payload,
  backfillLocalFollowupSnapshots: () => {},
  hydrateLocalFollowups: (cards) => cards,
  personalizeTrialCards: (cards) => cards,
}
vm.createContext(context)
vm.runInContext(compiled, context)
const result = await context.exports.getVerifiedOpportunityPool()
assert.equal(result.total, 2)
assert.deepEqual(Array.from(result.cards, (card) => card.facts.market_code).sort(), ['JL', 'TJ'])
for (const [selection, expectedId] of [['TJ', 'tjmugh_runtime'], ['JL', 'ccgp_jl_runtime']]) {
  const allowed = new Set(marketCodesForSelection(selection))
  const visible = Array.from(result.cards).filter((card) => allowed.has(card.facts.market_code))
  assert.deepEqual(visible.map((card) => card.opportunity_id), [expectedId])
  const market = marketDefinition(visible[0].facts.market_code)
  assert.equal(visible[0].facts.market_name, market.name)
  assert.equal(visible[0].facts.market_admin_code, market.adminCode)
}

const todaySource = readFileSync(new URL('../src/services/index.ts', import.meta.url), 'utf8')
const todayParsed = ts.createSourceFile('index.ts', todaySource, ts.ScriptTarget.Latest, true)
const scopeClass = todayParsed.statements.find((statement) =>
  ts.isClassDeclaration(statement) && statement.name?.text === 'MarketScopedTodayActionsService',
)
assert(scopeClass)
const todayCompiled = ts.transpileModule(
  ts.createPrinter().printNode(ts.EmitHint.Unspecified, scopeClass, todayParsed)
    + '\nglobalThis.TodayScope = MarketScopedTodayActionsService',
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } },
).outputText
const todayContext = { marketCodeForOpportunity, marketCodesForSelection: () => ['TJ'] }
vm.createContext(todayContext)
vm.runInContext(todayCompiled, todayContext)
const today = await new todayContext.TodayScope({ getTodayActions: async () => payload }).getTodayActions()
assert.deepEqual(Array.from(today.cards, (card) => card.opportunity_id), ['tjmugh_runtime'])

// Optional read-only acceptance against a complete, already published snapshot.
// Use its publication clock so retained acceptance evidence is reproducible.
const snapshotPath = process.argv[2]
if (snapshotPath) {
  const authority = JSON.parse(readFileSync(snapshotPath, 'utf8'))
  const live = authority.response ?? authority
  const livePool = live.opportunity_pool ?? live.cards
  const publishedMs = Date.parse(live.snapshot_as_of)
  assert(Array.isArray(livePool) && livePool.length > 0 && Number.isFinite(publishedMs))
  assert.equal(livePool.length, live.opportunity_pool_count)
  const originalPayload = JSON.stringify(live)
  class PublicationDate extends Date {
    constructor(...args) { super(...(args.length ? args : [publishedMs])) }
    static now() { return publishedMs }
  }
  const liveContext = {
    ...context,
    exports: {},
    Date: PublicationDate,
    researchEventWindowClosed: (facts, at = publishedMs) => researchEventWindowClosed(facts, at),
    loadVerifiedSnapshotPayload: async () => live,
  }
  vm.createContext(liveContext)
  vm.runInContext(compiled, liveContext)
  const mapped = await liveContext.exports.getVerifiedOpportunityPool()
  assert.equal(mapped.cards.length, livePool.length, 'The complete actionable authority pool must survive mapping')
  const expectedMarket = (card) => {
    const source = card.opportunity_id.match(/^ccgp_(bj|tj|he|ln|jl|hl)_/i)
    if (source) return source[1].toUpperCase()
    assert(/^(?:tjmugh|tjnothop|tjfch|teda|tjzxfc|tjzyefy)_/i.test(card.opportunity_id), 'Acceptance fixture must have a registered source')
    return 'TJ'
  }
  const counts = {}
  for (const selection of ['ALL', 'TJ', 'BJ', 'HL', 'HE', 'JL', 'LN']) {
    const allowed = new Set(marketCodesForSelection(selection))
    const expected = livePool.filter((card) => allowed.has(expectedMarket(card))).map((card) => card.opportunity_id)
    const poolVisible = Array.from(mapped.cards).filter((card) => allowed.has(card.facts.market_code))
    assert.deepEqual(poolVisible.map((card) => card.opportunity_id).sort(), [...expected].sort(), `Pool ${selection}`)
    for (const card of poolVisible) assert.equal(card.facts.market_code, expectedMarket(card), card.opportunity_id)
    const scopedContext = { marketCodeForOpportunity, marketCodesForSelection: () => [...allowed] }
    vm.createContext(scopedContext)
    vm.runInContext(todayCompiled, scopedContext)
    const scoped = await new scopedContext.TodayScope({ getTodayActions: async () => live }).getTodayActions()
    assert.deepEqual(Array.from(scoped.opportunity_pool, (card) => card.opportunity_id), expected, `Today pool ${selection}`)
    assert.deepEqual(Array.from(scoped.cards, (card) => card.opportunity_id), expected.slice(0, 5), `Today top ${selection}`)
    counts[selection] = poolVisible.length
  }
  const top = live.cards[0]
  assert.equal(mapped.cards.find((card) => card.opportunity_id === top.opportunity_id)?.facts.market_code, expectedMarket(top))
  assert.equal(JSON.stringify(live), originalPayload, 'Market display must not mutate the published authority')
  console.log(`Published authority market scope: PASS ${JSON.stringify({ ...counts, top_id: top.opportunity_id, top_market: expectedMarket(top) })}`)
}

console.log('Opportunity market scope: PASS')
