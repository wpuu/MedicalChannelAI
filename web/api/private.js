import privateCoreHandler from './_privateCore.js'
import {
  procurementIntentFollowupSummary,
  procurementIntentSuccessorPairs,
} from './_procurementIntentFollowup.js'
import { countFormalCandidatesNeedingAction } from './_procurementIntentFollowupDisplay.js'

function firstQuery(request, key) {
  const raw = request.query?.[key]
  return Array.isArray(raw) ? raw[0] : raw
}

function shouldProjectLightToday(request) {
  if (request.method !== 'GET') return false
  if (firstQuery(request, 'route') !== 'today') return false
  return firstQuery(request, 'include_pool') !== '1'
}

function projectLightTodayPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload
  if (payload.mode !== 'TODAY_ACTIONS') return payload
  if (!Object.prototype.hasOwnProperty.call(payload, 'opportunity_pool')) return payload
  const { opportunity_pool: fullPool, ...lightPayload } = payload
  const pairs = procurementIntentSuccessorPairs(fullPool)
  const projected = {
    ...lightPayload,
    procurement_intent_followup_summary: procurementIntentFollowupSummary(fullPool),
  }
  // Account-private display state only. It suppresses repeated homepage nudges
  // after an explicit follow-up decision, but never changes public lineage.
  projected.procurement_intent_followup_summary.formal_candidates_needing_action =
    countFormalCandidatesNeedingAction(fullPool, pairs)
  return projected
}

export default async function handler(request, response) {
  if (!shouldProjectLightToday(request) || typeof response.json !== 'function') {
    return privateCoreHandler(request, response)
  }

  const originalJson = response.json
  response.json = function projectedJson(payload) {
    return originalJson.call(this, projectLightTodayPayload(payload))
  }
  try {
    return await privateCoreHandler(request, response)
  } finally {
    response.json = originalJson
  }
}