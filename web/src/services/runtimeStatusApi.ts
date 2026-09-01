export interface RuntimeStatus {
  schema_version: '0.1'
  service: 'MedicalChannelAI'
  ready: boolean
  degraded: boolean
  production_ready: false
  ai: {
    configured: boolean
  }
  snapshot: {
    available: boolean
    source_mode: 'BUNDLED' | 'REMOTE' | 'UNAVAILABLE'
    snapshot_as_of: string | null
    freshness: 'FRESH' | 'STALE' | 'INVALID' | 'UNAVAILABLE'
    age_minutes: number | null
    stale_after_minutes: number
    today_card_count: number
    opportunity_pool_count: number
  }
}

const STATUS_URL = '/api/status'
const CACHE_TTL_MS = 60_000

let cached: { expiresAt: number; value: RuntimeStatus } | null = null
let inFlight: Promise<RuntimeStatus | null> | null = null

function isRuntimeStatus(value: unknown): value is RuntimeStatus {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const row = value as Record<string, unknown>
  const ai = row.ai as Record<string, unknown> | undefined
  const snapshot = row.snapshot as Record<string, unknown> | undefined
  return (
    row.schema_version === '0.1' &&
    row.service === 'MedicalChannelAI' &&
    typeof row.ready === 'boolean' &&
    typeof row.degraded === 'boolean' &&
    row.production_ready === false &&
    Boolean(ai) &&
    typeof ai?.configured === 'boolean' &&
    Boolean(snapshot) &&
    typeof snapshot?.available === 'boolean' &&
    ['BUNDLED', 'REMOTE', 'UNAVAILABLE'].includes(String(snapshot?.source_mode)) &&
    (snapshot?.snapshot_as_of === null || typeof snapshot?.snapshot_as_of === 'string') &&
    ['FRESH', 'STALE', 'INVALID', 'UNAVAILABLE'].includes(String(snapshot?.freshness)) &&
    (snapshot?.age_minutes === null || typeof snapshot?.age_minutes === 'number') &&
    typeof snapshot?.stale_after_minutes === 'number' &&
    typeof snapshot?.today_card_count === 'number' &&
    typeof snapshot?.opportunity_pool_count === 'number'
  )
}

async function fetchRuntimeStatus(): Promise<RuntimeStatus | null> {
  try {
    const response = await fetch(STATUS_URL, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    const payload: unknown = await response.json()
    if (!isRuntimeStatus(payload)) return null
    return payload
  } catch {
    return null
  }
}

export async function getRuntimeStatus(force = false): Promise<RuntimeStatus | null> {
  const now = Date.now()
  if (!force && cached && cached.expiresAt > now) return cached.value
  if (!force && inFlight) return inFlight

  const request = fetchRuntimeStatus().then((value) => {
    if (value) {
      cached = {
        expiresAt: Date.now() + CACHE_TTL_MS,
        value,
      }
    }
    return value
  })
  inFlight = request
  try {
    return await request
  } finally {
    if (inFlight === request) inFlight = null
  }
}

export function clearRuntimeStatusCacheForTests(): void {
  cached = null
  inFlight = null
}
