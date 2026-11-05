import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { marketDefinition, marketCodesForSelection } from '../src/config/marketPreference.ts'
import { marketCodeForOpportunity } from '../src/utils/opportunityMarket.ts'

for (const [id, facts, expected] of [
  ['tjmugh_runtime', { region: '天津市' }, 'TJ'],
  ['runtime_jilin', { region: '吉林省长春市' }, 'JL'],
  ['runtime_beijing', { region: '北京市朝阳区' }, 'BJ'],
  ['runtime_hebei', { region: '河北' }, 'HE'],
  ['runtime_liaoning', { region: '辽宁省' }, 'LN'],
  ['runtime_heilongjiang', { region: '黑龙江省' }, 'HL'],
  ['ccgp_jl_legacy', {}, 'JL'],
  ['tjmugh_legacy', {}, 'TJ'],
  ['unknown_opaque_id', {}, null],
  ['tjmugh_unsupported_region', { region: '山东省' }, null],
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

console.log('Opportunity market scope: PASS')
