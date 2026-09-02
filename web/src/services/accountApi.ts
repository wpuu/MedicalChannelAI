import { API_BASE_URL } from './apiConfig'

async function accountRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  const payload = await response.json().catch(() => null) as { error?: string } | null
  if (!response.ok) {
    throw new Error(payload?.error || `HTTP_${response.status}`)
  }
  return payload as T
}

export async function exportPilotAccountData(): Promise<Record<string, unknown>> {
  return accountRequest<Record<string, unknown>>('/account/export')
}

export async function deletePilotAccount(password: string): Promise<void> {
  await accountRequest<{ deleted: true }>('/account/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

export function downloadAccountExport(payload: Record<string, unknown>): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `medicalchannelai-account-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
