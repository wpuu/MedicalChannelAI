import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  procurementIntentFollowupSummary,
  procurementIntentSuccessorPairs,
} from '../api/_procurementIntentFollowup.js'
import { countFormalCandidatesNeedingAction } from '../api/_procurementIntentFollowupDisplay.js'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const dataDir = resolve(scriptDir, '../pipeline/data')

function load(name) {
  return JSON.parse(readFileSync(resolve(dataDir, name), 'utf8'))
}

function byId(records, id) {
  const record = records.find((item) => item?.opportunity_id === id)
  if (!record) throw new Error(`VERIFIED_LINEAGE_RECORD_MISSING:${id}`)
  return record
}

const intents = load('tianjin_live_tjzyefy_intent_records.json')
const ccgp = load('tianjin_live_ccgp_records.json')
const intent = byId(intents, 'tjzyefy_intent_20260804_030195986')
const formal = byId(ccgp, 'ccgp_bf77073fba23504b')

if (intent.source?.url !== 'https://www.tjzyefy.com/system/2026/08/04/030195986.shtml') {
  throw new Error('REAL_INTENT_OFFICIAL_SOURCE_CHANGED')
}
if (formal.source?.url !== 'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260902_27255226.htm') {
  throw new Error('REAL_FORMAL_OFFICIAL_SOURCE_CHANGED')
}
if (formal.facts?.registration_deadline !== '2026-09-09T17:00:00+08:00') {
  throw new Error('REAL_FORMAL_REGISTRATION_DEADLINE_CHANGED')
}
if (formal.facts?.bid_deadline !== '2026-09-23T08:30:00+08:00') {
  throw new Error('REAL_FORMAL_BID_DEADLINE_CHANGED')
}
if ((formal.facts?.product_items ?? []).length !== 0) {
  throw new Error('REAL_FORMAL_EXPECTED_EMPTY_PRODUCT_ITEMS')
}

const pairs = procurementIntentSuccessorPairs([intent, formal])
if (
  pairs.length !== 1 ||
  pairs[0].intent_opportunity_id !== intent.opportunity_id ||
  pairs[0].candidate_opportunity_id !== formal.opportunity_id
) {
  throw new Error(`REAL_PROCUREMENT_INTENT_SUCCESSOR_NOT_LINKED:${JSON.stringify(pairs)}`)
}

const summary = procurementIntentFollowupSummary([intent, formal])
if (
  summary.intent_count !== 1 ||
  summary.intents_with_formal_successor !== 1 ||
  summary.candidate_pair_count !== 1
) {
  throw new Error(`PROCUREMENT_INTENT_SUMMARY_INVALID:${JSON.stringify(summary)}`)
}

const newCandidate = { ...formal, followup_status: 'NEW', remind_at: null }
if (countFormalCandidatesNeedingAction([intent, newCandidate], pairs) !== 1) {
  throw new Error('NEW_FORMAL_CANDIDATE_SHOULD_NEED_ACTION')
}

const followedCandidate = { ...formal, followup_status: 'REVIEWING', remind_at: null }
if (countFormalCandidatesNeedingAction([intent, followedCandidate], pairs) !== 0) {
  throw new Error('FOLLOWED_FORMAL_CANDIDATE_SHOULD_NOT_REPEAT_NUDGE')
}

const scheduledCandidate = {
  ...formal,
  followup_status: 'NEW',
  remind_at: '2026-09-08T09:00:00+08:00',
}
if (countFormalCandidatesNeedingAction([intent, scheduledCandidate], pairs) !== 0) {
  throw new Error('SCHEDULED_FORMAL_CANDIDATE_SHOULD_NOT_REPEAT_NUDGE')
}

const summaryAfterPrivateHandling = procurementIntentFollowupSummary([intent, followedCandidate])
if (JSON.stringify(summaryAfterPrivateHandling) !== JSON.stringify(summary)) {
  throw new Error('PRIVATE_HANDLING_MUST_NOT_CHANGE_PUBLIC_LINEAGE_SUMMARY')
}

console.log('Procurement intent followup summary: PASS')