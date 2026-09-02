import { authenticatedUser, sendJson } from '../_auth.js'
import { privateDatabaseConfigured } from '../_privateDb.js'

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }

  try {
    const user = await authenticatedUser(request)
    if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    return sendJson(response, 200, {
      schema_version: '0.1',
      user: {
        username: user.username,
        display_name: user.display_name,
        role: user.role,
      },
    })
  } catch (error) {
    console.error('session lookup failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'SESSION_LOOKUP_FAILED' })
  }
}
