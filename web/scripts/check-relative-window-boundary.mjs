import assert from 'node:assert/strict'
import { runtimeWindowStatus } from '../api/ai/_analyzeCore.js'
import {
  buildGroundedOutreachDraft,
  outreachWindow,
} from '../api/ai/analyze.js'

const relativeFacts = {
  project_name: '医疗器械精细化管理项目测试企业征集公告',
  hospital_name: '天津市第一中心医院',
  buyer_name: '天津市第一中心医院',
  lifecycle_state: 'MARKET_RESEARCH',
  notice_type: '采购前期测试企业征集公告',
  published_at: '2026-09-01',
  registration_deadline: null,
  registration_deadline_date: null,
  bid_deadline: null,
  budget: null,
  public_contact: { name: '王老师', phone: '022-12345678', email: null },
  quality_flags: ['RELATIVE_REGISTRATION_WINDOW_7_DAYS'],
}

const sanitizedRelativeFacts = {
  project_code: null,
  project_name: relativeFacts.project_name,
  hospital: relativeFacts.hospital_name,
  buyer_name: relativeFacts.buyer_name,
  department: null,
  region: '天津市',
  lifecycle_stage: relativeFacts.lifecycle_state,
  notice_type: relativeFacts.notice_type,
  publish_date: relativeFacts.published_at,
  registration_deadline: null,
  registration_deadline_date: null,
  registration_deadline_precision: null,
  bid_deadline: null,
  expected_purchase_date: null,
  budget: null,
  procurement_method: '采购前期测试企业征集',
  product_categories: [],
  products: [],
  quality_flags: relativeFacts.quality_flags,
  official_contact: relativeFacts.public_contact,
  verification_status: 'VERIFIED',
  coverage_status: 'PARTIAL',
}

assert.equal(
  runtimeWindowStatus(sanitizedRelativeFacts, Date.parse('2026-09-08T23:00:00+08:00')),
  'RELATIVE_WINDOW',
)
assert.equal(
  runtimeWindowStatus(sanitizedRelativeFacts, Date.parse('2026-09-09T00:01:00+08:00')),
  'CLOSED',
)

const openWindow = outreachWindow(relativeFacts, Date.parse('2026-09-05T12:00:00+08:00'))
assert.deepEqual(openWindow, { open: true, late: false, relative: true })
const closedWindow = outreachWindow(relativeFacts, Date.parse('2026-09-09T00:01:00+08:00'))
assert.deepEqual(closedWindow, { open: false, late: false, relative: true })

const draft = buildGroundedOutreachDraft(
  { opportunity_id: 'tjfch_test_example', facts: relativeFacts },
  { context: null },
  Date.parse('2026-09-05T12:00:00+08:00'),
)
assert.equal(draft.includes('自公告发布之日起7天'), true)
assert.equal(draft.includes('未公布精确截止时刻'), true)
assert.equal(draft.includes('确认目前测试企业报名是否仍开放'), true)
for (const forbidden of ['2026年9月8日', '9月8日截止', '17:00截止', '官方截止日期为']) {
  assert.equal(draft.includes(forbidden), false, `relative outreach invented deadline: ${forbidden}`)
}

const evidenceUrls = ['https://www.tjfch.com.cn/example.shtml']
assert.equal(evidenceUrls.every((url) => url.startsWith('https://www.tjfch.com.cn/')), true)

console.log('Relative registration window boundary checks: PASS')
