import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import {
  isWorkingDay,
  refreshLegalWindows,
  workingDaysRemaining,
} from '../api/_legalWindows.js'
import { runtimeRefreshSnapshotCard } from '../api/_runtimeOpportunityTime.js'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const snapshot = JSON.parse(readFileSync(resolve(scriptDir, '../public/data/today-actions.public.json'), 'utf8'))

// 1. The bundled snapshot must carry the calendar emitted by the Python builder.
const calendar = snapshot.working_calendar
assert(calendar && typeof calendar === 'object', 'snapshot must embed working_calendar')
assert.equal(calendar.legal_basis, 'MOF_ORDER_94')
assert.equal(calendar.challenge_working_days, 7)
assert.equal(calendar.complaint_working_days, 15)
assert(calendar.holidays.includes('2026-10-01'), '国庆 must be a holiday')
assert(calendar.adjusted_workdays.includes('2026-10-10'), '10-10 调休上班 must be an adjusted workday')

// 2. Same calendar semantics as medical_channel_pipeline/legal_windows.py (国办发明电〔2025〕7号).
assert.equal(isWorkingDay('2026-09-20', calendar), true)   // 周日调休上班
assert.equal(isWorkingDay('2026-09-25', calendar), false)  // 中秋
assert.equal(isWorkingDay('2026-10-07', calendar), false)  // 国庆末日
assert.equal(isWorkingDay('2026-10-08', calendar), true)
assert.equal(isWorkingDay('2026-10-11', calendar), false)  // 普通周日
assert.equal(isWorkingDay('2026-02-14', calendar), true)   // 春节调休上班

// 3. Remaining working days: identical figures to the Python unit tests.
assert.equal(workingDaysRemaining('2026-09-29', '2026-10-09', calendar), 4) // 9/29 9/30 10/8 10/9
assert.equal(workingDaysRemaining('2026-10-09', '2026-10-09', calendar), 1)
assert.equal(workingDaysRemaining('2026-10-10', '2026-10-09', calendar), 0)
assert.equal(workingDaysRemaining('2026-10-03', '2026-10-09', calendar), 2)
// Without a calendar we degrade to weekends-only and must never throw.
assert.equal(workingDaysRemaining('2026-09-29', '2026-10-09', null), 9)

// 4. Refresh only rewrites remaining/status; dates are preserved; input untouched.
const windows = [
  {
    code: 'DOCUMENT_CHALLENGE',
    anchor_kind: 'DOCUMENT_ACQUISITION_END',
    anchor_date: '2026-09-22',
    deadline_date: '2026-10-09',
    remaining_working_days: 7,
    status: 'OPEN',
  },
]
const frozen = structuredClone(windows)
const onLastDay = refreshLegalWindows(windows, Date.parse('2026-10-09T18:00:00+08:00'), calendar)
assert.equal(onLastDay[0].remaining_working_days, 1)
assert.equal(onLastDay[0].status, 'OPEN')
assert.equal(onLastDay[0].deadline_date, '2026-10-09')
const afterDeadline = refreshLegalWindows(windows, Date.parse('2026-10-10T00:01:00+08:00'), calendar)
assert.equal(afterDeadline[0].remaining_working_days, 0)
assert.equal(afterDeadline[0].status, 'CLOSED')
assert.deepEqual(windows, frozen, 'refresh must not mutate its input')
assert.equal(refreshLegalWindows(null, Date.now(), calendar), null)

// 5. End-to-end through the card refresher: facts untouched, legal_windows refreshed.
const card = {
  rank: 1,
  opportunity_id: 'legal_window_demo',
  facts: {
    lifecycle_state: 'BIDDING',
    notice_type: '公开招标公告',
    published_at: '2026-09-16',
    registration_deadline: '2026-09-22T16:30:00+08:00',
    registration_deadline_date: null,
    bid_deadline: '2026-10-10T09:00:00+08:00',
    quality_flags: [],
    verification_status: 'VERIFIED',
  },
  legal_windows: windows,
  priority: { score: 30, components: [] },
  recommendation_mode: 'LATE_WINDOW',
  model_decision_status: 'AWAITING_MODEL',
  model_block_reason: null,
  decision: null,
}
const factsBefore = structuredClone(card.facts)
const refreshedCard = runtimeRefreshSnapshotCard(card, Date.parse('2026-09-29T10:00:00+08:00'), calendar)
assert(refreshedCard)
assert.deepEqual(refreshedCard.facts, factsBefore, 'runtime evaluation must never rewrite verified public facts')
assert.equal(refreshedCard.legal_windows[0].remaining_working_days, 4)
assert.equal(refreshedCard.recommendation_mode, 'LATE_WINDOW')

// 6. Every bundled card with a window has a well-formed, compact payload.
const pool = Array.isArray(snapshot.opportunity_pool) ? snapshot.opportunity_pool : snapshot.cards
let withWindows = 0
for (const item of pool) {
  assert(!('legal_windows' in (item.facts || {})), `legal_windows must not live inside facts (${item.opportunity_id})`)
  if (item.legal_windows === null || item.legal_windows === undefined) continue
  assert(Array.isArray(item.legal_windows), `legal_windows must be an array (${item.opportunity_id})`)
  for (const window of item.legal_windows) {
    assert(['DOCUMENT_CHALLENGE', 'RESULT_CHALLENGE'].includes(window.code), window.code)
    assert(/^\d{4}-\d{2}-\d{2}$/.test(window.anchor_date))
    assert(/^\d{4}-\d{2}-\d{2}$/.test(window.deadline_date))
    assert(window.deadline_date > window.anchor_date, 'deadline must follow the anchor')
    assert(['OPEN', 'CLOSED'].includes(window.status))
    assert(Number.isInteger(window.remaining_working_days) && window.remaining_working_days >= 0)
  }
  withWindows += 1
}
assert(withWindows > 0, 'bundled snapshot should contain cards with legal windows')

console.log(`legal windows check passed (${withWindows}/${pool.length} cards carry windows)`)
