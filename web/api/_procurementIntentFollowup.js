const PROCUREMENT_INTENT = 'PROCUREMENT_INTENT'
const PRE_MARKET_SIGNAL = 'PRE_MARKET_SIGNAL'

const GENERIC_PRODUCT_TERMS = new Set([
  '医疗设备',
  '医疗器械',
  '设备',
  '耗材',
  '试剂',
  '服务',
  '采购项目',
  '设备采购项目',
  '医疗设备采购项目',
  '医疗器械采购项目',
])

const GENERIC_PROJECT_SUBJECTS = new Set([
  '采购项目',
  '医疗设备采购项目',
  '医疗器械采购项目',
  '设备采购项目',
  '服务项目',
])

function normalizeText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[\s·•,，。；;：:、()（）【】\[\]《》<>“”"'\/\\_-]+/g, '')
}

function factsOf(card) {
  return card && typeof card === 'object' && !Array.isArray(card) && card.facts && typeof card.facts === 'object'
    ? card.facts
    : {}
}

function institutionKey(card) {
  const facts = factsOf(card)
  return normalizeText(facts.hospital_name ?? facts.buyer_name)
}

function productTerms(card) {
  const facts = factsOf(card)
  const institution = institutionKey(card)
  const values = []
  if (Array.isArray(facts.product_categories)) values.push(...facts.product_categories)
  if (Array.isArray(facts.product_items)) {
    for (const item of facts.product_items) {
      if (typeof item === 'string') {
        values.push(item)
        continue
      }
      if (!item || typeof item !== 'object' || Array.isArray(item)) continue
      values.push(
        item.raw_name ?? item.product_name ?? item.name ?? item.item_name,
        item.category ?? item.product_category,
      )
    }
  }

  const result = new Set()
  for (const value of values) {
    let term = normalizeText(value)
    if (!term) continue
    if (institution && term.includes(institution)) term = term.replace(institution, '')
    if (term.length < 2 || GENERIC_PRODUCT_TERMS.has(term)) continue
    result.add(term)
  }
  return [...result]
}

function projectSubject(card) {
  const facts = factsOf(card)
  const institution = institutionKey(card)
  let subject = normalizeText(facts.project_name)
  if (!subject) return null
  if (institution && subject.includes(institution)) subject = subject.replace(institution, '')
  subject = subject.replace(/^采购意向公告(?:20\d{2}年)?第?\d+号?/, '')
  if (subject.length < 6 || GENERIC_PROJECT_SUBJECTS.has(subject)) return null
  return subject
}

function publicationTime(card) {
  const raw = factsOf(card).published_at
  if (!raw) return null
  const parsed = Date.parse(raw)
  return Number.isNaN(parsed) ? null : parsed
}

function isProcurementIntent(card) {
  return factsOf(card).lifecycle_state === PROCUREMENT_INTENT
}

function isPreMarket(card) {
  return isProcurementIntent(card) || card?.recommendation_mode === PRE_MARKET_SIGNAL
}

function matchedTerms(left, right) {
  const leftTerms = productTerms(left)
  const rightTerms = productTerms(right)
  const matches = new Set()
  for (const leftTerm of leftTerms) {
    for (const rightTerm of rightTerms) {
      const exact = leftTerm === rightTerm
      const contained =
        Math.min(leftTerm.length, rightTerm.length) >= 4 &&
        (leftTerm.includes(rightTerm) || rightTerm.includes(leftTerm))
      if (exact || contained) matches.add(leftTerm.length <= rightTerm.length ? leftTerm : rightTerm)
    }
  }
  return [...matches]
}

function hasConservativeSuccessorEvidence(intent, candidate) {
  const terms = matchedTerms(intent, candidate)
  if (terms.length > 0) return true
  const intentSubject = projectSubject(intent)
  const candidateSubject = projectSubject(candidate)
  return Boolean(intentSubject && candidateSubject && intentSubject === candidateSubject)
}

export function procurementIntentSuccessorPairs(cards) {
  if (!Array.isArray(cards) || cards.length === 0) return []

  const formalByInstitution = new Map()
  for (const card of cards) {
    if (isPreMarket(card)) continue
    const institution = institutionKey(card)
    const published = publicationTime(card)
    if (!institution || published === null) continue
    const list = formalByInstitution.get(institution) ?? []
    list.push({ card, published })
    formalByInstitution.set(institution, list)
  }

  const pairs = []
  for (const intent of cards) {
    if (!isProcurementIntent(intent)) continue
    const institution = institutionKey(intent)
    const intentPublished = publicationTime(intent)
    if (!institution || intentPublished === null) continue
    for (const candidate of formalByInstitution.get(institution) ?? []) {
      if (candidate.published < intentPublished) continue
      if (!hasConservativeSuccessorEvidence(intent, candidate.card)) continue
      pairs.push({
        intent_opportunity_id: String(intent.opportunity_id || ''),
        candidate_opportunity_id: String(candidate.card.opportunity_id || ''),
      })
    }
  }
  return pairs
}

export function procurementIntentFollowupSummary(cards) {
  const list = Array.isArray(cards) ? cards : []
  const intentCount = list.filter(isProcurementIntent).length
  const pairs = procurementIntentSuccessorPairs(list)
  const intentsWithFormalSuccessor = new Set(
    pairs.map((pair) => pair.intent_opportunity_id).filter(Boolean),
  ).size
  return {
    intent_count: intentCount,
    intents_with_formal_successor: intentsWithFormalSuccessor,
    candidate_pair_count: pairs.length,
  }
}
