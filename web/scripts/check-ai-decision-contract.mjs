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

const evidenceUrls = ['https://www.ccgp.gov.cn/example.htm']
const parse = (payload, overrides = {}) => parseDecisionContent(JSON.stringify(payload), {
  facts,
  evidenceUrls,
  customerContext: null,
  windowStatus: 'OPEN',
  ...overrides,
})

const messages = buildDecisionMessages(
  facts,
  evidenceUrls,
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
assert.equal(modelInput.includes('你没有事实陈述权'), true)
assert.equal(modelInput.includes('只输出纯 JSON'), true)
assert.equal(modelInput.includes('REVIEW_OFFICIAL_SOURCE'), true)
assert.equal(modelInput.includes('VERIFY_REQUIREMENTS'), true)
assert.equal(modelInput.includes('CONTACT_PUBLIC_CONTACT'), false)

const safe = parse({
  action_codes: ['REVIEW_OFFICIAL_SOURCE', 'VERIFY_REQUIREMENTS'],
})
assert.equal(safe.requires_human_confirmation, true)
assert.equal(safe.action.includes('已核验官方来源'), true)
assert.equal(safe.action.includes('核实技术要求'), true)
assert.equal(safe.reasons.some((item) => item.includes('天津市某医院检验设备采购项目')), true)
assert.equal(safe.reasons.some((item) => item.includes('2026年9月8日 16:00')), true)
assert.equal(safe.reasons.some((item) => item.includes('100万元')), true)
for (const unsupportedInference of ['通常存在一定竞争', '提前获取完整招标需求', '官方未披露医院既往', '中标不确定性较高']) {
  assert.equal(JSON.stringify(safe).includes(unsupportedInference), false)
}

const contactFacts = {
  ...facts,
  official_contact: { name: '范老师', phone: '022-12345678', email: null },
}
const contactDecision = parseDecisionContent(JSON.stringify({
  action_codes: ['CONTACT_PUBLIC_CONTACT', 'VERIFY_REQUIREMENTS'],
}), {
  facts: contactFacts,
  evidenceUrls,
  customerContext: null,
  windowStatus: 'OPEN',
})
assert.equal(contactDecision.action.includes('022-12345678'), true)
assert.equal(contactDecision.action.includes('只记录对方明确回复'), true)
assert.equal(contactDecision.risks.some((item) => item.includes('实际回复未知')), true)

assert.throws(
  () => parse({ action_codes: ['CONTACT_PUBLIC_CONTACT'] }),
  (error) => error?.code === 'AI_RESPONSE_INVALID',
)
assert.throws(
  () => parse({ action_codes: ['UNKNOWN_ACTION'] }),
  (error) => error?.code === 'AI_RESPONSE_INVALID',
)
assert.throws(
  () => parse({ action_codes: ['VERIFY_REQUIREMENTS', 'VERIFY_REQUIREMENTS'] }),
  (error) => error?.code === 'AI_RESPONSE_INVALID',
)
assert.throws(
  () => parse({ action_codes: ['VERIFY_REQUIREMENTS', 'REVIEW_OFFICIAL_SOURCE', 'PREPARE_REQUIRED_MATERIALS', 'CONTACT_PUBLIC_CONTACT'] }),
  (error) => error?.code === 'AI_RESPONSE_INVALID',
)
assert.throws(
  () => parse({
    action: '主动联系采购人可获取完整采购需求。',
    reasons: ['预算较大，通常存在一定竞争。'],
    risks: ['暂无医院既往采购规律。'],
  }),
  (error) => error?.code === 'AI_RESPONSE_INVALID',
)

const targetOnlyContext = {
  target_hospital: {
    hospital: '天津市某医院',
    watched_by_customer: true,
  },
  hospital_relationship: null,
  matching_product_capabilities: [],
  partnering_policy: {
    can_find_manufacturer: null,
    can_partner_channel: null,
    can_handle_lease: null,
  },
}
const targetOnlyMessages = JSON.stringify(buildDecisionMessages(
  facts,
  evidenceUrls,
  targetOnlyContext,
  'OPEN',
  '2026-09-01T13:00:00.000Z',
))
assert.equal(targetOnlyMessages.includes('MATCH_CONFIRMED_RESOURCES'), false)
assert.throws(
  () => parseDecisionContent(JSON.stringify({ action_codes: ['MATCH_CONFIRMED_RESOURCES'] }), {
    facts,
    evidenceUrls,
    customerContext: targetOnlyContext,
    windowStatus: 'OPEN',
  }),
  (error) => error?.code === 'AI_RESPONSE_INVALID',
)

const relationshipContext = {
  ...targetOnlyContext,
  hospital_relationship: {
    hospital: '天津市某医院',
    department: '检验科',
    relationship_strength: 'MEDIUM',
  },
}
const relationshipMessages = JSON.stringify(buildDecisionMessages(
  facts,
  evidenceUrls,
  relationshipContext,
  'OPEN',
  '2026-09-01T13:00:00.000Z',
))
assert.equal(relationshipMessages.includes('MATCH_CONFIRMED_RESOURCES'), true)

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
  budget: null,
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
assert.equal(relativeInput.includes('CONFIRM_RELATIVE_WINDOW'), true)
assert.equal(relativeInput.includes('系统内部推算'), false)
assert.equal(relativeInput.includes('RELATIVE_REGISTRATION_WINDOW_7_DAYS'), false)
// CONFIRM_RELATIVE_WINDOW is an allowed action code; only the standalone internal
// window enum must stay out of the model prompt.
assert.equal(relativeInput.includes('"RELATIVE_WINDOW"'), false)

const relativeSafe = parseDecisionContent(JSON.stringify({
  action_codes: ['CONFIRM_RELATIVE_WINDOW', 'REVIEW_OFFICIAL_SOURCE'],
}), {
  facts: relativeFacts,
  evidenceUrls: ['https://www.tjfch.com.cn/example.shtml'],
  customerContext: null,
  windowStatus: 'RELATIVE_WINDOW',
})
assert.equal(relativeSafe.requires_human_confirmation, true)
assert.equal(relativeSafe.action.includes('系统内部推算日期'), true)
assert.equal(relativeSafe.reasons.some((item) => item.includes('自公告发布之日起7天')), true)
assert.equal(relativeSafe.risks.some((item) => item.includes('未公布精确截止日期或时刻')), true)

console.log('AI deterministic action selector contract: PASS')
