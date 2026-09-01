import assert from 'node:assert/strict'
import {
  buildDecisionMessages,
  parseDecisionContent,
} from '../api/ai/_decisionContract.js'

const facts = {
  project_code: 'TEST-001',
  project_name: '天津市某医院检验设备采购项目',
  hospital: '天津市某医院',
  buyer_name: '天津市某医院',
  department: '检验科',
  region: '天津市',
  lifecycle_stage: 'BIDDING',
  notice_type: '公开招标公告',
  publish_date: '2026-09-01',
  registration_deadline: '2026-09-08T16:00:00+08:00',
  registration_deadline_date: null,
  registration_deadline_precision: 'MINUTE',
  bid_deadline: '2026-09-24T10:00:00+08:00',
  expected_purchase_date: null,
  budget: 1000000,
  procurement_method: '公开招标',
  product_categories: ['医疗设备'],
  products: [],
  official_contact: null,
  verification_status: 'VERIFIED',
  coverage_status: 'PARTIAL',
}

const messages = buildDecisionMessages(
  facts,
  ['https://www.ccgp.gov.cn/example.htm'],
  null,
  'OPEN',
  '2026-09-01T13:00:00.000Z',
)
const modelInput = JSON.stringify(messages)
for (const forbidden of [
  'runtime_window_status',
  'coverage_status',
  'verification_status',
  'lifecycle_stage',
  'BIDDING',
  'PARTIAL',
  'VERIFIED',
]) {
  assert.equal(modelInput.includes(forbidden), false, `machine token leaked into model prompt: ${forbidden}`)
}
assert.equal(modelInput.includes('当前仍在报名或获取文件窗口内'), true)

const safe = parseDecisionContent(JSON.stringify({
  action: '今天先联系采购代理确认文件获取方式，并下载官方附件核对技术需求。',
  reasons: ['报名或获取文件窗口仍在开放期，当前适合先完成公开信息核实。'],
  risks: ['产品参数和资格条件以官方附件为准，未核实前不要向客户承诺。'],
}))
assert.equal(safe.requires_human_confirmation, true)

for (const leaked of [
  {
    action: 'runtime_window_status=OPEN，建议立即联系采购人。',
    reasons: ['公开窗口仍开放。'],
    risks: [],
  },
  {
    action: '建议今天联系采购人。',
    reasons: ['项目处于BIDDING阶段。'],
    risks: [],
  },
  {
    action: '建议今天联系采购人。',
    reasons: ['coverage_status=PARTIAL，公告信息可能不完整。'],
    risks: [],
  },
  {
    action: '建议今天联系采购人。',
    reasons: ['现有信息有限。'],
    risks: ['参数后续可能调整，需要提前留意。'],
  },
]) {
  assert.throws(
    () => parseDecisionContent(JSON.stringify(leaked)),
    (error) => error?.code === 'AI_RESPONSE_INVALID',
  )
}

console.log('AI decision contract checks: PASS')
