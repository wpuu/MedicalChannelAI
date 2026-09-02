import type { PriorityScoreScope } from '@/types'
import { apiBaseUrl, isApiMode } from './apiConfig'

export interface TargetHospitalOpportunity {
  opportunity_id: string
  rank: number
  hospital: string | null
  buyer_name: string | null
  department: string | null
  project_name: string | null
  priority_score: number
  score_scope: PriorityScoreScope
  budget_cny: number | null
  registration_deadline: string | null
  registration_deadline_date: string | null
  bid_deadline: string | null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function numberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/,/g, '').trim())
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function budgetValue(value: unknown): number | null {
  const direct = numberValue(value)
  if (direct !== null) return direct
  const row = asRecord(value)
  if (!row) return null
  for (const key of ['amount', 'amount_cny', 'budget_cny', 'value']) {
    const parsed = numberValue(row[key])
    if (parsed !== null) return parsed
  }
  return null
}

function parseOpportunity(value: unknown, fallbackRank: number): TargetHospitalOpportunity | null {
  const row = asRecord(value)
  const facts = asRecord(row?.facts)
  const priority = asRecord(row?.priority)
  const id = text(row?.opportunity_id)
  if (!row || !facts || !priority || !id) return null

  const score = numberValue(priority.score)
  if (score === null) return null
  const scopeRaw = text(priority.score_scope)
  const scoreScope: PriorityScoreScope =
    scopeRaw === 'PERSONALIZED' || text(priority.score_type) === 'BUSINESS_PRIORITY_PERSONALIZED_V2'
      ? 'PERSONALIZED'
      : 'PUBLIC'

  return {
    opportunity_id: id,
    rank: numberValue(row.rank) ?? fallbackRank,
    hospital: text(facts.hospital_name) ?? text(facts.hospital),
    buyer_name: text(facts.buyer_name),
    department: text(facts.department),
    project_name: text(facts.project_name),
    priority_score: score,
    score_scope: scoreScope,
    budget_cny: budgetValue(facts.budget),
    registration_deadline: text(facts.registration_deadline),
    registration_deadline_date: text(facts.registration_deadline_date),
    bid_deadline: text(facts.bid_deadline),
  }
}

export async function getTargetHospitalOpportunityPool(): Promise<TargetHospitalOpportunity[]> {
  if (!isApiMode) throw new Error('API_MODE_REQUIRED')
  const response = await fetch(`${apiBaseUrl}/today`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    const payload = asRecord(await response.json().catch(() => null))
    const error = text(payload?.error) ?? `HTTP_${response.status}`
    throw new Error(error)
  }

  const root = asRecord(await response.json())
  const pool = Array.isArray(root?.opportunity_pool)
    ? root.opportunity_pool
    : Array.isArray(root?.cards)
      ? root.cards
      : null
  if (!pool) throw new Error('TARGET_OPPORTUNITY_POOL_INVALID')

  return pool
    .map((item, index) => parseOpportunity(item, index + 1))
    .filter((item): item is TargetHospitalOpportunity => item !== null)
}
