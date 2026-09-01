// Bump APP_VERSION whenever production-visible behavior changes.
export const APP_VERSION = '0.3.7'

const rawCommit = typeof __BUILD_COMMIT__ === 'string' ? __BUILD_COMMIT__ : ''
export const APP_BUILD_COMMIT = rawCommit && rawCommit !== 'local' ? rawCommit.slice(0, 7) : 'local'
export const APP_BUILD_LABEL = `v${APP_VERSION} · ${APP_BUILD_COMMIT}`
