import coreHandler, { config } from './_analyzeCore.js'

export { config }

const PUBLIC_FIRST_PARTY_ORIGIN = 'https://medicalai.qd.je'

function firstHeaderValue(value) {
  if (Array.isArray(value)) return value[0] ?? null
  return typeof value === 'string' ? value : null
}

/**
 * medicalai.qd.je is reverse-proxied through Caddy to Vercel. The browser keeps
 * Origin=https://medicalai.qd.je while the upstream Host becomes a Vercel
 * hostname, so the core same-origin guard would otherwise reject our own UI.
 * Only the exact public first-party Origin is normalized; every other origin
 * continues through the strict core validation unchanged.
 */
export default function handler(request, response) {
  const origin = firstHeaderValue(request.headers?.origin)
  if (origin !== PUBLIC_FIRST_PARTY_ORIGIN) return coreHandler(request, response)

  const normalizedRequest = {
    ...request,
    method: request.method,
    body: request.body,
    headers: {
      ...request.headers,
      host: 'medicalai.qd.je',
      'x-forwarded-host': 'medicalai.qd.je',
    },
  }
  return coreHandler(normalizedRequest, response)
}
