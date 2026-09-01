const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env

const SAME_ORIGIN_SNAPSHOT_API = '/api/public-snapshot'

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
 * Default: same-origin `/api/public-snapshot`.
 * The server function reads the bundled snapshot when no remote source is configured,
 * or `VERIFIED_SNAPSHOT_URL` when a remotely refreshed HTTPS snapshot is configured.
 * This keeps frontend code, AI grounding and dynamic data on one snapshot version while
 * allowing data refreshes without a Vercel frontend rebuild.
 *
 * `VITE_VERIFIED_SNAPSHOT_URL` remains an explicit browser-side override for controlled
 * local/testing scenarios; remote browser origins must provide their own CORS policy.
 */
export const verifiedSnapshotUrl =
  normalizeSnapshotUrl(env?.VITE_VERIFIED_SNAPSHOT_URL) ?? SAME_ORIGIN_SNAPSHOT_API

export const usesExternalVerifiedSnapshot = verifiedSnapshotUrl !== SAME_ORIGIN_SNAPSHOT_API
