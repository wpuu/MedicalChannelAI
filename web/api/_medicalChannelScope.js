import scopeConfig from '../pipeline/data/medical_channel_scope.json' with { type: 'json' }

const TERMS = (scopeConfig.terms || []).map((item) => String(item).toLocaleLowerCase('zh-CN'))
const CONTEXTUAL_TERMS = (scopeConfig.contextual_terms || []).map((item) => String(item).toLocaleLowerCase('zh-CN'))
const ADJACENT_TECH_TERMS = (scopeConfig.adjacent_tech_terms || []).map((item) => String(item).toLocaleLowerCase('zh-CN'))
const MEDICAL_CONTEXT_TERMS = (scopeConfig.medical_context_terms || []).map((item) => String(item).toLocaleLowerCase('zh-CN'))
const GENERIC_EXCLUSIONS = (scopeConfig.generic_exclusion_terms || []).map((item) => String(item).toLocaleLowerCase('zh-CN'))
const ACRONYMS = (scopeConfig.acronyms || []).map((item) => String(item).trim()).filter(Boolean)
const CONTEXTUAL_ACRONYMS = (scopeConfig.contextual_acronyms || []).map((item) => String(item).trim()).filter(Boolean)
const ADJACENT_TECH_ACRONYMS = (scopeConfig.adjacent_tech_acronyms || []).map((item) => String(item).trim()).filter(Boolean)

function acronymRegex(items) {
  return items.length
    ? new RegExp(`(?<![A-Za-z0-9])(?:${items.map((item) => item.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?![A-Za-z0-9])`, 'i')
    : null
}

const ACRONYM_RE = acronymRegex(ACRONYMS)
const CONTEXTUAL_ACRONYM_RE = acronymRegex(CONTEXTUAL_ACRONYMS)
const ADJACENT_TECH_ACRONYM_RE = acronymRegex(ADJACENT_TECH_ACRONYMS)
const MAX_TODAY_CARDS = 5

function scopeTextFromFacts(facts) {
  if (!facts || typeof facts !== 'object') return ''
  const values = []
  for (const key of ['project_name', 'department']) {
    const value = facts[key]
    if (typeof value === 'string' && value.trim()) values.push(value.trim())
  }
  for (const value of facts.product_categories || []) {
    if (typeof value === 'string' && value.trim()) values.push(value.trim())
  }
  for (const item of facts.product_items || []) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    for (const key of ['raw_name', 'name', 'category', 'specification']) {
      const value = item[key]
      if (typeof value === 'string' && value.trim()) values.push(value.trim())
    }
  }
  return values.join('\n')
}

function contextTextFromFacts(facts) {
  if (!facts || typeof facts !== 'object') return ''
  const values = [scopeTextFromFacts(facts)]
  // Buyer/hospital identity is context only. It cannot independently make an
  // administrative procurement a MedicalChannelAI opportunity.
  for (const key of ['buyer_name', 'hospital_name']) {
    const value = facts[key]
    if (typeof value === 'string' && value.trim()) values.push(value.trim())
  }
  return values.filter(Boolean).join('\n')
}

function hasStrongSignal(text) {
  const folded = text.toLocaleLowerCase('zh-CN')
  if (TERMS.some((term) => folded.includes(term))) return true
  return Boolean(ACRONYM_RE && ACRONYM_RE.test(text))
}

function hasContextualSignal(text) {
  const folded = text.toLocaleLowerCase('zh-CN')
  if (CONTEXTUAL_TERMS.some((term) => folded.includes(term))) return true
  return Boolean(CONTEXTUAL_ACRONYM_RE && CONTEXTUAL_ACRONYM_RE.test(text))
}

function hasAdjacentTechSignal(text) {
  const folded = text.toLocaleLowerCase('zh-CN')
  if (ADJACENT_TECH_TERMS.some((term) => folded.includes(term))) return true
  return Boolean(ADJACENT_TECH_ACRONYM_RE && ADJACENT_TECH_ACRONYM_RE.test(text))
}

function hasMedicalContext(text) {
  const folded = text.toLocaleLowerCase('zh-CN')
  return MEDICAL_CONTEXT_TERMS.some((term) => folded.includes(term))
}

function hasGenericExclusion(text) {
  const folded = text.toLocaleLowerCase('zh-CN')
  return GENERIC_EXCLUSIONS.some((term) => folded.includes(term))
}

export function isMedicalChannelRelevantText(value) {
  const text = String(value || '').trim()
  if (!text) return false
  if (hasStrongSignal(text)) return true
  if (hasGenericExclusion(text)) return false
  if (hasAdjacentTechSignal(text)) return hasMedicalContext(text)
  return hasContextualSignal(text) && hasMedicalContext(text)
}

export function isMedicalChannelRelevantCard(card) {
  const facts = card && typeof card === 'object' && !Array.isArray(card) ? card.facts : null
  if (!facts || typeof facts !== 'object') return false
  const scopeText = scopeTextFromFacts(facts)
  if (hasStrongSignal(scopeText)) return true
  if (hasGenericExclusion(scopeText)) return false
  if (hasAdjacentTechSignal(scopeText)) return hasMedicalContext(scopeText)
  return hasContextualSignal(scopeText) && hasMedicalContext(contextTextFromFacts(facts))
}

export function filterSnapshotToMedicalChannel(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return snapshot
  const pool = snapshot.opportunity_pool
  if (Array.isArray(pool)) {
    const scopedPool = pool
      .filter(isMedicalChannelRelevantCard)
      .map((card, index) => ({ ...card, rank: index + 1 }))
    const cards = scopedPool.slice(0, MAX_TODAY_CARDS)
    return {
      ...snapshot,
      matched_count: scopedPool.length,
      card_count: cards.length,
      opportunity_pool_count: scopedPool.length,
      cards,
      opportunity_pool: scopedPool,
    }
  }

  if (Array.isArray(snapshot.cards)) {
    const cards = snapshot.cards
      .filter(isMedicalChannelRelevantCard)
      .slice(0, MAX_TODAY_CARDS)
      .map((card, index) => ({ ...card, rank: index + 1 }))
    return { ...snapshot, matched_count: cards.length, card_count: cards.length, cards }
  }
  return snapshot
}
