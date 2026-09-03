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
  quality_flags: [],
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

const relativeFacts = {
  ...facts,
  project_code: null,
  project_name: '医疗器械精细化管理项目测试企业征集公告',
  lifecycle_stage: 'MARKET_RESEARCH',
  notice_type: '采购前期测试企业征集公告',
  publish_date: '2026-09-01',
  registration_deadline: null,
  registration_deadline_date: null,
  registration_deadline_precision: null,
  bid_deadline: null,
  procurement_method: '采购前期测试企业征集',
  quality_flags: ['RELATIVE_REGISTRATION_WINDOW_7_DAYS'],
}
const relativeMessages = buildDecisionMessages(
  relativeFacts,
  ['https://www.tjfch.com.cn/example.shtml'],
  null,
  'RELATIVE_WINDOW',
  '2026-09-03T02:00:00.000Z',
)
const relativeInput = JSON.stringify(relativeMessages)
assert.equal(relativeInput.includes('官方仅公布“自公告发布之日起7天”的相对报名窗口'), true)
assert.equal(relativeInput.includes('不得把系统内部推算日期或时刻写成官方截止时间'), true)
assert.equal(relativeInput.includes('根据已核验公开截止时间，当前仍在报名或获取文件窗口内'), false)
assert.equal(relativeInput.includes('RELATIVE_REGISTRATION_WINDOW_7_DAYS'), false)
assert.equal(relativeInput.includes('RELATIVE_WINDOW'), false)

const relativeSafe = parseDecisionContent(JSON.stringify({
  action: '今天先联系公告公开联系人，确认测试企业报名是否仍开放，并按官方要求准备产品资料。',
  reasons: ['官方采用发布日起7天的相对报名窗口，当前应优先人工确认实际开放状态。'],
  risks: ['官方未公布精确截止时刻，不要把系统内部行动窗口当作官方截止时间。'],
}), { relativeRegistrationWindow: true })
assert.equal(relativeSafe.requires_human_confirmation, true)

for (const inventedDeadline of [
  {
    action: '请在2026年9月8日前完成报名。',
    reasons: ['报名截止为2026年9月8日。'],
    risks: [],
  },
  {
    action: '今天联系医院确认资料。',
    reasons: ['9月8日是官方报名截止日。'],
    risks: [],
  },
  {
    action: '今天联系医院确认资料。',
    reasons: ['报名窗口仍开放。'],
    risks: ['官方截止时间为17:00。'],
  },
]) {
  assert.throws(
    () => parseDecisionContent(JSON.stringify(inventedDeadline), { relativeRegistrationWindow: true }),
    (error) => error?.code === 'AI_RESPONSE_INVALID',
  )
}

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
