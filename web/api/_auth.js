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

export function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.status(status).json(payload)
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
      s.id AS session_id
    FROM private_sessions s
    JOIN private_users u ON u.id = s.user_id
    WHERE s.token_hash = ${tokenHash}
      AND s.expires_at > now()
      AND u.status = 'ACTIVE'
    LIMIT 1
  `
  const user = rows[0]
  if (!user) return null
  await sql`
    UPDATE private_sessions
    SET last_seen_at = now()
    WHERE id = ${user.session_id}
      AND last_seen_at < now() - interval '10 minutes'
  `
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
    .map((value) => value.trim())
    .filter((value) => value.length >= 24)
    .map(sha256)
}

export async function claimInvite(tx, codeHash, userId, newOrganizationId) {
  const knownBootstrap = bootstrapInviteHashes().includes(codeHash)
  const existing = await tx`
    SELECT code_hash, organization_id, expires_at, used_by
    FROM private_pilot_invites
    WHERE code_hash = ${codeHash}
    FOR UPDATE
  `
  let invitation = existing[0] || null

  if (!invitation) {
    if (!knownBootstrap) return null
    await tx`
      INSERT INTO private_pilot_invites (code_hash, organization_id)
      VALUES (${codeHash}, ${newOrganizationId})
      ON CONFLICT (code_hash) DO NOTHING
    `
    const inserted = await tx`
      SELECT code_hash, organization_id, expires_at, used_by
      FROM private_pilot_invites
      WHERE code_hash = ${codeHash}
      FOR UPDATE
    `
    invitation = inserted[0] || null
  }

  if (!invitation || invitation.used_by) return null
  if (invitation.expires_at && new Date(invitation.expires_at).getTime() <= Date.now()) return null
  const organizationId = invitation.organization_id || newOrganizationId
  const claimed = await tx`
    UPDATE private_pilot_invites
    SET organization_id = ${organizationId}, used_by = ${userId}, used_at = now()
    WHERE code_hash = ${codeHash} AND used_by IS NULL
    RETURNING code_hash
  `
  return claimed.length === 1 ? organizationId : null
}
