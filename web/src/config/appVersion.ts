// Bump APP_VERSION whenever production-visible behavior changes.
// Deployment retry marker: 2026-09-01T05:08Z after Vercel Hobby build-rate window reset.
export const APP_VERSION = '0.1.2'

const rawCommit = typeof __BUILD_COMMIT__ === 'string' ? __BUILD_COMMIT__ : ''
export const APP_BUILD_COMMIT = rawCommit && rawCommit !== 'local' ? rawCommit.slice(0, 7) : 'local'
export const APP_BUILD_LABEL = `v${APP_VERSION} · ${APP_BUILD_COMMIT}`
