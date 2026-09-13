export type MarketCode = 'TJ' | 'BJ' | 'HE' | 'LN' | 'JL' | 'HL'
export type MarketSelection = MarketCode | 'JJ' | 'JJJ' | 'NE3' | 'ALL'

export interface MarketDefinition {
  code: MarketCode
  name: string
  adminCode: string
  ccgpZoneId: string
}

export const ENABLED_MARKETS: readonly MarketDefinition[] = [
  { code: 'BJ', name: '北京', adminCode: '110000', ccgpZoneId: '11' },
  { code: 'TJ', name: '天津', adminCode: '120000', ccgpZoneId: '12' },
  { code: 'HE', name: '河北', adminCode: '130000', ccgpZoneId: '13' },
  { code: 'LN', name: '辽宁', adminCode: '210000', ccgpZoneId: '21' },
  { code: 'JL', name: '吉林', adminCode: '220000', ccgpZoneId: '22' },
  { code: 'HL', name: '黑龙江', adminCode: '230000', ccgpZoneId: '23' },
] as const

export const MARKET_SELECTION_OPTIONS: readonly { value: MarketSelection; label: string }[] = [
  { value: 'TJ', label: '天津' },
  { value: 'BJ', label: '北京' },
  { value: 'HE', label: '河北' },
  { value: 'LN', label: '辽宁' },
  { value: 'JL', label: '吉林' },
  { value: 'HL', label: '黑龙江' },
  { value: 'JJ', label: '京津' },
  { value: 'JJJ', label: '京津冀' },
  { value: 'NE3', label: '东北三省' },
  { value: 'ALL', label: '全部已开通' },
] as const

const STORAGE_KEY = 'medicalchannelai.business-market.v1'
const VALID_SELECTIONS = new Set<MarketSelection>(MARKET_SELECTION_OPTIONS.map((item) => item.value))

export function getMarketSelection(): MarketSelection {
  if (typeof localStorage === 'undefined') return 'TJ'
  try {
    const value = localStorage.getItem(STORAGE_KEY) as MarketSelection | null
    return value && VALID_SELECTIONS.has(value) ? value : 'TJ'
  } catch {
    return 'TJ'
  }
}

export function setMarketSelection(value: MarketSelection): void {
  if (!VALID_SELECTIONS.has(value) || typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // Business-region preference is best-effort until account sync is introduced.
  }
}

export function marketCodesForSelection(selection = getMarketSelection()): MarketCode[] {
  if (selection === 'JJ') return ['BJ', 'TJ']
  if (selection === 'JJJ') return ['BJ', 'TJ', 'HE']
  if (selection === 'NE3') return ['LN', 'JL', 'HL']
  if (selection === 'ALL') return ENABLED_MARKETS.map((item) => item.code)
  return [selection]
}

export function marketSelectionLabel(selection = getMarketSelection()): string {
  return MARKET_SELECTION_OPTIONS.find((item) => item.value === selection)?.label ?? '天津'
}

export function marketCodeFromOpportunityId(opportunityId: string): MarketCode {
  const match = opportunityId.match(/^ccgp_(bj|he|ln|jl|hl)_/i)
  if (!match) return 'TJ'
  return match[1].toUpperCase() as MarketCode
}

export function marketDefinition(code: MarketCode): MarketDefinition {
  return ENABLED_MARKETS.find((item) => item.code === code) ?? ENABLED_MARKETS[1]
}
