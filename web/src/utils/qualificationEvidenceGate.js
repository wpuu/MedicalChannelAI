/**
 * A04: deterministic, offline-only qualification DOCUMENT precheck.
 * Never infers legal bid eligibility from product scope, AI, or self-reported
 * DIRECT_AUTHORIZED. Current published cards carry none of this contract.
 *
 * Callers may pass complete, separately verified synthetic evidence into this
 * pure function. Do not bind client certificates or proof text to public UI.
 */
const DEFAULT_GAPS = Object.freeze([
  '缺少经核验的官方资格条件全集、公告版本与适用包件。',
  '缺少当前账号经许可且核实有效的客户资质或厂家授权证明。',
  '尚未逐项核对主体、具体产品、有效期及合规替代路径。',
])
const LABEL = Object.freeze({
  SATISFIED: '资料预核匹配（非采购方资格确认）',
  NOT_SATISFIED: '存在明确不符合条件（需人工复核）',
  UNKNOWN: '投标资格待核',
})
const ITEM_REASON = Object.freeze({
  SATISFIED: '本项官方条件与经核验客户材料匹配；仍需人工复核。',
  NOT_SATISFIED: '已核实当前未满足本项强制条件且无有效替代材料。',
  UNKNOWN: '本项官方条件或客户证明缺少可核验的必要信息。',
})

function record(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v) ? v : null
}

function nonempty(v) {
  return typeof v === 'string' && v.trim().length > 0
}

function zonedTime(v) {
  if (typeof v !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(v)) return null
  const parsed = Date.parse(v)
  return Number.isFinite(parsed) ? parsed : null
}

function httpsUrl(v) {
  return nonempty(v) && /^https:\/\/[^/\s]+\//i.test(v)
}

function result(status, missing = [], items = [], risks = []) {
  return {
    status,
    label: LABEL[status],
    missing: [...missing],
    items: items.map((item) => ({
      index: item.index,
      status: item.status,
      reason: ITEM_REASON[item.status],
    })),
    risks: [...risks],
    final_qualification_confirmed: false,
  }
}

function unknown(missing = DEFAULT_GAPS, items = [], risks = []) {
  return result('UNKNOWN', missing, items, risks)
}

function isOfficialComplete(input, official, time) {
  if (!record(input) || !record(official) || time === null) return false
  if (![input.project_id, input.package_id, input.notice_version, input.organization_id, input.user_id].every(nonempty)) return false
  if (
    official.project_id !== input.project_id ||
    official.package_id !== input.package_id ||
    official.notice_version !== input.notice_version ||
    official.current_notice_version !== input.notice_version
  ) return false
  if (
    official.requirements_complete !== true ||
    official.attachments_complete !== true ||
    official.version_current_verified !== true ||
    official.source_verified !== true ||
    !httpsUrl(official.source_url)
  ) return false
  const checked = zonedTime(official.verified_at)
  return checked !== null && checked <= time && Array.isArray(official.requirements)
}

/**
 * @param {import('./qualificationEvidenceGate').QualificationAssessmentInput|null|undefined} input
 * @returns {import('./qualificationEvidenceGate').QualificationAssessmentResult}
 */
export function evaluateQualificationEvidence(input = null) {
  // Intentional fail-closed default for every real published card today.
  if (!record(input)) return unknown()
  const time = zonedTime(input.as_of)
  const official = record(input.official)
  if (!isOfficialComplete(input, official, time)) {
    return unknown(['官方资格条件、完整附件、包件或最新版本尚未获得独立核验。'])
  }
  const requirements = official.requirements
  if (requirements.length === 0 || requirements.some((r) => !record(r) || typeof r.hard !== 'boolean')) {
    return unknown(['官方硬性资格条款全集为空或不完整，不能自动认定资格满足。'])
  }
  const hard = requirements.filter((r) => r.hard === true)
  if (hard.length === 0) {
    return unknown(['未取得经独立核验的适用硬性资格条款；不把空清单判成满足。'])
  }
  const ids = new Set()
  for (const req of requirements) {
    if (
      !nonempty(req.id) || ids.has(req.id) ||
      !nonempty(req.source_locator) || !httpsUrl(req.source_url) ||
      !nonempty(req.source_excerpt) || req.verified !== true
    ) return unknown(['官方资格条款的逐项来源定位、完整性或条目编号不足。'])
    ids.add(req.id)
    if (req.hard && (![req.evidence_kind, req.subject_key, req.product_key].every(nonempty))) {
      return unknown(['硬性资格条件的材料类别、主体或适用产品范围尚不明确。'])
    }
  }
  const customer = record(input.customer)
  if (
    !customer ||
    customer.organization_id !== input.organization_id ||
    customer.user_id !== input.user_id ||
    customer.consent_to_precheck !== true ||
    !Array.isArray(customer.proofs)
  ) return unknown(['缺少当前账号经许可、可用于本次资格预核的客户证明。'])

  const items = []
  let hasNotMet = false
  let hasUnknown = false
  for (let index = 0; index < hard.length; index += 1) {
    const req = hard[index]
    const matches = customer.proofs.filter((proof) => record(proof) && proof.requirement_id === req.id)
    const scoped = matches.filter((proof) =>
      proof.organization_id === input.organization_id &&
      proof.user_id === input.user_id &&
      proof.project_id === input.project_id &&
      proof.package_id === input.package_id &&
      proof.notice_version === input.notice_version &&
      proof.evidence_kind === req.evidence_kind &&
      proof.subject_key === req.subject_key &&
      proof.product_key === req.product_key &&
      proof.consent_to_precheck === true &&
      proof.verified_by_human === true &&
      zonedTime(proof.checked_at) !== null &&
      zonedTime(proof.checked_at) <= time
    )
    let positive = false
    let negative = false
    let uncertain = matches.length !== scoped.length || scoped.length === 0
    for (const proof of scoped) {
      if (proof.conflict_unresolved === true) {
        uncertain = true
        continue
      }
      if (proof.finding === 'MATCH') {
        const start = zonedTime(proof.valid_from)
        const end = zonedTime(proof.valid_until)
        if (start !== null && end !== null && start <= time && time <= end && zonedTime(proof.checked_at) <= time) {
          positive = true
        } else {
          uncertain = true
        }
      } else if (proof.finding === 'NOT_MET') {
        // Absence of evidence is NOT a verified negative. The negative is
        // explicit only when alternatives have been independently ruled out.
        if (proof.no_valid_alternative_verified === true && proof.confirmed_current === true) {
          negative = true
        } else {
          uncertain = true
        }
      } else {
        uncertain = true
      }
    }
    let status = 'UNKNOWN'
    if (!uncertain && positive && !negative) status = 'SATISFIED'
    else if (!uncertain && negative && !positive) status = 'NOT_SATISFIED'
    else if (positive && negative) uncertain = true
    if (status === 'NOT_SATISFIED') hasNotMet = true
    if (status === 'UNKNOWN') hasUnknown = true
    items.push({ index, status })
  }
  if (hasUnknown) {
    const risks = hasNotMet ? ['另有已核实的不符合项，须人工核对；不可视为可投。'] : []
    return unknown(['至少一项适用硬性资格缺少可信证明、有效期或一致的核验结果。'], items, risks)
  }
  if (hasNotMet) {
    return result('NOT_SATISFIED', ['已确认至少一项强制条件不满足且无有效替代；仍需人工复核。'], items)
  }
  return result('SATISFIED', ['仅完成本次离线资料预核，不能代表采购方最终资格审核或当前报名窗口。'], items)
}
