export type OpportunityFeedback =
  | 'ALREADY_KNOWN'
  | 'NEW_NOT_VALUABLE'
  | 'NEW_WORTH_FOLLOWING'

interface OpportunityFeedbackEntry {
  value: OpportunityFeedback
  at: string
}

const STORAGE_KEY = 'medopp.opportunity-feedback.v1'
const FEEDBACK_VALUES = new Set<OpportunityFeedback>([
  'ALREADY_KNOWN',
  'NEW_NOT_VALUABLE',
  'NEW_WORTH_FOLLOWING',
])
const listeners = new Set<() => void>()

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function readEntries(): Record<string, OpportunityFeedbackEntry> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = asRecord(JSON.parse(raw))
    if (!parsed) return {}
    const result: Record<string, OpportunityFeedbackEntry> = {}
    for (const [opportunityId, value] of Object.entries(parsed)) {
      const row = asRecord(value)
      if (!row || typeof row.value !== 'string' || typeof row.at !== 'string') continue
      if (!FEEDBACK_VALUES.has(row.value as OpportunityFeedback)) continue
      result[opportunityId] = {
        value: row.value as OpportunityFeedback,
        at: row.at,
      }
    }
    return result
  } catch {
    return {}
  }
}

function writeEntries(entries: Record<string, OpportunityFeedbackEntry>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // Pilot feedback is best-effort local persistence. Public facts never depend on it.
  }
}

function emit(): void {
  listeners.forEach((listener) => listener())
}

export function subscribeOpportunityFeedback(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getOpportunityFeedback(opportunityId: string): OpportunityFeedback | null {
  return readEntries()[opportunityId]?.value ?? null
}

export function setOpportunityFeedback(
  opportunityId: string,
  value: OpportunityFeedback | null,
): void {
  const entries = readEntries()
  if (value === null) {
    delete entries[opportunityId]
  } else {
    entries[opportunityId] = {
      value,
      at: new Date().toISOString(),
    }
  }
  writeEntries(entries)
  emit()
}

export function recommendationFeedbackSummary(opportunityIds: string[]): {
  responded: number
  effective_surprises: number
  effective_surprise_rate: number | null
} {
  const entries = readEntries()
  const uniqueIds = [...new Set(opportunityIds)]
  const values = uniqueIds
    .map((opportunityId) => entries[opportunityId]?.value ?? null)
    .filter((value): value is OpportunityFeedback => value !== null)
  const effectiveSurprises = values.filter((value) => value === 'NEW_WORTH_FOLLOWING').length
  return {
    responded: values.length,
    effective_surprises: effectiveSurprises,
    effective_surprise_rate:
      values.length > 0 ? Math.round((effectiveSurprises / values.length) * 100) : null,
  }
}
