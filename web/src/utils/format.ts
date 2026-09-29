import type { PriorityTier } from '@/types'

export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const y = date.getFullYear()
  const m = date.getMonth() + 1
  const d = date.getDate()
  return `${y}年${m}月${d}日`
}

export function formatDateOnly(value: string | null | undefined): string | null {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const [, year, month, day] = match
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)))
  if (
    date.getUTCFullYear() !== Number(year) ||
    date.getUTCMonth() + 1 !== Number(month) ||
    date.getUTCDate() !== Number(day)
  ) {
    return null
  }
  return `${Number(year)}年${Number(month)}月${Number(day)}日`
}

export function formatDateTime(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const y = date.getFullYear()
  const m = date.getMonth() + 1
  const d = date.getDate()
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${y}年${m}月${d}日 ${hh}:${mm}`
}

export function formatBudget(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null
  if (value >= 10000) {
    // Up to two decimals, trailing zeros dropped: 10,499,940 → "1049.99 万元"
    // (toFixed(1) used to carry it to "1050.0 万元", which reads as a rounded
    // budget rather than the published figure).
    const wan = Math.round((value / 10000) * 100) / 100
    return `${wan} 万元`
  }
  return `¥${value.toLocaleString('zh-CN')}`
}

export function formatToday(): string {
  const now = new Date()
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']
  return `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 星期${weekdays[now.getDay()]}`
}

export function getPriorityTier(score: number): PriorityTier {
  if (score >= 90) return 'critical'
  if (score >= 75) return 'high'
  if (score >= 60) return 'medium'
  return 'low'
}

export function getPriorityLabel(score: number): string {
  const tier = getPriorityTier(score)
  if (tier === 'critical') return '立即关注'
  if (tier === 'high') return '重点跟进'
  if (tier === 'medium') return '持续观察'
  return '普通'
}

export function pickDisplayDate(facts: {
  bid_deadline: string | null
  expected_purchase_date: string | null
  registration_deadline: string | null
  registration_deadline_date?: string | null
}): { label: string; value: string } | null {
  if (facts.bid_deadline) {
    const formatted = formatDate(facts.bid_deadline)
    if (formatted) return { label: '投标截止', value: formatted }
  }
  if (facts.expected_purchase_date) {
    const formatted = formatDate(facts.expected_purchase_date)
    if (formatted) return { label: '预计采购', value: formatted }
  }
  if (facts.registration_deadline) {
    const formatted = formatDate(facts.registration_deadline)
    if (formatted) return { label: '报名截止', value: formatted }
  }
  if (facts.registration_deadline_date) {
    const formatted = formatDateOnly(facts.registration_deadline_date)
    if (formatted) {
      return {
        label: '报名截止日期',
        value: `${formatted}（未公布具体时间）`,
      }
    }
  }
  return null
}

export function isoDaysFromNow(days: number): string {
  const dt = new Date()
  dt.setHours(12, 0, 0, 0)
  dt.setDate(dt.getDate() + days)
  const y = dt.getFullYear()
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const d = String(dt.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function isoHoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString()
}

export function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString()
}

export function uid(prefix = 'id'): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`
}

export function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value))
}
