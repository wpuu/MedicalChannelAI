import {
  createSession,
  hashPassword,
  normalizeUsername,
  readJsonBody,
  sendJson,
  validatePassword,
  verifyPassword,
} from '../_auth.js'
import {
  ensurePrivateSchema,
  privateDatabaseConfigured,
  privateDb,
} from '../_privateDb.js'

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }

  const body = readJsonBody(request)
  const username = normalizeUsername(body?.username)
  const password = validatePassword(body?.password)
  if (!username || !password) {
    return sendJson(response, 401, { error: 'INVALID_CREDENTIALS' })
  }

  try {
    await ensurePrivateSchema()
    const sql = privateDb()
    const rows = await sql`
      SELECT id, username_display, password_salt, password_hash, role
      FROM private_users
      WHERE username_normalized = ${username.normalized}
        AND status = 'ACTIVE'
      LIMIT 1
    `
    const user = rows[0] || null
    const passwordOk = user
      ? await verifyPassword(password, user.password_salt, user.password_hash)
      : Boolean(await hashPassword(password)) && false

    if (!user || !passwordOk) {
      return sendJson(response, 401, { error: 'INVALID_CREDENTIALS' })
    }

    await createSession(user.id, request, response)
    return sendJson(response, 200, {
      schema_version: '0.1',
      user: {
        username: user.username_display,
        role: user.role,
      },
    })
  } catch (error) {
    console.error('pilot login failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return sendJson(response, 500, { error: 'LOGIN_FAILED' })
  }
}
