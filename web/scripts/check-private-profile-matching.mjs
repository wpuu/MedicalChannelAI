import assert from 'node:assert/strict'
import { minimalPrivateContextFromProfile } from '../api/_privateProfileContext.js'
import { buildGroundedOutreachDraft } from '../api/ai/analyze.js'

const profile = {
  capabilities: [
    {
      keyword: 'IVD',
      capability_type: 'DIRECT_UNCONFIRMED',
      updated_at: '2026-09-03T00:00:00.000Z',
    },
  ],
  relationships: [
    {
      hospital: '天津市第一中心医院',
      department: null,
      relationship_strength: 'STRONG',
      updated_at: '2026-09-03T00:00:00.000Z',
    },
  ],
  targets: [],
  preferences: null,
}

const igmQualityControl = {
  project_name: '天津市第一中心医院甲型肝炎病毒IgM抗体质控品等采购项目院内比选公告',
  hospital_name: '天津市第一中心医院',
  buyer_name: '天津市第一中心医院',
  department: null,
  lifecycle_state: 'BIDDING',
  notice_type: '院内比选采购公告',
  published_at: '2026-08-31',
  registration_deadline: null,
  registration_deadline_date: null,
  bid_deadline: '2026-09-07T17:00:00+08:00',
  budget: { amount_cny: 4588, currency: 'CNY' },
  product_categories: [],
  product_items: [],
  public_contact: {
    name: '王老师',
    title: null,
    phone: '23628323',
    email: 'sdyzxsbwzcsbk@tj.gov.cn',
  },
  quality_flags: [],
}

const matched = minimalPrivateContextFromProfile(profile, igmQualityControl)
assert.equal(matched.context.matching_product_capabilities.length, 1)
assert.equal(matched.context.matching_product_capabilities[0].category, 'IVD')
assert.equal(matched.context.matching_product_capabilities[0].capability_type, 'DIRECT_UNCONFIRMED')
assert.equal(matched.context.hospital_relationship?.relationship_strength, 'STRONG')

const outreach = buildGroundedOutreachDraft(
  { opportunity_id: 'tjfch_20260831_030197537', facts: igmQualityControl },
  matched,
  Date.parse('2026-09-03T06:00:00.000Z'),
)
assert.match(outreach, /王老师，您好/)
assert.match(outreach, /正在确认IVD相关供货条件/)
assert.doesNotMatch(outreach, /STRONG|强关系|院内关系/)
assert.doesNotMatch(outreach, /已获授权|厂家授权|授权代理/)

const unrelatedTherapeuticAntibody = {
  project_name: '某医院治疗性单克隆抗体临床研究服务项目',
  hospital_name: '某医院',
  buyer_name: '某医院',
  department: null,
  product_categories: [],
  product_items: [],
  quality_flags: [],
}

const unrelated = minimalPrivateContextFromProfile(profile, unrelatedTherapeuticAntibody)
assert.equal(unrelated.context.matching_product_capabilities.length, 0)

console.log('Private profile IVD matching and grounded outreach: PASS')
