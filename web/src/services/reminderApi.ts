import { apiBaseUrl, isApiMode } from './apiConfig'

export interface DueReminder {
  reminder_id: string
  opportunity_id: string
  followup_status: string
  remind_at: string
  note: string | null
  facts: {
    buyer_name: string | null
    hospital_name: string | null
    project_name: string | null
  }
}

interface ReminderInboxResponse {
  schema_version: '0.1'
  mode: 'FOLLOWUP_REMINDER_INBOX'
  count: number
  reminders: DueReminder[]
}

const FOLLOWUP_STATUSES = new Set([
  'NEW',
  'REVIEWING',
  'CONTACTED',
  'RELATIONSHIP_VERIFIED',
  'PREPARING',
  'BID_SUBMITTED',
  'WON',
  'LOST',
  'NOT_FIT',
  'MONITOR',
  'ARCHIVED',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function exactKeys(record: Record<string, unknown>, allowed: string[]): boolean {
  const expected = new Set(allowed)
  return Object.keys(record).length === expected.size &&
    Object.keys(record).every((key) => expected.has(key))
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function validateInbox(value: unknown): ReminderInboxResponse {
  const root = asRecord(value)
  if (
    !root ||
    !exactKeys(root, ['schema_version', 'mode', 'count', 'reminders']) ||
    root.schema_version !== '0.1' ||
    root.mode !== 'FOLLOWUP_REMINDER_INBOX' ||
    !Number.isInteger(root.count) ||
    typeof root.count !== 'number' ||
    root.count < 0 ||
    root.count > 20 ||
    !Array.isArray(root.reminders)
  ) {
    throw new Error('REMINDER_RESPONSE_INVALID')
  }
  const reminders = root.reminders.map((item) => {
    const row = asRecord(item)
    const facts = asRecord(row?.facts)
    if (
      !row ||
      !exactKeys(row, [
        'reminder_id',
        'opportunity_id',
        'followup_status',
        'remind_at',
        'note',
        'facts',
      ]) ||
      typeof row.reminder_id !== 'string' ||
      !/^mrem_[0-9a-f]{64}$/.test(row.reminder_id) ||
      typeof row.opportunity_id !== 'string' ||
      !/^opp_[0-9a-fA-F-]{36}$/.test(row.opportunity_id) ||
      typeof row.followup_status !== 'string' ||
      !FOLLOWUP_STATUSES.has(row.followup_status) ||
      typeof row.remind_at !== 'string' ||
      Number.isNaN(new Date(row.remind_at).getTime()) ||
      !nullableString(row.note) ||
      !facts ||
      !exactKeys(facts, ['buyer_name', 'hospital_name', 'project_name']) ||
      !nullableString(facts.buyer_name) ||
      !nullableString(facts.hospital_name) ||
      !nullableString(facts.project_name)
    ) {
      throw new Error('REMINDER_RESPONSE_INVALID')
    }
    return {
      reminder_id: row.reminder_id,
      opportunity_id: row.opportunity_id,
      followup_status: row.followup_status,
      remind_at: row.remind_at,
      note: row.note,
      facts: {
        buyer_name: facts.buyer_name,
        hospital_name: facts.hospital_name,
        project_name: facts.project_name,
      },
    } satisfies DueReminder
  })
  if (root.count !== reminders.length) throw new Error('REMINDER_RESPONSE_INVALID')
  return {
    schema_version: '0.1',
    mode: 'FOLLOWUP_REMINDER_INBOX',
    count: reminders.length,
    reminders,
  }
}

export async function getDueReminders(): Promise<DueReminder[]> {
  if (!isApiMode) return []
  const response = await fetch(`${apiBaseUrl}/reminders`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
  return validateInbox(await response.json()).reminders
}

export async function acknowledgeDueReminder(reminderId: string): Promise<void> {
  if (!isApiMode) return
  if (!/^mrem_[0-9a-f]{64}$/.test(reminderId)) throw new Error('REMINDER_ID_INVALID')
  const response = await fetch(`${apiBaseUrl}/reminders/${encodeURIComponent(reminderId)}/ack`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: '{}',
  })
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
}
