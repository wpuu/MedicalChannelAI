import { apiBaseUrl, isApiMode } from './apiConfig'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export async function updateTodayLimit(todayLimit: number): Promise<number> {
  if (!isApiMode) throw new Error('API_MODE_REQUIRED')
  const response = await fetch(`${apiBaseUrl}/today`, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ today_limit: todayLimit }),
  })

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new Error(response.ok ? 'TODAY_PREFERENCE_RESPONSE_INVALID' : `HTTP_${response.status}`)
  }
  const root = asRecord(payload)
  if (!response.ok) {
    throw new Error(typeof root?.error === 'string' ? root.error : `HTTP_${response.status}`)
  }
  const value = Number(root?.today_limit)
  if (!Number.isInteger(value) || value < 1 || value > 50) {
    throw new Error('TODAY_PREFERENCE_RESPONSE_INVALID')
  }
  return value
}
