import { ENABLED_MARKETS, type MarketCode } from '../config/marketPreference.ts'

interface OpportunityMarketInput {
  opportunity_id: string
  source_id?: string | null
  facts: {
    market_code?: string | null
    region?: string | null
  }
}

const MARKET_CODES = new Set<string>(ENABLED_MARKETS.map((market) => market.code))
const TIANJIN_LOCAL_REGIONS = new Set([
  '和平区', '河东区', '河西区', '南开区', '河北区', '红桥区', '东丽区', '西青区',
  '津南区', '北辰区', '武清区', '宝坻区', '滨海新区', '宁河区', '静海区', '蓟州区',
  '宁河县', '静海县', '蓟县', '市辖区',
])
const UNSUPPORTED_PROVINCE_NAMES = [
  '山西', '内蒙古', '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南',
  '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州', '云南', '西藏',
  '陕西', '甘肃', '青海', '宁夏', '新疆', '台湾', '香港', '澳门',
]

/** Resolve display scope for runtime/legacy snapshots without inventing a market. */
export function marketCodeForOpportunity(card: OpportunityMarketInput): MarketCode | null {
  const explicit = String(card.facts.market_code ?? '').trim().toUpperCase()
  if (explicit) return MARKET_CODES.has(explicit) ? explicit as MarketCode : null

  const region = String(card.facts.region ?? '').trim()
  if (region) {
    const market = ENABLED_MARKETS.find(({ code, name }) =>
      region === name || region.startsWith(`${name}${code === 'BJ' || code === 'TJ' ? '市' : '省'}`),
    )
    if (market) return market.code
    // Canonical CCGP regions may contain only a city/county/district. Retain
    // their validated adapter scope, but never override an explicit province
    // outside the supported markets (including autonomous regions/municipalities).
    if (
      UNSUPPORTED_PROVINCE_NAMES.some((name) => region.startsWith(name)) ||
      /省|自治区|特别行政区/.test(region) ||
      !/(?:市|县|区|旗|镇|乡|街道)$/.test(region)
    ) return null
  }

  // These prefixes are emitted by registered source adapters. Unknown opaque
  // ids must remain unscoped instead of being silently assigned to Tianjin.
  const regional = card.opportunity_id.match(/^ccgp_(tj|bj|he|ln|jl|hl)_/i)
  if (regional) return regional[1].toUpperCase() as MarketCode
  // Runtime source "ccgp" is the registered Tianjin query-plan collector.
  // Its legacy hash ids alone are not scope evidence: require that source
  // identity AND an official Tianjin-local region, never a title/buyer guess.
  if (card.source_id === 'ccgp' && /^ccgp_[a-f0-9]{16}$/i.test(card.opportunity_id)
      && TIANJIN_LOCAL_REGIONS.has(region)) return 'TJ'
  if (/^(?:tjmugh|tjnothop|tjfch|teda|tjzxfc|tjzyefy)_/i.test(card.opportunity_id)) return 'TJ'
  return null
}
