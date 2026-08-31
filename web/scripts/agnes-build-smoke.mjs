const key = 'sk-V52lRHG4hPkEYSJzqJbBniSjigmmWwksB92gGVzctVcSfhYq'
const endpoints = [
  'https://apihub.agnes-ai.com/v1/chat/completions',
  'https://apihub.agnes-ai.cn/v1/chat/completions',
]

function summarizeResponse(endpoint, response, text, elapsedMs) {
  let payload = null
  try { payload = JSON.parse(text) } catch {}
  return {
    endpoint_host: new URL(endpoint).host,
    ok: response.ok,
    status: response.status,
    elapsed_ms: elapsedMs,
    content_type: response.headers.get('content-type'),
    has_choices: Array.isArray(payload?.choices),
    choice_count: Array.isArray(payload?.choices) ? payload.choices.length : 0,
    message_content_type: typeof payload?.choices?.[0]?.message?.content,
    message_length: typeof payload?.choices?.[0]?.message?.content === 'string'
      ? payload.choices[0].message.content.length
      : null,
    message_preview: typeof payload?.choices?.[0]?.message?.content === 'string'
      ? payload.choices[0].message.content.slice(0, 300)
      : null,
    error_preview: response.ok ? null : text.slice(0, 500),
  }
}

for (const endpoint of endpoints) {
  const started = Date.now()
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${key}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        model: 'agnes-2.5-flash',
        messages: [{ role: 'user', content: 'Reply exactly OK' }],
        temperature: 0,
        max_tokens: 16,
        stream: false,
      }),
    })
    const text = await response.text()
    console.log('[agnes-build-smoke]', JSON.stringify(summarizeResponse(endpoint, response, text, Date.now() - started)))
  } catch (error) {
    console.log('[agnes-build-smoke]', JSON.stringify({
      endpoint_host: new URL(endpoint).host,
      ok: false,
      status: null,
      elapsed_ms: Date.now() - started,
      error_name: error?.name || 'Error',
      error_message: String(error?.message || error).slice(0, 500),
      cause_code: error?.cause?.code || null,
      cause_message: error?.cause?.message ? String(error.cause.message).slice(0, 500) : null,
    }))
  }
}

const realFetch = globalThis.fetch
globalThis.fetch = async (...args) => {
  const started = Date.now()
  const response = await realFetch(...args)
  const url = typeof args[0] === 'string' ? args[0] : args[0]?.url
  if (typeof url === 'string' && url.includes('agnes-ai.') && url.includes('/chat/completions')) {
    const clone = response.clone()
    const text = await clone.text()
    console.log('[agnes-handler-upstream]', JSON.stringify(summarizeResponse(url, response, text, Date.now() - started)))
  }
  return response
}

const previousKeys = process.env.AGNES_API_KEYS
process.env.AGNES_API_KEYS = key
try {
  const { default: analyzeHandler } = await import('../api/ai/_analyzeCore.js')
  const state = { status: 200, payload: null }
  const response = {
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
  await analyzeHandler({
    method: 'POST',
    headers: {
      origin: 'https://build-smoke.local',
      host: 'build-smoke.local',
      'x-forwarded-host': 'build-smoke.local',
      'x-forwarded-for': '127.0.0.1',
    },
    body: { opportunity_id: 'verified_xks_2026_a_641' },
  }, response)
  console.log('[agnes-handler-smoke]', JSON.stringify({ status: state.status, payload: state.payload }))
} catch (error) {
  console.log('[agnes-handler-smoke]', JSON.stringify({
    status: null,
    error_name: error?.name || 'Error',
    error_message: String(error?.message || error).slice(0, 500),
  }))
} finally {
  globalThis.fetch = realFetch
  if (previousKeys === undefined) delete process.env.AGNES_API_KEYS
  else process.env.AGNES_API_KEYS = previousKeys
}
