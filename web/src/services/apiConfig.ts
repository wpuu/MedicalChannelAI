const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env

export type WebBuildMode = 'demo' | 'pilot' | 'unspecified'

const rawBuildMode = env?.VITE_BUILD_MODE?.trim()?.toLowerCase() ?? ''
export const webBuildMode: WebBuildMode =
  rawBuildMode === 'demo' || rawBuildMode === 'pilot' ? rawBuildMode : 'unspecified'

export const apiBaseUrl = env?.VITE_API_BASE_URL?.trim()?.replace(/\/+$/, '') ?? ''
export const isApiMode = apiBaseUrl.length > 0

if (webBuildMode === 'demo' && isApiMode) {
  throw new Error('WEB_BUILD_MODE_MISMATCH: demo build must not configure VITE_API_BASE_URL')
}
if (webBuildMode === 'pilot' && apiBaseUrl !== '/api') {
  throw new Error('WEB_BUILD_MODE_MISMATCH: pilot build requires VITE_API_BASE_URL=/api')
}

export function isAuthRequiredError(error: unknown): boolean {
  return error instanceof Error &&
    (error.message === 'AUTH_REQUIRED' || error.message === 'HTTP_401')
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
