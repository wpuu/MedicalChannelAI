import { getCache } from '@vercel/functions'

const CROSS_RUNTIME_KEY = 'medicalchannelai-cross-runtime-v1'

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.status(status).json(payload)
}

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }

  try {
    const cache = getCache()
    const value = await cache.get(CROSS_RUNTIME_KEY)
    const readable =
      value &&
      typeof value === 'object' &&
      value.probe === 'python-to-node-runtime-cache'
    return sendJson(response, readable ? 200 : 503, {
      schema_version: '0.1',
      service: 'MedicalChannelAI',
      cross_runtime_cache: {
        readable: Boolean(readable),
        producer: readable ? 'python' : null,
        consumer: 'node',
      },
    })
  } catch {
    return sendJson(response, 503, {
      schema_version: '0.1',
      service: 'MedicalChannelAI',
      cross_runtime_cache: {
        readable: false,
        producer: null,
        consumer: 'node',
      },
    })
  }
}
