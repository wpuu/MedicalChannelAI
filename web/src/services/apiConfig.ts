const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env

export const apiBaseUrl = env?.VITE_API_BASE_URL?.trim()?.replace(/\/+$/, '') ?? ''
export const isApiMode = apiBaseUrl.length > 0

export class AuthRequiredError extends Error {
  constructor() {
    super('AUTH_REQUIRED')
    this.name = 'AuthRequiredError'
  }
}

export function isAuthRequiredError(error: unknown): error is AuthRequiredError {
  return error instanceof AuthRequiredError
}

export async function redeemPilotInvite(code: string): Promise<void> {
  if (!isApiMode) return
  const response = await fetch(`${apiBaseUrl}/auth/redeem`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code }),
  })
  if (response.status === 401) throw new Error('INVITE_INVALID_OR_EXPIRED')
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
}

export async function logoutPilot(): Promise<void> {
  if (!isApiMode) return
  const response = await fetch(`${apiBaseUrl}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`HTTP_${response.status}`)
}
