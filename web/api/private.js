import privateCoreHandler from './_privateCore.js'

function firstQuery(request, key) {
  const raw = request.query?.[key]
  return Array.isArray(raw) ? raw[0] : raw
}

function shouldProjectLightToday(request) {
  if (request.method !== 'GET') return false
  if (firstQuery(request, 'route') !== 'today') return false
  return firstQuery(request, 'include_pool') !== '1'
}

function projectLightTodayPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload
  if (payload.mode !== 'TODAY_ACTIONS') return payload
  if (!Object.prototype.hasOwnProperty.call(payload, 'opportunity_pool')) return payload
  const { opportunity_pool: _fullPool, ...lightPayload } = payload
  return lightPayload
}

export default async function handler(request, response) {
  if (!shouldProjectLightToday(request) || typeof response.json !== 'function') {
    return privateCoreHandler(request, response)
  }

  const originalJson = response.json
  response.json = function projectedJson(payload) {
    return originalJson.call(this, projectLightTodayPayload(payload))
  }
  try {
    return await privateCoreHandler(request, response)
  } finally {
    response.json = originalJson
  }
}
