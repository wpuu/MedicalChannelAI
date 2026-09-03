import assert from 'node:assert/strict'
import { minimalPrivateContextFromProfile } from '../api/_privateProfileContext.js'

const profile = {
  capabilities: [
    {
      keyword: 'IVD',
      capability_type: 'DIRECT_UNCONFIRMED',
      updated_at: '2026-09-03T00:00:00.000Z',
    },
  ],
  relationships: [],
  targets: [],
  preferences: null,
}

const igmQualityControl = {
  project_name: '天津市第一中心医院甲型肝炎病毒IgM抗体质控品等采购项目院内比选公告',
  hospital_name: '天津市第一中心医院',
  buyer_name: '天津市第一中心医院',
  department: null,
  product_categories: [],
  product_items: [],
  quality_flags: [],
}

const matched = minimalPrivateContextFromProfile(profile, igmQualityControl)
assert.equal(matched.context.matching_product_capabilities.length, 1)
assert.equal(matched.context.matching_product_capabilities[0].category, 'IVD')
assert.equal(matched.context.matching_product_capabilities[0].capability_type, 'DIRECT_UNCONFIRMED')

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

console.log('Private profile IVD capability matching: PASS')
