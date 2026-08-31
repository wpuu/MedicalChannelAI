const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env

const LOCAL_SNAPSHOT_URL = '/data/today-actions.public.json'

function normalizeSnapshotUrl(raw: string | undefined): string | null {
  const value = raw?.trim()
  if (!value) return null
  try {
    const url = new URL(value, window.location.origin)
    const isLocalDevelopment =
      (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
      (url.protocol === 'http:' || url.protocol === 'https:')
    if (url.protocol !== 'https:' && !isLocalDevelopment) return null
    return url.toString()
  } catch {
    return null
  }
}

/**
 * Verified-trial snapshot location.
 *
 * Default: bundled `/data/today-actions.public.json`.
 * Optional: set `VITE_VERIFIED_SNAPSHOT_URL` to an externally refreshed HTTPS JSON object.
 * This lets verified data refresh independently from frontend deployments.
 */
export const verifiedSnapshotUrl =
  normalizeSnapshotUrl(env?.VITE_VERIFIED_SNAPSHOT_URL) ?? LOCAL_SNAPSHOT_URL

export const usesExternalVerifiedSnapshot = verifiedSnapshotUrl !== LOCAL_SNAPSHOT_URL
