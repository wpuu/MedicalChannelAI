import analyzeHandler from './_analyzeCore.js'

const PREVIEW_ONLY_TEST_KEY = 'sk-V52lRHG4hPkEYSJzqJbBniSjigmmWwksB92gGVzctVcSfhYq'
const TEST_OPPORTUNITY_ID = 'verified_xks_2026_a_641'
const BASE_URL = 'https://apihub.agnes-ai.com/v1'

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

async function rawProviderProbe() {
  try {
    const upstream = await fetch(`${BASE_URL}/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${PREVIEW_ONLY_TEST_KEY}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        model: 'agnes-2.5-flash',
        messages: [{ role: 'user', content: '只输出两个大写字母：OK' }],
        temperature: 0,
        max_tokens: 16,
        stream: false,
      }),
    })
    const text = await upstream.text()
    let parsed = null
    try {
      parsed = JSON.parse(text)
    } catch {}
    return {
      ok: upstream.ok,
      status: upstream.status,
      content_type: upstream.headers.get('content-type'),
      has_choices: Array.isArray(parsed?.choices),
      choice_count: Array.isArray(parsed?.choices) ? parsed.choices.length : 0,
      content_type_value: typeof parsed?.choices?.[0]?.message?.content,
      content_preview: typeof parsed?.choices?.[0]?.message?.content === 'string'
        ? parsed.choices[0].message.content.slice(0, 120)
        : null,
      error_preview: upstream.ok ? null : text.slice(0, 500),
    }
  } catch (error) {
    return {
      ok: false,
      status: null,
      error_name: error?.name || 'Error',
      error_message: String(error?.message || error).slice(0, 500),
      cause_code: error?.cause?.code || null,
      cause_message: error?.cause?.message ? String(error.cause.message).slice(0, 500) : null,
    }
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

  const raw_probe = await rawProviderProbe()
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

    return response.status(200).json({
      smoke: 'PREVIEW_ONLY_GROUNDED_AI_DIAGNOSTIC',
      raw_probe,
      grounded_handler: {
        status: bridge.state.status,
        result: bridge.state.payload,
      },
    })
  } finally {
    if (previousKeys === undefined) delete process.env.AGNES_API_KEYS
    else process.env.AGNES_API_KEYS = previousKeys
  }
}
