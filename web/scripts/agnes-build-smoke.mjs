const key = 'sk-V52lRHG4hPkEYSJzqJbBniSjigmmWwksB92gGVzctVcSfhYq'
const endpoints = [
  'https://apihub.agnes-ai.com/v1/chat/completions',
  'https://apihub.agnes-ai.cn/v1/chat/completions',
]

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
    let payload = null
    try { payload = JSON.parse(text) } catch {}
    console.log('[agnes-build-smoke]', JSON.stringify({
      endpoint_host: new URL(endpoint).host,
      ok: response.ok,
      status: response.status,
      elapsed_ms: Date.now() - started,
      content_type: response.headers.get('content-type'),
      has_choices: Array.isArray(payload?.choices),
      choice_count: Array.isArray(payload?.choices) ? payload.choices.length : 0,
      message_content_type: typeof payload?.choices?.[0]?.message?.content,
      message_preview: typeof payload?.choices?.[0]?.message?.content === 'string'
        ? payload.choices[0].message.content.slice(0, 80)
        : null,
      error_preview: response.ok ? null : text.slice(0, 300),
    }))
  } catch (error) {
    console.log('[agnes-build-smoke]', JSON.stringify({
      endpoint_host: new URL(endpoint).host,
      ok: false,
      status: null,
      elapsed_ms: Date.now() - started,
      error_name: error?.name || 'Error',
      error_message: String(error?.message || error).slice(0, 300),
      cause_code: error?.cause?.code || null,
      cause_message: error?.cause?.message ? String(error.cause.message).slice(0, 300) : null,
    }))
  }
}
