import privateCoreHandler from './_privateCore.js'
import {
  procurementIntentFollowupSummary,
  procurementIntentSuccessorPairs,
} from './_procurementIntentFollowup.js'

function firstQuery(request, key) {
  const raw = request.query?.[key]
  return Array.isArray(raw) ? raw[0] : raw
}

function shouldProjectLightToday(request) {
  if (request.method !== 'GET') return false
  if (firstQuery(request, 'route') !== 'today') return false
  return firstQuery(request, 'include_pool') !== '1'
}

function hasExplicitUserHandling(card) {
  if (!card || typeof card !== 'object' || Array.isArray(card)) return false
  const status = typeof card.followup_status === 'string' ? card.followup_status.trim() : ''
  return Boolean((status && status !== 'NEW') || card.remind_at)
}

function procurementIntentDisplaySummary(fullPool) {
  const publicSummary = procurementIntentFollowupSummary(fullPool)
  const pairs = procurementIntentSuccessorPairs(fullPool)
  const cardsById = new Map(
    (Array.isArray(fullPool) ? fullPool : [])
      .filter((card) => card && typeof card === 'object' && !Array.isArray(card))
      .map((card) => [String(card.opportunity_id || ''), card]),
  )
  const formalCandidatesNeedingAction = new Set()
  for (const pair of pairs) {
    const candidateId = String(pair.candidate_opportunity_id || '')
    if (!candidateId) continue
    if (!hasExplicitUserHandling(cardsById.get(candidateId))) {
      formalCandidatesNeedingAction.add(candidateId)
    }
  }
  return {
    ...publicSummary,
    // Account-private display state only. It suppresses repeated homepage nudges
    // after an explicit follow-up decision, but never changes public lineage.
    formal_candidates_needing_action: formalCandidatesNeedingAction.size,
  }
}

function projectLightTodayPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload
  if (payload.mode !== 'TODAY_ACTIONS') return payload
  if (!Object.prototype.hasOwnProperty.call(payload, 'opportunity_pool')) return payload
  const { opportunity_pool: fullPool, ...lightPayload } = payload
  return {
    ...lightPayload,
    procurement_intent_followup_summary: procurementIntentDisplaySummary(fullPool),
  }
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