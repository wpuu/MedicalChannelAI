import scopeConfig from '../pipeline/data/medical_channel_scope.json' with { type: 'json' }

const TERMS = (scopeConfig.terms || []).map((item) => String(item).toLocaleLowerCase('zh-CN'))
const ACRONYMS = (scopeConfig.acronyms || []).map((item) => String(item).trim()).filter(Boolean)
const ACRONYM_RE = ACRONYMS.length
  ? new RegExp(`(?<![A-Za-z0-9])(?:${ACRONYMS.map((item) => item.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?![A-Za-z0-9])`, 'i')
  : null
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
  // buyer_name/hospital_name are intentionally excluded: a hospital buyer alone
  // must not make security, training or finance procurement a channel opportunity.
  return values.join('\n')
}

export function isMedicalChannelRelevantText(value) {
  const text = String(value || '').trim()
  if (!text) return false
  const folded = text.toLocaleLowerCase('zh-CN')
  if (TERMS.some((term) => folded.includes(term))) return true
  return Boolean(ACRONYM_RE && ACRONYM_RE.test(text))
}

export function isMedicalChannelRelevantCard(card) {
  const facts = card && typeof card === 'object' && !Array.isArray(card) ? card.facts : null
  return isMedicalChannelRelevantText(scopeTextFromFacts(facts))
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
