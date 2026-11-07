import assert from 'node:assert/strict'
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
