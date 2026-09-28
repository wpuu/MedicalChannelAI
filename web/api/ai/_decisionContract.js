const RELATIVE_WINDOW_FLAG = 'RELATIVE_REGISTRATION_WINDOW_7_DAYS'

export const ACTION_LABELS = Object.freeze({
  REVIEW_OFFICIAL_SOURCE: '核对已核验官方来源和可获取的官方文件',
  VERIFY_REQUIREMENTS: '核实技术要求、资格条件和提交方式',
  CONTACT_PUBLIC_CONTACT: '使用公告公开联系方式核实公开要求',
  PREPARE_REQUIRED_MATERIALS: '按官方要求准备当前阶段所需材料',
  CONFIRM_RELATIVE_WINDOW: '向官方确认相对报名或资料提交窗口是否仍开放',
  CHECK_LATE_WINDOW_OPTIONS: '核实报名窗口结束后的公开后续路径',
  MATCH_CONFIRMED_RESOURCES: '仅按当前账号已确认资源核对执行条件',
})

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function text(value, max = 600) {
  if (value === null || value === undefined) return null
  const result = String(value).trim()
  return result ? result.slice(0, max) : null
}

function invalid(code) {
  const error = new Error(code)
  error.code = 'AI_RESPONSE_INVALID'
  return error
}

function hasRelativeRegistrationWindow(facts) {
  return Array.isArray(facts?.quality_flags) && facts.quality_flags.includes(RELATIVE_WINDOW_FLAG)
}

function hasPublicContact(facts) {
  const contact = asObject(facts?.official_contact)
  return Boolean(text(contact?.name, 150) || text(contact?.phone, 100) || text(contact?.email, 200))
}

function hasConfirmedExecutionContext(context) {
  const root = asObject(context)
  if (!root) return false
  const relationship = asObject(root.hospital_relationship)
  if (
    relationship &&
    [relationship.hospital, relationship.department, relationship.relationship_strength].some((value) => text(value, 300))
  ) {
    return true
  }
  if (Array.isArray(root.matching_product_capabilities) && root.matching_product_capabilities.length > 0) return true
  const policy = asObject(root.partnering_policy)
  return Boolean(policy && Object.values(policy).some((value) => value === true))
}

function allowedActionCodes(facts, evidenceUrls, customerContext, windowStatus) {
  const allowed = new Set(['VERIFY_REQUIREMENTS'])
  if (Array.isArray(evidenceUrls) && evidenceUrls.some((url) => /^https:\/\//i.test(String(url || '')))) {
    allowed.add('REVIEW_OFFICIAL_SOURCE')
  }
  if (hasPublicContact(facts)) allowed.add('CONTACT_PUBLIC_CONTACT')
  if (windowStatus === 'OPEN' || windowStatus === 'RELATIVE_WINDOW') {
    allowed.add('PREPARE_REQUIRED_MATERIALS')
  }
  if (windowStatus === 'RELATIVE_WINDOW' && hasRelativeRegistrationWindow(facts)) {
    allowed.add('CONFIRM_RELATIVE_WINDOW')
  }
  if (windowStatus === 'LATE_WINDOW') allowed.add('CHECK_LATE_WINDOW_OPTIONS')
  if (hasConfirmedExecutionContext(customerContext)) allowed.add('MATCH_CONFIRMED_RESOURCES')
  return allowed
}

function dateTimeText(value) {
  const raw = text(value, 100)
  if (!raw) return null
  const match = raw.match(/^(20\d{2})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (!match) return raw
  return `${match[1]}年${Number(match[2])}月${Number(match[3])}日 ${match[4]}:${match[5]}`
}

function dateOnlyText(value) {
  const raw = text(value, 20)
  if (!raw) return null
  const match = raw.match(/^(20\d{2})-(\d{2})-(\d{2})$/)
  if (!match) return raw
  return `${match[1]}年${Number(match[2])}月${Number(match[3])}日`
}

function budgetText(value) {
  const amount = typeof value === 'number' && Number.isFinite(value) ? value : null
  if (amount === null || amount <= 0) return null
  if (amount < 10_000) return `${Math.round(amount)}元`
  const wan = amount / 10_000
  const decimals = Number.isInteger(wan) ? 0 : wan < 10 ? 2 : 1
  return `${Number(wan.toFixed(decimals))}万元`
}

function publicContactText(facts) {
  const contact = asObject(facts?.official_contact)
  if (!contact) return null
  const name = text(contact.name, 150)
  const phone = text(contact.phone, 100)
  const email = text(contact.email, 200)
  const details = [name, phone, email].filter(Boolean)
  return details.length ? details.join(' / ') : null
}

function renderAction(code, facts) {
  if (code === 'REVIEW_OFFICIAL_SOURCE') {
    return '今天先打开已核验官方来源，核对项目原文以及其中可获取的官方文件。'
  }
  if (code === 'VERIFY_REQUIREMENTS') {
    return '核实技术要求、资格条件和提交方式；未核实前不补全参数，也不作产品、资质或投标承诺。'
  }
  if (code === 'CONTACT_PUBLIC_CONTACT') {
    const contact = publicContactText(facts)
    return contact
      ? `按公告公开联系方式联系 ${contact}，只核实文件获取、技术要求、资格条件和当前公开窗口，并只记录对方明确回复。`
      : '按公告公开联系方式联系公开联系人，核实公开要求，并只记录对方明确回复。'
  }
  if (code === 'PREPARE_REQUIRED_MATERIALS') {
    return '按官方文件整理当前阶段需要的资质、技术和商务材料；具体材料清单以官方要求为准。'
  }
  if (code === 'CONFIRM_RELATIVE_WINDOW') {
    return '先向官方确认相对报名或资料提交窗口是否仍开放，不把系统内部推算日期当作官方截止事实。'
  }
  if (code === 'CHECK_LATE_WINDOW_OPTIONS') {
    return '报名或文件获取窗口已结束，先核实公告允许的后续答疑、投标或资料对接路径。'
  }
  if (code === 'MATCH_CONFIRMED_RESOURCES') {
    return '仅依据当前账号已确认的关系和产品能力核对可执行资源，不把重点关注对象当作已有关系。'
  }
  throw invalid('AI_DECISION_ACTION_CODE_UNKNOWN')
}

function renderWindowReason(facts, windowStatus) {
  const registration = dateTimeText(facts?.registration_deadline)
  const registrationDate = dateOnlyText(facts?.registration_deadline_date)
  const bid = dateTimeText(facts?.bid_deadline)
  if (windowStatus === 'RELATIVE_WINDOW') {
    return hasRelativeRegistrationWindow(facts)
      ? '官方原文只给出“自公告发布之日起7天”的相对窗口，未提供精确截止日期或时刻。'
      : '当前窗口需要继续按官方原文人工核实。'
  }
  if (windowStatus === 'LATE_WINDOW') {
    return bid
      ? `已核验报名或文件获取窗口已经结束，但投标/响应截止时间 ${bid} 尚未到。`
      : '已核验报名或文件获取窗口已经结束，后续动作需按官方原文人工核实。'
  }
  if (registration) return `已核验报名或文件获取截止时间为 ${registration}，当前窗口仍开放。`
  if (registrationDate) return `已核验报名或文件获取截止日期为 ${registrationDate}；官方未提供具体时刻，当前日期尚未超过该日。`
  if (bid) return `已核验投标/响应截止时间为 ${bid}，当前窗口尚未关闭。`
  return '根据已核验公开时间字段，当前机会尚未被系统判定为关闭。'
}

function renderReasons(facts, windowStatus, actionCodes) {
  const reasons = []
  const projectName = text(facts?.project_name, 500)
  if (projectName) reasons.push(`已核验项目为「${projectName}」。`)
  reasons.push(renderWindowReason(facts, windowStatus))
  const budget = budgetText(facts?.budget)
  if (budget) reasons.push(`已核验项目预算为 ${budget}。`)
  if (actionCodes.includes('CONTACT_PUBLIC_CONTACT') && hasPublicContact(facts)) {
    reasons.push('已核验公告提供公开联系人或联系方式，可用于核实公开要求；沟通结果本身仍需人工确认。')
  }
  return reasons.slice(0, 5)
}

function productDetailsMissing(facts) {
  const products = Array.isArray(facts?.products) ? facts.products : []
  if (products.length === 0) return true
  return products.every((item) => {
    const spec = text(item?.specification, 200)
    return !spec || /详见|见采购文件|见招标文件|见附件/.test(spec)
  })
}

/**
 * Item-specific risks only. Generic disclaimers (official text prevails, the
 * user decides, focus targets are not relationships) are rendered once per
 * page by the frontend instead of being repeated on every card.
 */
function renderRisks(facts, customerContext, windowStatus) {
  const risks = []
  if (windowStatus === 'RELATIVE_WINDOW') {
    risks.push('官方只给出相对窗口，未公布精确截止日期或时刻；内部推算时间不得对外表述为官方事实。')
  }
  if (windowStatus === 'LATE_WINDOW') {
    risks.push('报名或文件获取窗口已结束；能否继续获取文件或参与，以官方答复为准。')
  }
  if (budgetText(facts?.budget) === null) {
    risks.push('公告未列明预算金额，需在官方文件中核实。')
  }
  if (productDetailsMissing(facts)) {
    risks.push('公告正文未列出完整品目和技术参数，需下载官方采购文件逐条核对。')
  }
  if (customerContext && !hasConfirmedExecutionContext(customerContext)) {
    risks.push('重点关注对象不能视为已有关系，也不能据此推断医院竞争情况。')
  }
  return risks.slice(0, 4)
}

function renderDecision(actionCodes, facts, customerContext, windowStatus) {
  return {
    action: actionCodes.map((code) => renderAction(code, facts)).join(' '),
    reasons: renderReasons(facts, windowStatus, actionCodes),
    risks: renderRisks(facts, customerContext, windowStatus),
    requires_human_confirmation: true,
  }
}

export const PUBLIC_RULE_VERSION = 'public-fact-rules-v1'

// Deterministic priority order per window. The previous design asked the model
// to pick 1-3 of these codes while the server rendered every visible word, so
// the model added latency and cost but no information. Rules make the next
// step instant, identical for every visitor and available without an AI key.
const RULE_ACTION_ORDER = Object.freeze({
  OPEN: ['REVIEW_OFFICIAL_SOURCE', 'MATCH_CONFIRMED_RESOURCES', 'VERIFY_REQUIREMENTS', 'CONTACT_PUBLIC_CONTACT', 'PREPARE_REQUIRED_MATERIALS'],
  RELATIVE_WINDOW: ['CONFIRM_RELATIVE_WINDOW', 'CONTACT_PUBLIC_CONTACT', 'REVIEW_OFFICIAL_SOURCE', 'MATCH_CONFIRMED_RESOURCES', 'VERIFY_REQUIREMENTS'],
  LATE_WINDOW: ['CHECK_LATE_WINDOW_OPTIONS', 'REVIEW_OFFICIAL_SOURCE', 'CONTACT_PUBLIC_CONTACT', 'MATCH_CONFIRMED_RESOURCES', 'VERIFY_REQUIREMENTS'],
})

export function selectRuleActionCodes(facts, evidenceUrls, customerContext, windowStatus) {
  const allowed = allowedActionCodes(facts, evidenceUrls, customerContext, windowStatus)
  const order = RULE_ACTION_ORDER[windowStatus] || RULE_ACTION_ORDER.OPEN
  const codes = order.filter((code) => allowed.has(code)).slice(0, 3)
  return codes.length ? codes : ['VERIFY_REQUIREMENTS']
}

export function buildRuleDecision(facts, evidenceUrls, customerContext, windowStatus) {
  const safeFacts = asObject(facts)
  if (!safeFacts) throw invalid('RULE_DECISION_CONTEXT_MISSING')
  const context = asObject(customerContext)
  const codes = selectRuleActionCodes(safeFacts, evidenceUrls, context, windowStatus)
  return renderDecision(codes, safeFacts, context, windowStatus)
}

export function firstRuleActionText(facts, evidenceUrls, windowStatus) {
  const [code] = selectRuleActionCodes(facts, evidenceUrls, null, windowStatus)
  return renderAction(code, facts)
}

export { budgetText, dateTimeText, dateOnlyText }
