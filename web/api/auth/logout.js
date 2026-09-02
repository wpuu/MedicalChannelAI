import { destroyCurrentSession, sendJson } from '../_auth.js'
import { privateDatabaseConfigured } from '../_privateDb.js'

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }

  try {
    await destroyCurrentSession(request, response)
    return sendJson(response, 200, { schema_version: '0.1', logged_out: true })
  } catch (error) {
    console.error('pilot logout failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'LOGOUT_FAILED' })
  }
}
