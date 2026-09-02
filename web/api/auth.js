import {
  authenticatedUser,
  createSession,
  destroyCurrentSession,
  hashPassword,
  normalizeUsername,
  readJsonBody,
  registerUserWithInvite,
  sendJson,
  validatePassword,
  verifyPassword,
} from './_auth.js'
import {
  ensurePrivateSchema,
  privateDatabaseConfigured,
  privateDb,
} from './_privateDb.js'

function routeName(request) {
  const raw = Array.isArray(request.query?.route) ? request.query.route[0] : request.query?.route
  return typeof raw === 'string' ? raw.trim() : ''
}

async function register(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
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
      user: { username: user.username, role: user.role },
    })
  } catch (error) {
    const code = error instanceof Error ? error.message : 'REGISTRATION_FAILED'
    if (code === 'INVITE_INVALID_OR_EXPIRED') return sendJson(response, 401, { error: code })
    if (code === 'USERNAME_TAKEN') return sendJson(response, 409, { error: code })
    if (code === 'USERNAME_INVALID' || code === 'PASSWORD_INVALID') {
      return sendJson(response, 400, { error: code })
    }
    console.error('pilot registration failed', { error: code })
    return sendJson(response, 500, { error: 'REGISTRATION_FAILED' })
  }
}

async function login(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  const body = readJsonBody(request)
  const username = normalizeUsername(body?.username)
  const password = validatePassword(body?.password)
  if (!username || !password) return sendJson(response, 401, { error: 'INVALID_CREDENTIALS' })

  try {
    await ensurePrivateSchema()
    const sql = privateDb()
    const rows = await sql`
      SELECT id, username_display, password_salt, password_hash, role
      FROM private_users
      WHERE username_normalized = ${username.normalized} AND status = 'ACTIVE'
      LIMIT 1
    `
    const user = rows[0] || null
    const passwordOk = user
      ? await verifyPassword(password, user.password_salt, user.password_hash)
      : Boolean(await hashPassword(password)) && false
    if (!user || !passwordOk) return sendJson(response, 401, { error: 'INVALID_CREDENTIALS' })

    await createSession(user.id, request, response)
    return sendJson(response, 200, {
      schema_version: '0.1',
      user: { username: user.username_display, role: user.role },
    })
  } catch (error) {
    console.error('pilot login failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'LOGIN_FAILED' })
  }
}

async function logout(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  try {
    await destroyCurrentSession(request, response)
    return sendJson(response, 200, { schema_version: '0.1', logged_out: true })
  } catch (error) {
    console.error('pilot logout failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'LOGOUT_FAILED' })
  }
}

async function me(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  try {
    const user = await authenticatedUser(request)
    if (!user) return sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    return sendJson(response, 200, {
      schema_version: '0.1',
      user: { username: user.username, display_name: user.display_name, role: user.role },
    })
  } catch (error) {
    console.error('session lookup failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'SESSION_LOOKUP_FAILED' })
  }
}

export default async function handler(request, response) {
  if (!privateDatabaseConfigured()) {
    return sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
  }
  const route = routeName(request)
  if (route === 'register') return register(request, response)
  if (route === 'login') return login(request, response)
  if (route === 'logout') return logout(request, response)
  if (route === 'me') return me(request, response)
  return sendJson(response, 404, { error: 'AUTH_ROUTE_NOT_FOUND' })
}
