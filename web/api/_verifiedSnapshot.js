import bundledSnapshot from '../public/data/today-actions.public.json' with { type: 'json' }

const REMOTE_CACHE_TTL_MS = 60 * 1000
const REMOTE_TIMEOUT_MS = 6000
const MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024

let remoteCache = null

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function configuredRemoteUrl() {
  const raw = (
    process.env.VERIFIED_SNAPSHOT_URL ||
    process.env.VITE_VERIFIED_SNAPSHOT_URL ||
    ''
  ).trim()
  if (!raw) return null

  let url
  try {
    url = new URL(raw)
  } catch {
    throw new Error('VERIFIED_SNAPSHOT_URL_INVALID')
  }
  const localDevelopment =
    process.env.NODE_ENV !== 'production' &&
    (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
    (url.protocol === 'http:' || url.protocol === 'https:')
  if (url.protocol !== 'https:' && !localDevelopment) {
    throw new Error('VERIFIED_SNAPSHOT_URL_NOT_HTTPS')
  }
  return url.toString()
}

export function validateVerifiedSnapshot(value) {
  const snapshot = asObject(value)
  if (!snapshot) throw new Error('VERIFIED_SNAPSHOT_INVALID')
  if (snapshot.schema_version !== '0.1' || snapshot.mode !== 'TODAY_ACTIONS') {
    throw new Error('VERIFIED_SNAPSHOT_SCHEMA_INVALID')
  }
  if (
    typeof snapshot.snapshot_as_of !== 'string' ||
    Number.isNaN(Date.parse(snapshot.snapshot_as_of))
  ) {
    throw new Error('VERIFIED_SNAPSHOT_AS_OF_INVALID')
  }
  if (!Array.isArray(snapshot.cards) || snapshot.cards.length > 500) {
    throw new Error('VERIFIED_SNAPSHOT_CARDS_INVALID')
  }
  return snapshot
}

export function bundledVerifiedSnapshot() {
  return validateVerifiedSnapshot(bundledSnapshot)
}

export async function loadVerifiedSnapshot() {
  const remoteUrl = configuredRemoteUrl()
  if (!remoteUrl) return bundledVerifiedSnapshot()

  const now = Date.now()
  if (remoteCache?.url === remoteUrl && remoteCache.expiresAt > now) {
    return remoteCache.snapshot
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REMOTE_TIMEOUT_MS)
  try {
    const response = await fetch(remoteUrl, {
      method: 'GET',
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!response.ok) throw new Error(`VERIFIED_SNAPSHOT_HTTP_${response.status}`)

    const declaredLength = Number(response.headers.get('content-length') || '0')
    if (declaredLength > MAX_SNAPSHOT_BYTES) {
      throw new Error('VERIFIED_SNAPSHOT_TOO_LARGE')
    }
    const text = await response.text()
    if (Buffer.byteLength(text, 'utf8') > MAX_SNAPSHOT_BYTES) {
      throw new Error('VERIFIED_SNAPSHOT_TOO_LARGE')
    }
    const snapshot = validateVerifiedSnapshot(JSON.parse(text))
    remoteCache = {
      url: remoteUrl,
      expiresAt: now + REMOTE_CACHE_TTL_MS,
      snapshot,
    }
    return snapshot
  } finally {
    clearTimeout(timeout)
  }
}

export function verifiedSnapshotSourceMode() {
  return configuredRemoteUrl() ? 'REMOTE' : 'BUNDLED'
}

export function clearVerifiedSnapshotCacheForTests() {
  remoteCache = null
}
