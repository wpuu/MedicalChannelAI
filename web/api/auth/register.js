import {
  createSession,
  readJsonBody,
  registerUserWithInvite,
  sendJson,
} from '../_auth.js'
import { privateDatabaseConfigured } from '../_privateDb.js'

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }

  const body = readJsonBody(request)
  if (!body) return sendJson(response, 400, { error: 'REQUEST_INVALID' })

  try {
    const user = await registerUserWithInvite({
      inviteCode: body.invite_code,
      username: body.username,
      password: body.password,
    })
    await createSession(user.id, request, response)
    return sendJson(response, 201, {
      schema_version: '0.1',
      user: {
        username: user.username,
        role: user.role,
      },
    })
  } catch (error) {
    const code = error instanceof Error ? error.message : 'REGISTRATION_FAILED'
    if (code === 'INVITE_INVALID_OR_EXPIRED') {
      return sendJson(response, 401, { error: code })
    }
    if (code === 'USERNAME_TAKEN') {
      return sendJson(response, 409, { error: code })
    }
    if (code === 'USERNAME_INVALID' || code === 'PASSWORD_INVALID') {
      return sendJson(response, 400, { error: code })
    }
    console.error('pilot registration failed', { error: code })
    return sendJson(response, 500, { error: 'REGISTRATION_FAILED' })
  }
}
