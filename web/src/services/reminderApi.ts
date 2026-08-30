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

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function validateInbox(value: unknown): ReminderInboxResponse {
  const root = asRecord(value)
  if (
    !root ||
    root.schema_version !== '0.1' ||
    root.mode !== 'FOLLOWUP_REMINDER_INBOX' ||
    !Number.isInteger(root.count) ||
    !Array.isArray(root.reminders)
  ) {
    throw new Error('REMINDER_RESPONSE_INVALID')
  }
  const reminders = root.reminders.map((item) => {
    const row = asRecord(item)
    const facts = asRecord(row?.facts)
    if (
      !row ||
      typeof row.reminder_id !== 'string' ||
      !/^mrem_[0-9a-f]{64}$/.test(row.reminder_id) ||
      typeof row.opportunity_id !== 'string' ||
      typeof row.followup_status !== 'string' ||
      typeof row.remind_at !== 'string' ||
      !facts
    ) {
      throw new Error('REMINDER_RESPONSE_INVALID')
    }
    return {
      reminder_id: row.reminder_id,
      opportunity_id: row.opportunity_id,
      followup_status: row.followup_status,
      remind_at: row.remind_at,
      note: typeof row.note === 'string' ? row.note : null,
      facts: {
        buyer_name: typeof facts.buyer_name === 'string' ? facts.buyer_name : null,
        hospital_name: typeof facts.hospital_name === 'string' ? facts.hospital_name : null,
        project_name: typeof facts.project_name === 'string' ? facts.project_name : null,
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
