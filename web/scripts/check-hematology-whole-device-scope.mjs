import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

if (process.argv.includes('--a02-only')) {
  const views = [
    { name: '商机池', url: new URL('../src/pages/OpportunityPoolPage.tsx', import.meta.url) },
    { name: 'Today卡片', url: new URL('../src/components/today/ActionCard.tsx', import.meta.url) },
    { name: '商机详情', url: new URL('../src/pages/OpportunityDetailPage.tsx', import.meta.url) },
  ]
  const clauses = [
    ['共享纯函数导入', "import { classifyHematologyWholeDeviceScope } from '@/utils/hematologyWholeDeviceScope'"],
    ['基于卡片计算范围', 'const deviceScope = classifyHematologyWholeDeviceScope(card)'],
    ['整机相关一致文案', "'整机相关 · 资格待核'"],
    ['非本期一致文案', "'非本期整机'"],
    ['依据不足一致文案', "'证据不足待核'"],
    ['展示保守理由', '{deviceScope.reason}'],
    ['结构化产品编号', 'deviceScope.evidence.itemIndex + 1'],
    ['结构化产品原名', 'deviceScope.evidence.productName'],
    ['风险免责声明', '仅判断首期产品范围；不代表型号参数、采购资格或投标条件已核实。'],
    ['三态提示标识', '血细胞分析仪整机范围提示'],
  ]
  let verified = 0
  for (const view of views) {
    const source = readFileSync(view.url, 'utf8')
    for (const [label, token] of clauses) {
      assert.ok(source.includes(token), view.name + ': ' + label)
      verified += 1
    }
  }
  const today = readFileSync(views[1].url, 'utf8')
  const detail = readFileSync(views[2].url, 'utf8')
  assert.ok(today.includes('<ActionButtons'), 'Today原操作按钮保留')
  verified += 1
  assert.ok(today.includes('<DecisionBlock'), 'Today原AI决策保留')
  verified += 1
  assert.ok(detail.includes('<FollowupCard'), '详情原跟进流程保留')
  verified += 1
  assert.ok(detail.includes('<OpportunityExecutionCard'), '详情原经营资源入口保留')
  verified += 1
  assert.ok(detail.includes('历史跟进只按当时保存的快照标注产品范围，不反映当前官方公告或行动窗口。'), '历史快照非实时免责声明')
  verified += 1
  console.log('PASS A02 cross-page static contract: ' + verified + '/' + verified)
  process.exit(0)
}
import { classifyHematologyWholeDeviceScope as classify } from '../src/utils/hematologyWholeDeviceScope.js'

const URL = 'https://example.test/official/notice'
const makeCard = (names, overrides = {}) => ({
  facts: {
    market_code: 'TJ', verification_status: 'VERIFIED',
    products: names.map((name) => ({ name, category: null, specification: null })),
    project_name: '合成公告：离线规则测试', product_categories: ['血液检验'],
    ...overrides.facts,
  },
  evidence_source_urls: [URL],
  ...Object.fromEntries(Object.entries(overrides).filter(([key]) => key !== 'facts')),
})

let checks = 0
function check(label, card, expected, index = null) {
  const source = JSON.stringify(card)
  const actual = classify(card)
  assert.equal(actual.status, expected, label)
  assert.equal(typeof actual.reason, 'string', label)
  assert.ok(actual.reason.length > 0, label)
  if (expected === 'IN_SCOPE') {
    assert.ok(actual.reason.includes('仍须核对资格'), label)
    assert.equal(actual.evidence?.itemIndex, index, label)
    assert.ok(actual.evidence.field.startsWith('facts.products['), label)
  }
  assert.ok(!/(资格满足|已符合投标资格|确保中标|可直接投标)/u.test(actual.reason), label)
  assert.equal(JSON.stringify(card), source, label + ': input mutated')
  checks += 1
}

check('blood cell analyzer whole device', makeCard(['全自动血细胞分析仪']), 'IN_SCOPE', 0)
check('five-part blood analyzer', makeCard(['五分类血细胞分析仪']), 'IN_SCOPE', 0)
check('three-part analyzer', makeCard(['三分类血球仪']), 'IN_SCOPE', 0)
check('hemocyte analyzer variation', makeCard(['血液细胞分析仪']), 'IN_SCOPE', 0)
check('hematology device mixed separate reagent', makeCard(['血球仪配套试剂', '血细胞分析仪']), 'IN_SCOPE', 1)
check('hematology device then reagent in same product row', makeCard(['血球仪及配套试剂']), 'IN_SCOPE', 0)
check('reagent in same product row before analyzer', makeCard(['质控品与血细胞分析仪']), 'IN_SCOPE', 0)
check('reagent-only', makeCard(['血细胞分析仪专用试剂']), 'OUT_OF_SCOPE')
check('diluent-only', makeCard(['血球仪专用稀释液']), 'OUT_OF_SCOPE')
check('quality control-only', makeCard(['血球仪质控品']), 'OUT_OF_SCOPE')
check('calibrator-only', makeCard(['血细胞分析仪校准液']), 'OUT_OF_SCOPE')
check('consumables only', makeCard(['血球仪耗材']), 'OUT_OF_SCOPE')
check('maintenance only', makeCard(['血细胞分析仪维保服务']), 'OUT_OF_SCOPE')
check('software only', makeCard(['血球仪配套软件']), 'OUT_OF_SCOPE')
check('other analyzer', makeCard(['全自动生化分析仪']), 'OUT_OF_SCOPE')
check('multiple out of scope accessories', makeCard(['校准品', '血球仪清洗液']), 'OUT_OF_SCOPE')
check('device and category disagreement', makeCard([], {facts:{products:[{name:'血细胞分析仪',category:'试剂',specification:null}]}}), 'NEEDS_EVIDENCE')
check('device and specification disagreement', makeCard([], {facts:{products:[{name:'血球仪',category:null,specification:'校准试剂盒'}]}}), 'NEEDS_EVIDENCE')
check('combined ambiguous bundle', makeCard(['血球仪整机含配套试剂']), 'NEEDS_EVIDENCE')
check('generic IVD', makeCard(['IVD设备']), 'NEEDS_EVIDENCE')
check('generic laboratory', makeCard(['检验设备']), 'NEEDS_EVIDENCE')
check('title alone no structured product', makeCard([], {facts:{project_name:'采购五分类血球仪'}}), 'NEEDS_EVIDENCE')
check('category only no product', makeCard([], {facts:{product_categories:['血细胞分析仪']}}), 'NEEDS_EVIDENCE')
check('non Tianjin province', makeCard(['血球仪'], {facts:{market_code:'BJ'}}), 'OUT_OF_SCOPE')
check('missing market', makeCard(['血球仪'], {facts:{market_code:null}}), 'NEEDS_EVIDENCE')
check('not verified', makeCard(['血球仪'], {facts:{verification_status:'PARTIAL'}}), 'NEEDS_EVIDENCE')
check('no evidence URL', makeCard(['血球仪'], {evidence_source_urls: []}), 'NEEDS_EVIDENCE')
check('http URL only', makeCard(['血球仪'], {evidence_source_urls: ['http://example.test/notice']}), 'NEEDS_EVIDENCE')
check('mixed ambiguous and excluded', makeCard(['血球仪试剂', '检验设备']), 'NEEDS_EVIDENCE')
check('empty product list remains empty without new rows', makeCard([], {}), 'NEEDS_EVIDENCE')
check('bad card', null, 'NEEDS_EVIDENCE')
check('bad product entry', makeCard([], {facts:{products:[null]}}), 'NEEDS_EVIDENCE')
check('no candidate list is a real zero, not a generated opportunity', makeCard([], {facts:{products:[]}}), 'NEEDS_EVIDENCE')
assert.equal([].map(classify).length, 0, 'zero candidates remain zero')
checks += 1

console.log('PASS A01 hematology whole-device offline targeted checks: ' + checks + '/' + checks)
