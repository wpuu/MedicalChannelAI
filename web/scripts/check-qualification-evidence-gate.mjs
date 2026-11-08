import assert from 'node:assert/strict'
import { evaluateQualificationEvidence as evaluate } from '../src/utils/qualificationEvidenceGate.js'

const AT = '2026-11-08T09:00:00+08:00'
const START = '2026-01-01T00:00:00+08:00'
const END = '2027-01-01T00:00:00+08:00'
const OFFICIAL_URL = 'https://official.example.test/tender/2026-a'
const officialRequirement = (id = 'R1') => ({
  id, hard: true, verified: true,
  source_url: OFFICIAL_URL, source_locator: '公告附件第3页/资格要求2',
  source_excerpt: '合成离线条件（非真实公告）：需对应主体的有效厂家授权',
  evidence_kind: 'MANUFACTURER_AUTHORIZATION',
  subject_key: 'dealer:agent-a',
  product_key: 'hematology:model-x',
})
const proof = (id = 'R1') => ({
  requirement_id: id, project_id: 'TJ-2026-A', package_id: 'PACKAGE-1',
  notice_version: 'v1', organization_id: 'org-A', user_id: 'user-A',
  evidence_kind: 'MANUFACTURER_AUTHORIZATION', subject_key: 'dealer:agent-a',
  product_key: 'hematology:model-x', consent_to_precheck: true,
  verified_by_human: true, checked_at: AT, valid_from: START, valid_until: END,
  finding: 'MATCH', secret_document_number: 'SECRET-CERT-DO-NOT-LEAK',
})
const complete = () => ({
  project_id: 'TJ-2026-A', package_id: 'PACKAGE-1', notice_version: 'v1',
  organization_id: 'org-A', user_id: 'user-A', as_of: AT,
  // Synthetic, independently attested official and customer fixtures only.
  official: {
    project_id: 'TJ-2026-A', package_id: 'PACKAGE-1',
    notice_version: 'v1', current_notice_version: 'v1',
    source_url: OFFICIAL_URL, verified_at: AT,
    source_verified: true, requirements_complete: true,
    attachments_complete: true, version_current_verified: true,
    requirements: [officialRequirement()],
  },
  customer: {
    organization_id: 'org-A', user_id: 'user-A', consent_to_precheck: true,
    proofs: [proof()],
  },
})
const copy = (v) => structuredClone(v)
let passed = 0
function test(label, input, status, indexStatus = null) {
  const before = JSON.stringify(input)
  const got = evaluate(input)
  assert.equal(got.status, status, label)
  assert.equal(got.final_qualification_confirmed, false, label)
  assert.ok(typeof got.label === 'string' && got.label.length > 0, label)
  assert.ok(Array.isArray(got.missing) && got.missing.length > 0, label)
  assert.ok(Array.isArray(got.items) && Array.isArray(got.risks), label)
  assert.ok(!JSON.stringify(got).includes('SECRET-CERT-DO-NOT-LEAK'), label + ' raw document leak')
  if (indexStatus) assert.equal(got.items[0]?.status, indexStatus, label)
  if (status === 'SATISFIED') {
    assert.ok(got.label.includes('非采购方资格确认'), label)
    assert.ok(got.missing.some((x) => x.includes('不能代表采购方最终资格审核')), label)
  }
  assert.equal(JSON.stringify(input), before, label + ' mutated input')
  passed += 1
}

// A03 contract Q01–Q15, only synthetic fixtures, not a live procurement result.
test('Q01 no official requirements input', null, 'UNKNOWN')
test('Q02 product scope and self-reported authorization alone', { match_status: 'IN_SCOPE', capability_type: 'DIRECT_AUTHORIZED', model_score: 99 }, 'UNKNOWN')
const incomplete = complete(); incomplete.official.requirements_complete = false
test('Q03 official conditions incomplete even with matching proof', incomplete, 'UNKNOWN')
const noDoc = complete(); noDoc.customer.proofs = []
test('Q04 official condition but customer proof absent', noDoc, 'UNKNOWN', 'UNKNOWN')
const unverified = complete(); unverified.customer.proofs[0].verified_by_human = false
test('Q05 self-report without independent verification', unverified, 'UNKNOWN', 'UNKNOWN')
const noAuthorization = complete()
noAuthorization.customer.proofs[0] = {
  ...proof(), finding: 'NOT_MET', no_valid_alternative_verified: true,
  confirmed_current: true,
}
test('Q06 verified missing mandatory manufacturer authorization with no alternative', noAuthorization, 'NOT_SATISFIED', 'NOT_SATISFIED')
const wrongPackageConfirmed = complete()
wrongPackageConfirmed.customer.proofs[0] = {
  ...proof(), finding: 'NOT_MET', no_valid_alternative_verified: true,
  confirmed_current: true,
}
test('Q07 independently verified no suitable proof for required package', wrongPackageConfirmed, 'NOT_SATISFIED')
const partial = complete()
partial.official.requirements.push(officialRequirement('R2'))
test('Q08 one matched of two mandatory rules', partial, 'UNKNOWN')
test('Q09 fully verified one rule and in-date proof', complete(), 'SATISFIED', 'SATISFIED')
const corrected = complete(); corrected.official.current_notice_version = 'v2'
test('Q10 corrected official version invalidates previous approval', corrected, 'UNKNOWN')
const conflicting = complete(); conflicting.customer.proofs.push({...proof(), finding:'NOT_MET', confirmed_current:true, no_valid_alternative_verified:true})
test('Q11 positive and explicit negative evidence conflict', conflicting, 'UNKNOWN', 'UNKNOWN')
const closedWindow = complete(); closedWindow.public_window = { registration_deadline: '2026-11-07T00:00:00+08:00' }
test('Q12 qualification is independent of expired registration window', closedWindow, 'SATISFIED')
const anotherOrg = complete(); anotherOrg.customer.proofs[0].organization_id = 'org-B'
test('Q13 other organization proof is not transferable', anotherOrg, 'UNKNOWN')
const procurementIntent = complete(); procurementIntent.official.attachments_complete = false
test('Q14 procurement intent without formal official terms', procurementIntent, 'UNKNOWN')
const licenseOnly = complete()
licenseOnly.official.requirements[0].evidence_kind = 'BUSINESS_LICENSE'
licenseOnly.customer.proofs[0].evidence_kind = 'BUSINESS_LICENSE'
test('Q15 no presumed manufacturer authorization if official never requires it', licenseOnly, 'SATISFIED')

const wrongUser = complete(); wrongUser.customer.proofs[0].user_id = 'user-B'
test('wrong user evidence never reused', wrongUser, 'UNKNOWN')
const wrongProject = complete(); wrongProject.customer.proofs[0].project_id = 'TJ-other'
test('wrong project evidence never reused', wrongProject, 'UNKNOWN')
const wrongNotice = complete(); wrongNotice.customer.proofs[0].notice_version = 'old-v0'
test('wrong official version evidence never reused', wrongNotice, 'UNKNOWN')
const wrongBrand = complete(); wrongBrand.customer.proofs[0].product_key = 'hematology:model-y'
test('wrong manufacturer/product model evidence not accepted', wrongBrand, 'UNKNOWN')
const expired = complete(); expired.customer.proofs[0].valid_until = '2026-11-07T00:00:00+08:00'
test('expired proof alone is unknown not noncompliant', expired, 'UNKNOWN')
const notYetValid = complete(); notYetValid.customer.proofs[0].valid_from = '2026-12-01T00:00:00+08:00'
test('future-start proof is not valid', notYetValid, 'UNKNOWN')
const unlicensedProof = complete(); unlicensedProof.customer.proofs[0].consent_to_precheck = false
test('proof without customer consent not reusable', unlicensedProof, 'UNKNOWN')
const noConsent = complete(); noConsent.customer.consent_to_precheck = false
test('account consent absent is unknown', noConsent, 'UNKNOWN')
const absentAlt = complete(); absentAlt.customer.proofs[0] = {...proof(), finding:'NOT_MET', confirmed_current:true, no_valid_alternative_verified:false}
test('negative without ruled-out alternatives is unknown', absentAlt, 'UNKNOWN')
const notCurrent = complete(); notCurrent.customer.proofs[0] = {...proof(), finding:'NOT_MET', confirmed_current:false, no_valid_alternative_verified:true}
test('unconfirmed current negative is unknown', notCurrent, 'UNKNOWN')
const officialUnknown = complete(); officialUnknown.official.source_verified = false
test('official verification absent', officialUnknown, 'UNKNOWN')
const missingLocator = complete(); missingLocator.official.requirements[0].source_locator = ''
test('official source locator missing', missingLocator, 'UNKNOWN')
const urlBad = complete(); urlBad.official.requirements[0].source_url = 'http://official.example.test/tender'
test('unsupported insecure official requirement URL', urlBad, 'UNKNOWN')
const duplicate = complete(); duplicate.official.requirements.push(officialRequirement('R1'))
test('duplicated official requirement id', duplicate, 'UNKNOWN')
const empty = complete(); empty.official.requirements = []
test('no mandatory terms cannot vacuously satisfy', empty, 'UNKNOWN')
const softOnly = complete(); softOnly.official.requirements[0].hard = false
test('no hard eligibility requirements cannot vacuously satisfy', softOnly, 'UNKNOWN')
const contradictoryStatus = complete(); contradictoryStatus.customer.proofs.push({...proof(), finding:'UNVERIFIED'})
test('unverified evidence conflict forces unknown', contradictoryStatus, 'UNKNOWN')
const partialOfficial = complete(); partialOfficial.official.attachments_complete = false
test('official attachments incomplete', partialOfficial, 'UNKNOWN')
const incompleteDate = complete(); incompleteDate.as_of = '2026-11-08'
test('timezone not specified on review date', incompleteDate, 'UNKNOWN')
const futureVerification = complete(); futureVerification.official.verified_at = '2027-01-01T00:00:00+08:00'
test('future official verification is unknown', futureVerification, 'UNKNOWN')
const safeMismatched = complete(); safeMismatched.customer.proofs[0].secret_document_number = 'SECOND_PRIVATE_IDENTIFIER'
assert.ok(!JSON.stringify(evaluate(safeMismatched)).includes('SECOND_PRIVATE_IDENTIFIER'))
passed += 1

console.log('PASS A04 offline qualification evidence synthetic checks: ' + passed + '/' + passed)
