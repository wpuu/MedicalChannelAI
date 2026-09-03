import {
  authenticatedUser,
  clearSessionCookie,
  createSession,
  destroyCurrentSession,
  hashPassword,
  normalizeUsername,
  readJsonBody,
  registerUserWithInvite,
  sendJson,
  sha256,
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

function localScope(userId) {
  return sha256(`pilot-local-scope:v1:${userId}`).slice(0, 32)
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
      user: {
        username: user.username,
        display_name: user.display_name ?? null,
        role: user.role,
        local_scope: localScope(user.id),
      },
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
      SELECT id, username_display, display_name, password_salt, password_hash, role
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
      user: {
        username: user.username_display,
        display_name: user.display_name,
        role: user.role,
        local_scope: localScope(user.id),
      },
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
      user: {
        username: user.username,
        display_name: user.display_name,
        role: user.role,
        local_scope: localScope(user.id),
      },
    })
  } catch (error) {
    console.error('session lookup failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'SESSION_LOOKUP_FAILED' })
  }
}

async function requireUser(request, response) {
  const user = await authenticatedUser(request)
  if (!user) {
    sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    return null
  }
  return user
}

async function exportAccount(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  try {
    const user = await requireUser(request, response)
    if (!user) return
    const sql = privateDb()
    const [accountRows, capabilities, relationships, targetHospitals, preferences, followups, events, feedback] = await Promise.all([
      sql`
        SELECT username_display, display_name, role, status, created_at, updated_at
        FROM private_users WHERE id = ${user.id} LIMIT 1
      `,
      sql`
        SELECT keyword, capability_type, created_at, updated_at
        FROM private_product_capabilities
        WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
        ORDER BY created_at ASC
      `,
      sql`
        SELECT hospital, department, relationship_strength, created_at, updated_at
        FROM private_hospital_relationships
        WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
        ORDER BY created_at ASC
      `,
      sql`
        SELECT hospital, department, created_at, updated_at
        FROM private_target_hospitals
        WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
        ORDER BY created_at ASC
      `,
      sql`
        SELECT can_find_manufacturer, can_partner_channel, can_handle_lease, updated_at
        FROM private_user_preferences WHERE user_id = ${user.id} LIMIT 1
      `,
      sql`
        SELECT id, opportunity_id, status, remind_at, public_snapshot, created_at, updated_at
        FROM private_followups
        WHERE user_id = ${user.id} AND organization_id = ${user.organization_id}
        ORDER BY created_at ASC
      `,
      sql`
        SELECT followup_id, mutation_id, status, note, reason, remind_at, created_at
        FROM private_followup_events
        WHERE user_id = ${user.id}
        ORDER BY created_at ASC
      `,
      sql`
        SELECT opportunity_id, value, created_at, updated_at
        FROM private_recommendation_feedback
        WHERE user_id = ${user.id}
        ORDER BY created_at ASC
      `,
    ])
    const account = accountRows[0]
    if (!account) return sendJson(response, 404, { error: 'ACCOUNT_NOT_FOUND' })
    return sendJson(response, 200, {
      schema_version: '0.1',
      exported_at: new Date().toISOString(),
      account: {
        username: account.username_display,
        display_name: account.display_name,
        role: account.role,
        status: account.status,
        created_at: account.created_at,
        updated_at: account.updated_at,
      },
      private_profile: {
        product_capabilities: capabilities,
        hospital_relationships: relationships,
        target_hospitals: targetHospitals,
        preferences: preferences[0] || null,
      },
      followups,
      followup_events: events,
      recommendation_feedback: feedback,
    })
  } catch (error) {
    console.error('account export failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'ACCOUNT_EXPORT_FAILED' })
  }
}

async function deleteAccount(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  const body = readJsonBody(request)
  const password = validatePassword(body?.password)
  if (!password) return sendJson(response, 400, { error: 'PASSWORD_INVALID' })

  try {
    const user = await requireUser(request, response)
    if (!user) return
    const sql = privateDb()
    const rows = await sql`
      SELECT password_salt, password_hash
      FROM private_users
      WHERE id = ${user.id} AND status = 'ACTIVE'
      LIMIT 1
    `
    const account = rows[0]
    if (!account || !await verifyPassword(password, account.password_salt, account.password_hash)) {
      return sendJson(response, 401, { error: 'PASSWORD_CONFIRMATION_FAILED' })
    }

    await sql.begin(async (tx) => {
      await tx`DELETE FROM private_users WHERE id = ${user.id}`
      const remaining = await tx`
        SELECT count(*)::int AS count
        FROM private_users
        WHERE organization_id = ${user.organization_id}
      `
      if (Number(remaining[0]?.count || 0) === 0) {
        await tx`DELETE FROM private_organizations WHERE id = ${user.organization_id}`
      }
    })
    clearSessionCookie(request, response)
    return sendJson(response, 200, {
      schema_version: '0.1',
      deleted: true,
    })
  } catch (error) {
    console.error('account deletion failed', { error: error instanceof Error ? error.message : 'UNKNOWN' })
    return sendJson(response, 500, { error: 'ACCOUNT_DELETE_FAILED' })
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
  if (route === 'export') return exportAccount(request, response)
  if (route === 'delete') return deleteAccount(request, response)
  return sendJson(response, 404, { error: 'AUTH_ROUTE_NOT_FOUND' })
}
