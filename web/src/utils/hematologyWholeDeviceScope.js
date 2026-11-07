/**
 * A01: conservative, presentation-only product scope for the Tianjin pilot.
 * This does not establish supplier qualification, eligibility to bid, source
 * freshness, or whether an opportunity was actually collected today.
 * It never mutates a published opportunity or customer-private data.
 */
const WHOLE_DEVICE = /(?:血(?:液)?细胞分析仪|血球(?:分析)?仪|血常规分析仪)/u
const ACCESSORY_OR_SERVICE = /(?:试剂|质控|校准|稀释|溶血剂|清洗液|清洗剂|冲洗液|鞘液|耗材|配件|备件|零件|电源模块|计数板|试纸|测试卡|维修|维保|维护|保养|售后|租赁|服务|配套软件)/u
const OTHER_DEVICE = /(?:生化分析仪|免疫分析仪|凝血分析仪|血气分析仪|尿液分析仪|尿沉渣分析仪|流式细胞仪|心电图机|超声诊断仪|CT机|磁共振成像仪)/iu
const CLAUSE_DIVIDER = /(?:以及|及|与|和|并|、|，|,|；|;|＋|\+)/u

function compact(value) {
  return typeof value === 'string' ? value.trim().replace(/\s+/gu, ' ').slice(0, 180) : ''
}

function result(status, reason, evidence = null) {
  return { status, reason, evidence }
}

function evidenceFor(index, name) {
  return { field: 'facts.products[' + index + '].name', itemIndex: index, productName: name.slice(0, 90) }
}

/**
 * @param {{ facts?: object, evidence_source_urls?: unknown }} card - existing UI view model.
 * @returns {{status: 'IN_SCOPE'|'OUT_OF_SCOPE'|'NEEDS_EVIDENCE',reason:string,evidence:object|null}}
 */
export function classifyHematologyWholeDeviceScope(card) {
  const facts = card && typeof card === 'object' && !Array.isArray(card) ? card.facts : null
  if (!facts || typeof facts !== 'object' || Array.isArray(facts)) {
    return result('NEEDS_EVIDENCE', '缺少已结构化的官方商机事实，无法判断整机范围。')
  }

  const marketCode = compact(facts.market_code).toUpperCase()
  if (!marketCode) return result('NEEDS_EVIDENCE', '缺少明确的地区代码，不能认定为天津商机。')
  if (marketCode !== 'TJ') return result('OUT_OF_SCOPE', '本期仅覆盖天津采购机会，当前商机的地区代码不是天津。')

  if (facts.verification_status !== 'VERIFIED') {
    return result('NEEDS_EVIDENCE', '官方事实尚未标为 VERIFIED，不对整机相关性作肯定判断。')
  }
  const urls = Array.isArray(card.evidence_source_urls) ? card.evidence_source_urls : []
  if (!urls.some((url) => typeof url === 'string' && /^https:\/\/[^\s/]+\//iu.test(url))) {
    return result('NEEDS_EVIDENCE', '缺少快照附带的有效 HTTPS 官方依据链接，需人工核对来源。')
  }

  const items = Array.isArray(facts.products) ? facts.products : []
  if (items.length === 0) {
    return result('NEEDS_EVIDENCE', '缺少逐项结构化设备明细；项目标题、IVD或检验科名称不能确认整机。')
  }

  let excluded = 0
  let ambiguous = 0
  let firstExcluded = null
  let firstAmbiguous = null
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index]
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      ambiguous += 1
      continue
    }
    const name = compact(item.name)
    const category = compact(item.category)
    const specification = compact(item.specification)
    if (!name) {
      ambiguous += 1
      continue
    }
    const evidence = evidenceFor(index, name)
    const clauses = name.split(CLAUSE_DIVIDER).map((part) => part.trim()).filter(Boolean)
    const explicitDevice = clauses.some((part) => WHOLE_DEVICE.test(part) && !ACCESSORY_OR_SERVICE.test(part))
    const conflictingMetadata = ACCESSORY_OR_SERVICE.test(category) || ACCESSORY_OR_SERVICE.test(specification)
    if (explicitDevice && !conflictingMetadata) {
      return result('IN_SCOPE', '官方结构化设备明细第' + (index + 1) + '项明确列有血细胞分析仪整机；仍须核对资格与报名条件。', evidence)
    }
    if (explicitDevice && conflictingMetadata) {
      ambiguous += 1
      firstAmbiguous ??= evidence
      continue
    }
    // An unsplit phrase mentioning a device and its accessories/services can
    // describe the accessory alone or a bundled purchase: never affirm it.
    if (WHOLE_DEVICE.test(name) && ACCESSORY_OR_SERVICE.test(name) && /(?:整机|设备|购置|采购|包含|含)/u.test(name)) {
      ambiguous += 1
      firstAmbiguous ??= evidence
      continue
    }
    if (ACCESSORY_OR_SERVICE.test(name) || OTHER_DEVICE.test(name)) {
      excluded += 1
      firstExcluded ??= evidence
      continue
    }
    ambiguous += 1
    firstAmbiguous ??= evidence
  }

  if (ambiguous > 0) {
    return result('NEEDS_EVIDENCE', '已有设备明细但不能确定属于血细胞分析仪整机；请逐项核实产品名称和规格。', firstAmbiguous)
  }
  if (excluded > 0) {
    return result('OUT_OF_SCOPE', '结构化设备明细仅见试剂、质控、耗材、维保或其他明确非本期整机项目。', firstExcluded)
  }
  return result('NEEDS_EVIDENCE', '设备明细不足，不能认定为血细胞分析仪整机。')
}
