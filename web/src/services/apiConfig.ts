const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env

export type WebBuildMode = 'demo' | 'pilot' | 'unspecified'

const rawBuildMode = env?.VITE_BUILD_MODE?.trim()?.toLowerCase() ?? ''
export const webBuildMode: WebBuildMode =
  rawBuildMode === 'demo' || rawBuildMode === 'pilot' ? rawBuildMode : 'unspecified'

export const apiBaseUrl = env?.VITE_API_BASE_URL?.trim()?.replace(/\/+$/, '') ?? ''
export const isApiMode = apiBaseUrl.length > 0
export const PILOT_SESSION_CHANGE_KEY = 'medicalchannelai.pilot.session-change.v1'

if (webBuildMode === 'demo' && isApiMode) {
  throw new Error('WEB_BUILD_MODE_MISMATCH: demo build must not configure VITE_API_BASE_URL')
}
if (webBuildMode === 'pilot' && apiBaseUrl !== '/api') {
  throw new Error('WEB_BUILD_MODE_MISMATCH: pilot build requires VITE_API_BASE_URL=/api')
}

export interface PilotUser {
  username: string
  display_name: string | null
  role: 'OWNER' | 'ADMIN' | 'MEMBER'
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function parsePilotUser(value: unknown): PilotUser {
  const row = asRecord(value)
  if (
    !row ||
    typeof row.username !== 'string' ||
    !(row.display_name === null || typeof row.display_name === 'string') ||
    !['OWNER', 'ADMIN', 'MEMBER'].includes(String(row.role))
  ) {
    throw new Error('AUTH_RESPONSE_INVALID')
  }
  return {
    username: row.username,
    display_name: row.display_name,
    role: row.role as PilotUser['role'],
  }
}

export function signalPilotSessionChanged(): void {
  if (typeof window === 'undefined') return
  try {
    const nonce = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2)
    window.localStorage.setItem(PILOT_SESSION_CHANGE_KEY, `${Date.now()}:${nonce}`)
  } catch {
    // Cross-tab coordination is a defense-in-depth signal. The server session
    // remains authoritative even when browser storage is unavailable.
  }
}

async function authError(response: Response): Promise<Error> {
  try {
    const root = asRecord(await response.json())
    if (root && typeof root.error === 'string') return new Error(root.error)
  } catch {
    // Fall back to HTTP status below.
  }
  return new Error(`HTTP_${response.status}`)
}

export function isAuthRequiredError(error: unknown): boolean {
  return error instanceof Error &&
    (error.message === 'AUTH_REQUIRED' || error.message === 'HTTP_401')
}

export async function registerPilotAccount(input: {
  inviteCode: string
  username: string
  password: string
}): Promise<PilotUser> {
  if (!isApiMode) throw new Error('API_MODE_REQUIRED')
  const response = await fetch(`${apiBaseUrl}/auth/register`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      invite_code: input.inviteCode,
      username: input.username,
      password: input.password,
    }),
  })
  if (!response.ok) throw await authError(response)
  const root = asRecord(await response.json())
  const user = parsePilotUser(root?.user)
  signalPilotSessionChanged()
  return user
}

export async function loginPilotAccount(input: {
  username: string
  password: string
}): Promise<PilotUser> {
  if (!isApiMode) throw new Error('API_MODE_REQUIRED')
  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })
  if (!response.ok) throw await authError(response)
  const root = asRecord(await response.json())
  const user = asRecord(root?.user)
  const parsed = parsePilotUser({ ...user, display_name: user?.display_name ?? null })
  signalPilotSessionChanged()
  return parsed
}

export async function getPilotSession(): Promise<PilotUser> {
  if (!isApiMode) throw new Error('API_MODE_REQUIRED')
  const response = await fetch(`${apiBaseUrl}/auth/me`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await authError(response)
  const root = asRecord(await response.json())
  return parsePilotUser(root?.user)
}

export async function logoutPilot(): Promise<void> {
  if (!isApiMode) return
  const response = await fetch(`${apiBaseUrl}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await authError(response)
  signalPilotSessionChanged()
}
