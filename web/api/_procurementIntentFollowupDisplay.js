function hasExplicitUserHandling(card) {
  if (!card || typeof card !== 'object' || Array.isArray(card)) return false
  const status = typeof card.followup_status === 'string' ? card.followup_status.trim() : ''
  return Boolean((status && status !== 'NEW') || card.remind_at)
}

export function countFormalCandidatesNeedingAction(cards, pairs) {
  const cardsById = new Map(
    (Array.isArray(cards) ? cards : [])
      .filter((card) => card && typeof card === 'object' && !Array.isArray(card))
      .map((card) => [String(card.opportunity_id || ''), card]),
  )
  const pendingCandidateIds = new Set()
  for (const pair of Array.isArray(pairs) ? pairs : []) {
    const candidateId = String(pair?.candidate_opportunity_id || '')
    if (!candidateId) continue
    if (!hasExplicitUserHandling(cardsById.get(candidateId))) {
      pendingCandidateIds.add(candidateId)
    }
  }
  return pendingCandidateIds.size
}
