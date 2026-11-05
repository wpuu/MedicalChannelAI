import { ENABLED_MARKETS, type MarketCode } from '../config/marketPreference.ts'

interface OpportunityMarketInput {
  opportunity_id: string
  facts: {
    market_code?: string | null
    region?: string | null
  }
}

const MARKET_CODES = new Set<string>(ENABLED_MARKETS.map((market) => market.code))

/** Resolve display scope for runtime/legacy snapshots without inventing a market. */
export function marketCodeForOpportunity(card: OpportunityMarketInput): MarketCode | null {
  const explicit = String(card.facts.market_code ?? '').trim().toUpperCase()
  if (explicit) return MARKET_CODES.has(explicit) ? explicit as MarketCode : null

  const region = String(card.facts.region ?? '').trim()
  if (region) {
    const market = ENABLED_MARKETS.find(({ code, name }) =>
      region === name || region.startsWith(`${name}${code === 'BJ' || code === 'TJ' ? '市' : '省'}`),
    )
    return market?.code ?? null
  }

  // These prefixes are emitted by registered source adapters. Unknown opaque
  // ids must remain unscoped instead of being silently assigned to Tianjin.
  const regional = card.opportunity_id.match(/^ccgp_(tj|bj|he|ln|jl|hl)_/i)
  if (regional) return regional[1].toUpperCase() as MarketCode
  if (/^(?:tjmugh|tjnothop|tjfch|teda|tjzxfc|tjzyefy)_/i.test(card.opportunity_id)) return 'TJ'
  return null
}
