import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import {
  runtimeRefreshSnapshotCard,
  runtimeRefreshSnapshotPool,
} from '../api/_runtimeOpportunityTime.js'

function component(code, points, maxPoints, basis = code) {
  return { code, points, max_points: maxPoints, basis, profile_paths: [], opportunity_paths: [] }
}

function baseCard() {
  return {
    rank: 1,
    opportunity_id: 'runtime_boundary_demo',
    facts: {
      project_number: 'XCSD-2026-A-641',
      project_name: '天津市胸科医院检验科设备租赁服务项目',
      buyer_name: '天津市胸科医院',
      hospital_name: '天津市胸科医院',
      department: '检验科',
      region: '天津市',
      lifecycle_state: 'BIDDING',
      notice_type: '公开招标公告',
      published_at: '2026-08-27',
      registration_deadline: '2026-09-03T16:00:00+08:00',
      registration_deadline_date: null,
      bid_deadline: '2026-09-17T09:30:00+08:00',
      budget: { amount_cny: 5730000, currency: 'CNY' },
      quality_flags: [],
      verification_status: 'VERIFIED',
    },
    evidence_source_urls: ['https://www.ccgp.gov.cn/example'],
    priority: {
      score: 58,
      components: [
        component('PRODUCT_EXECUTION_CAPABILITY', 0, 25),
        component('RELATIONSHIP', 0, 10),
        component('EXECUTION_FLEXIBILITY', 0, 5),
        component('INTERVENTION_STAGE', 25, 25, 'PUBLIC_OPPORTUNITY'),
        component('DEADLINE_URGENCY', 10, 10, 'NEXT_ACTIONABLE_DEADLINE'),
        component('PROJECT_AMOUNT', 10, 10),
        component('PRODUCT_SPECIFICITY', 8, 8),
        component('PUBLICATION_FRESHNESS', 5, 7),
      ],
      warnings: ['ZERO_CONFIG_PUBLIC_FACTS_ONLY'],
    },
    match_status: 'MATCHED_CANDIDATE',
    recommendation_mode: 'PUBLIC_OPPORTUNITY',
    model_decision_status: 'AWAITING_MODEL',
    model_block_reason: null,
    decision: null,
  }
}

function points(card, code) {
  return card.priority.components.find((item) => item.code === code)?.points
}

const beforeDeadline = Date.parse('2026-09-03T15:00:00+08:00')
const afterRegistration = Date.parse('2026-09-03T16:54:00+08:00')
const afterBid = Date.parse('2026-09-17T09:31:00+08:00')

const original = baseCard()
const originalFacts = structuredClone(original.facts)
const before = runtimeRefreshSnapshotCard(original, beforeDeadline)
assert(before)
assert.equal(before.recommendation_mode, 'PUBLIC_OPPORTUNITY')
assert.equal(before.priority.score, 58)
assert.equal(points(before, 'INTERVENTION_STAGE'), 25)
assert.equal(points(before, 'DEADLINE_URGENCY'), 10)

const late = runtimeRefreshSnapshotCard(original, afterRegistration)
assert(late)
assert.deepEqual(late.facts, originalFacts, 'runtime evaluation must never rewrite verified public facts')
assert.equal(late.recommendation_mode, 'LATE_WINDOW')
assert.equal(points(late, 'INTERVENTION_STAGE'), 8)
assert.equal(points(late, 'DEADLINE_URGENCY'), 5)
assert.equal(late.priority.score, 36)
assert.equal(late.model_decision_status, 'AWAITING_MODEL')
assert.equal(late.decision, null)
assert.equal(runtimeRefreshSnapshotCard(original, afterBid), null)

const dateOnly = baseCard()
dateOnly.opportunity_id = 'date_only'
dateOnly.facts.registration_deadline = null
dateOnly.facts.registration_deadline_date = '2026-09-03'
dateOnly.facts.bid_deadline = null
assert(runtimeRefreshSnapshotCard(dateOnly, Date.parse('2026-09-03T23:00:00+08:00')))
assert.equal(runtimeRefreshSnapshotCard(dateOnly, Date.parse('2026-09-04T00:01:00+08:00')), null)

const relative = baseCard()
relative.opportunity_id = 'relative_window'
relative.facts.published_at = '2026-06-11'
relative.facts.registration_deadline = null
relative.facts.registration_deadline_date = null
relative.facts.bid_deadline = null
relative.facts.quality_flags = ['RELATIVE_REGISTRATION_WINDOW_7_DAYS']
assert(runtimeRefreshSnapshotCard(relative, Date.parse('2026-06-18T22:00:00+08:00')))
assert.equal(runtimeRefreshSnapshotCard(relative, Date.parse('2026-06-19T00:01:00+08:00')), null)

const alternative = baseCard()
alternative.opportunity_id = 'still_actionable'
alternative.rank = 2
alternative.priority.score = 40
alternative.facts.published_at = '2026-09-02'
alternative.facts.registration_deadline = '2026-09-10T17:00:00+08:00'
alternative.facts.bid_deadline = '2026-09-20T10:00:00+08:00'
alternative.priority.components = [
  component('PRODUCT_EXECUTION_CAPABILITY', 0, 25),
  component('RELATIONSHIP', 0, 10),
  component('EXECUTION_FLEXIBILITY', 0, 5),
  component('INTERVENTION_STAGE', 25, 25, 'PUBLIC_OPPORTUNITY'),
  component('DEADLINE_URGENCY', 7, 10, 'NEXT_ACTIONABLE_DEADLINE'),
  component('PROJECT_AMOUNT', 2, 10),
  component('PRODUCT_SPECIFICITY', 0, 8),
  component('PUBLICATION_FRESHNESS', 6, 7),
]
const reranked = runtimeRefreshSnapshotPool([original, alternative], afterRegistration)
assert.equal(reranked[0].opportunity_id, 'still_actionable')
assert.equal(reranked[0].rank, 1)
assert.equal(reranked[1].opportunity_id, 'runtime_boundary_demo')
assert.equal(reranked[1].rank, 2)

const scriptDir = dirname(fileURLToPath(import.meta.url))
const staticService = readFileSync(resolve(scriptDir, '../src/services/StaticSnapshotTodayActionsService.ts'), 'utf8')
assert(staticService.includes('applyRuntimeActionability('), 'verified trial must keep runtime deadline handling')
assert(staticService.includes('LATE_WINDOW_POINTS = 8'), 'trial and API must share the same late-window intervention points')

console.log('Runtime opportunity time boundary: PASS')
