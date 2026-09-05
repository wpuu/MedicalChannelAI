import {
  createHash,
  randomBytes,
  randomUUID,
  scrypt as scryptCallback,
  timingSafeEqual,
} from 'node:crypto'
import { promisify } from 'node:util'
import { ensurePrivateSchema, privateDb } from './_privateDb.js'

const scrypt = promisify(scryptCallback)
const SESSION_COOKIE = 'medopp_session'
const SESSION_DAYS = 30
const SESSION_TOUCH_INTERVAL_MS = 10 * 60 * 1000
const SHORT_INVITE_RE = /^[A-Za-z0-9]{6,8}$/

export function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.setHeader('Referrer-Policy', 'no-referrer')
  response.status(status).json(payload)
}

export function readJsonBody(request) {
  if (request.body && typeof request.body === 'object' && !Array.isArray(request.body)) {
    return request.body
  }
  if (typeof request.body === 'string' && request.body.length <= 16_384) {
    try {
      const parsed = JSON.parse(request.body)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return null
}

export function normalizeUsername(value) {
  const text = String(value || '').trim()
  if (!/^[A-Za-z0-9._-]{4,32}$/.test(text)) return null
  return { display: text, normalized: text.toLowerCase() }
}

export function validatePassword(value) {
  const password = String(value || '')
  if (password.length < 10 || password.length > 128) return null
  return password
}

export function sha256(value) {
  return createHash('sha256').update(String(value), 'utf8').digest('hex')
}

export function normalizeInviteCode(value) {
  const text = String(value || '').trim()
  if (SHORT_INVITE_RE.test(text)) return text.toUpperCase()
  if (text.length >= 24 && text.length <= 512) return text
  return null
}

export async function hashPassword(password) {
  const salt = randomBytes(16)
  const derived = await scrypt(password, salt, 64, {
    N: 32768,
    r: 8,
    p: 1,
    maxmem: 64 * 1024 * 1024,
  })
  return {
    salt: salt.toString('base64url'),
    hash: Buffer.from(derived).toString('base64url'),
  }
}

export async function verifyPassword(password, saltText, hashText) {
  try {
    const salt = Buffer.from(saltText, 'base64url')
    const expected = Buffer.from(hashText, 'base64url')
    if (salt.length < 16 || expected.length !== 64) return false
    const actual = Buffer.from(await scrypt(password, salt, 64, {
      N: 32768,
      r: 8,
      p: 1,
      maxmem: 64 * 1024 * 1024,
    }))
    return actual.length === expected.length && timingSafeEqual(actual, expected)
  } catch {
    return false
  }
}

function parseCookies(request) {
  const header = String(request.headers?.cookie || '')
  const result = {}
  for (const part of header.split(';')) {
    const index = part.indexOf('=')
    if (index <= 0) continue
    const key = part.slice(0, index).trim()
    const value = part.slice(index + 1).trim()
    if (!key) continue
    try {
      result[key] = decodeURIComponent(value)
    } catch {
      result[key] = value
    }
  }
  return result
}

function cookieSecure(request) {
  if (process.env.VERCEL) return true
  const forwarded = String(request.headers?.['x-forwarded-proto'] || '').toLowerCase()
  return forwarded === 'https'
}

export function clearSessionCookie(request, response) {
  const secure = cookieSecure(request) ? '; Secure' : ''
  response.setHeader(
    'Set-Cookie',
    `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`,
  )
}

export async function createSession(userId, request, response) {
  await ensurePrivateSchema()
  const sql = privateDb()
  const rawToken = randomBytes(32).toString('base64url')
  const tokenHash = sha256(rawToken)
  const sessionId = randomUUID()
  const expiresAt = new Date(Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000)
  await sql`DELETE FROM private_sessions WHERE expires_at <= now()`
  await sql`
    INSERT INTO private_sessions (id, user_id, token_hash, expires_at)
    VALUES (${sessionId}, ${userId}, ${tokenHash}, ${expiresAt.toISOString()})
  `
  const secure = cookieSecure(request) ? '; Secure' : ''
  response.setHeader(
    'Set-Cookie',
    `${SESSION_COOKIE}=${encodeURIComponent(rawToken)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_DAYS * 24 * 60 * 60}${secure}`,
  )
}

export async function destroyCurrentSession(request, response) {
  await ensurePrivateSchema()
  const rawToken = parseCookies(request)[SESSION_COOKIE]
  if (rawToken) {
    const sql = privateDb()
    await sql`DELETE FROM private_sessions WHERE token_hash = ${sha256(rawToken)}`
  }
  clearSessionCookie(request, response)
}

export async function authenticatedUser(request) {
  await ensurePrivateSchema()
  const rawToken = parseCookies(request)[SESSION_COOKIE]
  if (!rawToken) return null
  const sql = privateDb()
  const tokenHash = sha256(rawToken)
  const rows = await sql`
    SELECT
      u.id,
      u.organization_id,
      u.username_display,
      u.role,
      u.display_name,
      s.id AS session_id,
      s.last_seen_at
    FROM private_sessions s
    JOIN private_users u ON u.id = s.user_id
    WHERE s.token_hash = ${tokenHash}
      AND s.expires_at > now()
      AND u.status = 'ACTIVE'
    LIMIT 1
  `
  const user = rows[0]
  if (!user) return null

  const lastSeenAt = new Date(user.last_seen_at).getTime()
  const touchDue = !Number.isFinite(lastSeenAt) || lastSeenAt < Date.now() - SESSION_TOUCH_INTERVAL_MS
  if (touchDue) {
    await sql`
      UPDATE private_sessions
      SET last_seen_at = now()
      WHERE id = ${user.session_id}
        AND last_seen_at < now() - interval '10 minutes'
    `
  }

  return {
    id: user.id,
    organization_id: user.organization_id,
    username: user.username_display,
    role: user.role,
    display_name: user.display_name,
  }
}

export function bootstrapInviteHashes() {
  return String(process.env.PILOT_INVITE_CODES || '')
    .split(/[\n,;]+/)
    .map(normalizeInviteCode)
    .filter(Boolean)
    .map(sha256)
}

function inviteExpired(invitation) {
  return Boolean(
    invitation?.expires_at && new Date(invitation.expires_at).getTime() <= Date.now(),
  )
}

export async function registerUserWithInvite({ inviteCode, username, password }) {
  await ensurePrivateSchema()
  const normalizedUsername = normalizeUsername(username)
  const validPassword = validatePassword(password)
  const normalizedInvite = normalizeInviteCode(inviteCode)
  if (!normalizedUsername) throw new Error('USERNAME_INVALID')
  if (!validPassword) throw new Error('PASSWORD_INVALID')
  if (!normalizedInvite) throw new Error('INVITE_INVALID_OR_EXPIRED')

  const inviteHash = sha256(normalizedInvite)
  const bootstrapAllowed = bootstrapInviteHashes().includes(inviteHash)
  const passwordRecord = await hashPassword(validPassword)
  const sql = privateDb()
  const userId = randomUUID()

  try {
    return await sql.begin(async (tx) => {
      const inviteRows = await tx`
        SELECT code_hash, organization_id, expires_at, used_by, used_at
        FROM private_pilot_invites
        WHERE code_hash = ${inviteHash}
        FOR UPDATE
      `
      const invitation = inviteRows[0] || null
      if (invitation && (invitation.used_at || invitation.used_by || inviteExpired(invitation))) {
        throw new Error('INVITE_INVALID_OR_EXPIRED')
      }
      if (!invitation && !bootstrapAllowed) {
        throw new Error('INVITE_INVALID_OR_EXPIRED')
      }

      const duplicate = await tx`
        SELECT id FROM private_users
        WHERE username_normalized = ${normalizedUsername.normalized}
        LIMIT 1
      `
      if (duplicate.length) throw new Error('USERNAME_TAKEN')

      const organizationId = invitation?.organization_id || randomUUID()
      const createsOrganization = !invitation?.organization_id
      if (createsOrganization) {
        await tx`
          INSERT INTO private_organizations (id, name)
          VALUES (${organizationId}, ${`${normalizedUsername.display} 的团队`})
        `
      }

      await tx`
        INSERT INTO private_users (
          id, organization_id, username_normalized, username_display,
          password_salt, password_hash, role
        ) VALUES (
          ${userId}, ${organizationId}, ${normalizedUsername.normalized}, ${normalizedUsername.display},
          ${passwordRecord.salt}, ${passwordRecord.hash}, ${createsOrganization ? 'OWNER' : 'MEMBER'}
        )
      `

      if (invitation) {
        const claimed = await tx`
          UPDATE private_pilot_invites
          SET organization_id = ${organizationId}, used_by = ${userId}, used_at = now()
          WHERE code_hash = ${inviteHash}
            AND used_at IS NULL
            AND used_by IS NULL
            AND (expires_at IS NULL OR expires_at > now())
          RETURNING code_hash
        `
        if (claimed.length !== 1) throw new Error('INVITE_INVALID_OR_EXPIRED')
      } else {
        const claimed = await tx`
          INSERT INTO private_pilot_invites (
            code_hash, organization_id, used_by, used_at
          ) VALUES (
            ${inviteHash}, ${organizationId}, ${userId}, now()
          )
          ON CONFLICT (code_hash) DO NOTHING
          RETURNING code_hash
        `
        if (claimed.length !== 1) throw new Error('INVITE_INVALID_OR_EXPIRED')
      }

      return {
        id: userId,
        organization_id: organizationId,
        username: normalizedUsername.display,
        role: createsOrganization ? 'OWNER' : 'MEMBER',
      }
    })
  } catch (error) {
    if (error instanceof Error && [
      'INVITE_INVALID_OR_EXPIRED',
      'USERNAME_TAKEN',
      'USERNAME_INVALID',
      'PASSWORD_INVALID',
    ].includes(error.message)) {
      throw error
    }
    if (error && typeof error === 'object' && error.code === '23505') {
      throw new Error('USERNAME_TAKEN')
    }
    throw error
  }
}
