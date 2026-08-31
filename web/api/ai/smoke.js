import analyzeHandler from './_analyzeCore.js'

const PREVIEW_ONLY_TEST_KEY = 'sk-V52lRHG4hPkEYSJzqJbBniSjigmmWwksB92gGVzctVcSfhYq'
const TEST_OPPORTUNITY_ID = 'verified_xks_2026_a_641'

function internalResponse() {
  const state = { status: 200, payload: null }
  return {
    state,
    setHeader() {},
    status(code) {
      state.status = code
      return this
    },
    json(payload) {
      state.payload = payload
      return payload
    },
  }
}

export default async function handler(request, response) {
  if (process.env.VERCEL_ENV !== 'preview') {
    return response.status(404).json({ error: 'NOT_FOUND' })
  }
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return response.status(405).json({ error: 'METHOD_NOT_ALLOWED' })
  }

  const previousKeys = process.env.AGNES_API_KEYS
  if (!previousKeys) process.env.AGNES_API_KEYS = PREVIEW_ONLY_TEST_KEY

  try {
    const bridge = internalResponse()
    await analyzeHandler({
      method: 'POST',
      headers: {
        origin: 'https://preview-smoke.local',
        host: 'preview-smoke.local',
        'x-forwarded-host': 'preview-smoke.local',
        'x-forwarded-for': '127.0.0.1',
      },
      body: { opportunity_id: TEST_OPPORTUNITY_ID },
    }, bridge)

    return response.status(bridge.state.status).json({
      smoke: 'PREVIEW_ONLY_GROUNDED_AI',
      result: bridge.state.payload,
    })
  } finally {
    if (previousKeys === undefined) delete process.env.AGNES_API_KEYS
    else process.env.AGNES_API_KEYS = previousKeys
  }
}
