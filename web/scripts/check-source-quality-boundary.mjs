import assert from 'node:assert/strict'
import {
  minimalPrivateContextFromProfile,
  privatePriorityPoints,
} from '../api/_privateProfileContext.js'

const emptyProfile = {
  relationships: [],
  targets: [],
  preferences: null,
}

const conflictedFacts = {
  project_name: '天津市职业病防治院采购X线移动业务用车项目',
  buyer_name: '天津市职业病防治院',
  hospital_name: '天津市职业病防治院',
  department: null,
  procurement_method: '公开招标',
  product_categories: ['医用磁共振设备'],
  product_items: [
    {
      raw_name: 'X线移动业务用车',
      category: '医用磁共振设备',
      specification: '详见附件',
    },
  ],
  quality_flags: ['SOURCE_CATEGORY_TITLE_CONFLICT'],
}

const mriProfile = {
  ...emptyProfile,
  capabilities: [{ keyword: 'MRI', capability_type: 'DIRECT', updated_at: null }],
}
const mriContext = minimalPrivateContextFromProfile(mriProfile, conflictedFacts)
assert.equal(
  mriContext.context.matching_product_capabilities.length,
  0,
  'source-conflicted MRI category must not create a private capability match',
)
assert.equal(
  privatePriorityPoints(mriContext.context, conflictedFacts).capability,
  0,
  'source-conflicted category must contribute zero private capability points',
)

const xrayProfile = {
  ...emptyProfile,
  capabilities: [{ keyword: 'X线', capability_type: 'DIRECT', updated_at: null }],
}
const xrayContext = minimalPrivateContextFromProfile(xrayProfile, conflictedFacts)
assert.equal(
  xrayContext.context.matching_product_capabilities.length,
  1,
  'verified project title/raw product text must remain usable after category suppression',
)
assert.equal(privatePriorityPoints(xrayContext.context, conflictedFacts).capability, 25)

const nonConflictedFacts = {
  ...conflictedFacts,
  quality_flags: [],
}
const normalMriContext = minimalPrivateContextFromProfile(mriProfile, nonConflictedFacts)
assert.equal(
  normalMriContext.context.matching_product_capabilities.length,
  1,
  'non-conflicted official categories must remain eligible for capability matching',
)

console.log('Source-quality matching boundary checks: PASS')
