import type { TodayActionCard } from '@/types'

export type BusinessMarketCode = 'TJ' | 'BJ' | 'HE' | 'LN' | 'JL' | 'HL'

export const BUSINESS_MARKETS: ReadonlyArray<{ code: BusinessMarketCode; name: string }> = [
  { code: 'TJ', name: '天津' },
  { code: 'BJ', name: '北京' },
  { code: 'HE', name: '河北' },
  { code: 'LN', name: '辽宁' },
  { code: 'JL', name: '吉林' },
  { code: 'HL', name: '黑龙江' },
]

const STORAGE_KEY = 'medopp.business-markets.v1'
const ALLOWED_CODES = new Set<BusinessMarketCode>(BUSINESS_MARKETS.map((item) => item.code))

function normalizeCodes(value: unknown): BusinessMarketCode[] {
  if (!Array.isArray(value)) return []
  const result: BusinessMarketCode[] = []
  for (const raw of value) {
    if (typeof raw !== 'string') continue
    const code = raw.trim().toUpperCase() as BusinessMarketCode
    if (!ALLOWED_CODES.has(code) || result.includes(code)) continue
    result.push(code)
  }
  return BUSINESS_MARKETS.map((item) => item.code).filter((code) => result.includes(code))
}

export function loadBusinessMarketPreferences(): BusinessMarketCode[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (Array.isArray(parsed)) return normalizeCodes(parsed)
    if (parsed && typeof parsed === 'object' && 'codes' in parsed) {
      return normalizeCodes((parsed as { codes?: unknown }).codes)
    }
    return []
  } catch {
    return []
  }
}

export function saveBusinessMarketPreferences(codes: BusinessMarketCode[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ codes: normalizeCodes(codes) }))
  } catch {
    // Best effort only. Business-region selection never changes public facts.
  }
}

export function cardMatchesBusinessMarkets(
  card: TodayActionCard,
  codes: BusinessMarketCode[],
): boolean {
  if (codes.length === 0) return true
  const code = card.facts.market_code?.trim().toUpperCase() as BusinessMarketCode | undefined
  return Boolean(code && codes.includes(code))
}

export function filterCardsByBusinessMarkets(
  cards: TodayActionCard[],
  codes = loadBusinessMarketPreferences(),
): TodayActionCard[] {
  return codes.length === 0 ? cards : cards.filter((card) => cardMatchesBusinessMarkets(card, codes))
}

export function businessMarketSelectionLabel(codes: BusinessMarketCode[]): string {
  const normalized = normalizeCodes(codes)
  if (normalized.length === 0) return '全部已覆盖地区'
  if (normalized.length === 2 && normalized.includes('TJ') && normalized.includes('BJ')) return '京津'
  return BUSINESS_MARKETS.filter((item) => normalized.includes(item.code))
    .map((item) => item.name)
    .join('、')
}

export function toggleBusinessMarket(
  current: BusinessMarketCode[],
  code: BusinessMarketCode,
): BusinessMarketCode[] {
  if (current.length === 0) return [code]
  const next = current.includes(code)
    ? current.filter((item) => item !== code)
    : [...current, code]
  return normalizeCodes(next)
}

export function isExactBusinessMarketSelection(
  current: BusinessMarketCode[],
  expected: BusinessMarketCode[],
): boolean {
  const left = normalizeCodes(current)
  const right = normalizeCodes(expected)
  return left.length === right.length && left.every((code, index) => code === right[index])
}
