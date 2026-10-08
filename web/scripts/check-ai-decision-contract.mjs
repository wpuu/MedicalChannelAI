// Contract checks for (1) deterministic per-card next steps and (2) the
// page-level AI brief (MCAI-AI-PAGE-BRIEF-001).
import assert from 'node:assert/strict'
import {
  buildRuleDecision,
  selectRuleActionCodes,
} from '../api/ai/_decisionContract.js'
import {
  annotateBriefItems,
  buildPageBriefMessages,
  buildRuleBrief,
  parsePageBriefContent,
  safeNote,
} from '../api/ai/_pageBrief.js'

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
  products: [{ name: '全自动生化分析仪', category: '医疗设备', quantity: '1台', specification: '详见采购文件' }],
  quality_flags: [],
  official_contact: null,
  verification_status: 'VERIFIED',
  coverage_status: 'PARTIAL',
}
const evidenceUrls = ['https://www.ccgp.gov.cn/example.htm']

// ---- (1) Deterministic per-card rules ---------------------------------------
const safe = buildRuleDecision(facts, evidenceUrls, null, 'OPEN')
assert.deepEqual(selectRuleActionCodes(facts, evidenceUrls, null, 'OPEN'), ['REVIEW_OFFICIAL_SOURCE', 'VERIFY_REQUIREMENTS', 'PREPARE_REQUIRED_MATERIALS'])
assert.equal(safe.requires_human_confirmation, true)
assert.equal(safe.action.includes('已核验官方来源'), true)
assert.equal(safe.action.includes('核实技术要求'), true)
assert.equal(safe.reasons.some((item) => item.includes('天津市某医院检验设备采购项目')), true)
assert.equal(safe.reasons.some((item) => item.includes('2026年9月8日 16:00')), true)
assert.equal(safe.reasons.some((item) => item.includes('100万元')), true)
// Item-specific risks only; page-level disclaimers are not repeated per card.
assert.equal(safe.risks.some((item) => item.includes('完整品目和技术参数')), true)
assert.equal(safe.risks.some((item) => item.includes('仍需用户人工确认')), false)
for (const unsupportedInference of ['通常存在一定竞争', '提前获取完整招标需求', '官方未披露医院既往', '中标不确定性较高']) {
  assert.equal(JSON.stringify(safe).includes(unsupportedInference), false)
}
// Deterministic: same input, same output.
assert.deepEqual(buildRuleDecision(facts, evidenceUrls, null, 'OPEN'), safe)

const contactFacts = { ...facts, official_contact: { name: '范老师', phone: '022-12345678', email: null } }
const lateContact = buildRuleDecision(contactFacts, evidenceUrls, null, 'LATE_WINDOW')
assert.deepEqual(selectRuleActionCodes(contactFacts, evidenceUrls, null, 'LATE_WINDOW'), ['CHECK_LATE_WINDOW_OPTIONS', 'REVIEW_OFFICIAL_SOURCE', 'CONTACT_PUBLIC_CONTACT'])
assert.equal(lateContact.action.includes('022-12345678'), true)
assert.equal(lateContact.action.includes('只记录对方明确回复'), true)
assert.equal(lateContact.risks.some((item) => item.includes('以官方答复为准')), true)
// No public contact -> never a contact action.
assert.equal(selectRuleActionCodes(facts, evidenceUrls, null, 'OPEN').includes('CONTACT_PUBLIC_CONTACT'), false)
// No https evidence -> never "open the official source".
assert.equal(selectRuleActionCodes(facts, ['http://insecure.example'], null, 'OPEN').includes('REVIEW_OFFICIAL_SOURCE'), false)

const targetOnlyContext = {
  target_hospital: { hospital: '天津市某医院', watched_by_customer: true },
  hospital_relationship: null,
  matching_product_capabilities: [],
  partnering_policy: { can_find_manufacturer: null, can_partner_channel: null, can_handle_lease: null },
}
assert.equal(selectRuleActionCodes(facts, evidenceUrls, targetOnlyContext, 'OPEN').includes('MATCH_CONFIRMED_RESOURCES'), false)
assert.equal(buildRuleDecision(facts, evidenceUrls, targetOnlyContext, 'OPEN').risks.some((item) => item.includes('不能视为已有关系')), true)
const relationshipContext = {
  ...targetOnlyContext,
  hospital_relationship: { hospital: '天津市某医院', department: '检验科', relationship_strength: 'MEDIUM' },
}
assert.equal(selectRuleActionCodes(facts, evidenceUrls, relationshipContext, 'OPEN')[1], 'MATCH_CONFIRMED_RESOURCES')

const relativeFacts = {
  ...facts,
  project_code: null,
  project_name: '医疗器械精细化管理项目测试企业征集公告',
  lifecycle_stage: 'MARKET_RESEARCH',
  notice_type: '采购前期测试企业征集公告',
  registration_deadline: null,
  bid_deadline: null,
  budget: null,
  quality_flags: ['RELATIVE_REGISTRATION_WINDOW_7_DAYS'],
}
const relativeSafe = buildRuleDecision(relativeFacts, ['https://www.tjfch.com.cn/example.shtml'], null, 'RELATIVE_WINDOW')
assert.equal(selectRuleActionCodes(relativeFacts, ['https://www.tjfch.com.cn/example.shtml'], null, 'RELATIVE_WINDOW')[0], 'CONFIRM_RELATIVE_WINDOW')
assert.equal(relativeSafe.action.includes('系统内部推算日期'), true)
assert.equal(relativeSafe.reasons.some((item) => item.includes('自公告发布之日起7天')), true)
assert.equal(relativeSafe.risks.some((item) => item.includes('未公布精确截止日期或时刻')), true)
assert.equal(relativeSafe.risks.some((item) => item.includes('未列明预算')), true)

// ---- (2) Page brief contract ------------------------------------------------
const nowMs = Date.parse('2026-09-20T02:00:00Z') // 2026-09-20 10:00 Shanghai
const items = annotateBriefItems([
  { opportunity_id: 'a', facts: { ...facts, project_name: '甲医院超声采购', buyer_name: '甲医院', registration_deadline: '2026-09-22T16:00:00+08:00', budget: 3_000_000 }, evidenceUrls, windowStatus: 'OPEN' },
  { opportunity_id: 'b', facts: { ...facts, project_name: '乙医院调度平台', buyer_name: '乙医院', registration_deadline: '2026-10-20T16:00:00+08:00', bid_deadline: '2026-10-30T10:00:00+08:00', budget: 500_000 }, evidenceUrls, windowStatus: 'OPEN' },
  { opportunity_id: 'c', facts: { ...facts, project_name: '甲医院内镜采购意向', buyer_name: '甲医院', lifecycle_stage: 'PROCUREMENT_INTENT', notice_type: '采购意向公告', registration_deadline: null, bid_deadline: null, budget: null }, evidenceUrls, windowStatus: 'OPEN' },
], nowMs)
assert.equal(items[0].ref, '#1')
assert.equal(items[0].daysLeft, 2)
assert.equal(items[0].sameBuyer, true)
assert.equal(items[2].earlySignal, true)

const prompt = JSON.stringify(buildPageBriefMessages(items, new Date(nowMs).toISOString()))
for (const forbidden of ['runtime_window_status', 'coverage_status', 'verification_status', 'lifecycle_stage', 'BIDDING', 'PARTIAL', 'VERIFIED', '"OPEN"', 'LATE_WINDOW"', 'opportunity_id']) {
  assert.equal(prompt.includes(forbidden), false, `machine token leaked into page-brief prompt: ${forbidden}`)
}
assert.equal(prompt.includes('只输出纯 JSON'), true)
assert.equal(prompt.includes('严禁出现任何数字'), true)

const good = parsePageBriefContent(JSON.stringify({
  headline: '先抓甲医院两个项目',
  focus: [
    { ref: '#1', reason: 'DEADLINE_SOON', note: '截止临近先核对文件' },
    { ref: '#3', reason: 'EARLY_SIGNAL' },
  ],
  skip: [{ ref: '#2', reason: 'NON_DEVICE_SCOPE' }],
}), items)
assert.equal(good.brief_source, 'AI')
assert.equal(good.focus[0].opportunity_id, 'a')
assert.equal(good.focus[0].fact_line.includes('报名截止 9月22日 16:00（剩2天）'), true)
assert.equal(good.focus[0].fact_line.includes('300万元'), true)
assert.equal(good.focus[0].next_step.includes('官方来源'), true)
assert.equal(good.skip[0].opportunity_id, 'b')
assert.equal(good.same_buyer_groups[0].count, 2)
assert.equal(good.deadlines_within_7_days.length, 1)

const rejects = (payload, why) => assert.throws(
  () => parsePageBriefContent(typeof payload === 'string' ? payload : JSON.stringify(payload), items),
  (error) => error?.code === 'AI_RESPONSE_INVALID',
  why,
)
rejects('not json', 'garbage')
rejects({ focus: [] }, 'empty focus')
rejects({ focus: [{ ref: '#9', reason: 'CLEAR_DEVICE_DEMAND' }] }, 'unknown ref')
rejects({ focus: [{ ref: '#2', reason: 'DEADLINE_SOON' }] }, 'deadline not within 7 days')
rejects({ focus: [{ ref: '#2', reason: 'EARLY_SIGNAL' }] }, 'not an early signal')
rejects({ focus: [{ ref: '#2', reason: 'LARGE_BUDGET' }] }, 'budget too small')
rejects({ focus: [{ ref: '#2', reason: 'SAME_BUYER_BATCH' }] }, 'no same buyer')
rejects({ focus: [{ ref: '#1', reason: 'WIN_PROBABILITY' }] }, 'unknown reason')
rejects({ focus: [{ ref: '#1', reason: 'DEADLINE_SOON' }], skip: [{ ref: '#1', reason: 'LOW_INFO' }] }, 'duplicate ref')
rejects({ focus: [{ ref: '#1', reason: 'DEADLINE_SOON' }], skip: [{ ref: '#2', reason: 'WINDOW_TOO_TIGHT' }] }, 'window not that tight')
rejects({ focus: [{ ref: '#1', reason: 'DEADLINE_SOON' }], score: 90 }, 'extra field')
rejects({ focus: [{ ref: '#1', reason: 'DEADLINE_SOON', budget: 1 }] }, 'extra entry field')
rejects({ focus: [1, 2, 3, 4].map(() => ({ ref: '#1', reason: 'DEADLINE_SOON' })) }, 'too many focus')

// Notes never carry numbers, amounts, probabilities or relationship claims.
for (const bad of ['预算300万值得做', '三百万项目', '中标概率高', '院方有关系', '剩2天', 'x'.repeat(41)]) {
  assert.equal(safeNote(bad, 40), null, bad)
}
assert.equal(safeNote('截止临近先核对文件', 40), '截止临近先核对文件')
const dropped = parsePageBriefContent(JSON.stringify({ focus: [{ ref: '#1', reason: 'DEADLINE_SOON', note: '预算300万' }] }), items)
assert.equal(dropped.focus[0].note, null)

const rules = buildRuleBrief(items)
assert.equal(rules.brief_source, 'RULES')
assert.deepEqual(rules.focus.map((item) => item.opportunity_id), ['a', 'c', 'b'])
assert.equal(rules.headline, null)

console.log('Rule next-step + page-brief contract: PASS')
