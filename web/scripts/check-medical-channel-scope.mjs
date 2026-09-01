import assert from 'node:assert/strict'
import {
  filterSnapshotToMedicalChannel,
  isMedicalChannelRelevantText,
} from '../api/_medicalChannelScope.js'

for (const title of [
  '天津市第五中心医院医疗设备更新项目-数字减影血管造影机采购项目',
  '天津市滨海新区大港医院CT影像设备维保项目',
  '天津市胸科医院检验科设备租赁服务项目',
  '天津市滨海新区海滨人民医院采购人工智能GPU（8卡）算力服务器项目',
]) {
  assert.equal(isMedicalChannelRelevantText(title), true, `scope should include: ${title}`)
}

for (const title of [
  '天津中医药大学第二附属医院安保服务项目',
  '天津市海河医院战略型复合人才培养项目',
  '西青区卫生健康基层医疗卫生机构财务信息化管理项目',
]) {
  assert.equal(isMedicalChannelRelevantText(title), false, `scope should exclude: ${title}`)
}

const card = (id, title, rank) => ({ opportunity_id: id, rank, facts: { project_name: title, product_categories: [], product_items: [] } })
const filtered = filterSnapshotToMedicalChannel({
  matched_count: 4,
  card_count: 4,
  opportunity_pool_count: 4,
  cards: [
    card('medical', '数字彩色超声诊断系统采购项目', 1),
    card('security', '医院安保服务项目', 2),
    card('finance', '医院财务信息化管理项目', 3),
    card('gpu', '人工智能GPU算力服务器项目', 4),
  ],
  opportunity_pool: [
    card('medical', '数字彩色超声诊断系统采购项目', 1),
    card('security', '医院安保服务项目', 2),
    card('finance', '医院财务信息化管理项目', 3),
    card('gpu', '人工智能GPU算力服务器项目', 4),
  ],
})
assert.deepEqual(filtered.opportunity_pool.map((item) => item.opportunity_id), ['medical', 'gpu'])
assert.deepEqual(filtered.opportunity_pool.map((item) => item.rank), [1, 2])
assert.equal(filtered.matched_count, 2)
assert.equal(filtered.card_count, 2)
assert.equal(filtered.opportunity_pool_count, 2)
console.log('Medical channel scope checks: PASS')
