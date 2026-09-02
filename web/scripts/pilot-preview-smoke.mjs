import { randomUUID } from 'node:crypto'

const baseUrl = String(process.env.PILOT_SMOKE_BASE_URL || '').trim().replace(/\/+$/, '')
const inviteCode = String(process.env.PILOT_SMOKE_INVITE_CODE || '').trim()
const bypassSecret = String(process.env.VERCEL_AUTOMATION_BYPASS_SECRET || '').trim()
const testAi = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.PILOT_SMOKE_AI || '').trim().toLowerCase(),
)

if (!baseUrl) throw new Error('PILOT_SMOKE_BASE_URL_REQUIRED')
if (inviteCode.length < 24) throw new Error('PILOT_SMOKE_INVITE_CODE_REQUIRED')

const base = new URL(baseUrl)
if (base.protocol !== 'https:') throw new Error('PILOT_SMOKE_HTTPS_REQUIRED')
if (base.hostname === 'medicalai.qd.je') {
  throw new Error('PILOT_SMOKE_PRODUCTION_FORBIDDEN')
}
if (!base.hostname.endsWith('.vercel.app')) {
  throw new Error('PILOT_SMOKE_PREVIEW_HOST_REQUIRED')
}

const username = String(process.env.PILOT_SMOKE_USERNAME || `smoke${Date.now().toString(36)}`)
  .trim()
  .slice(0, 32)
const password = String(process.env.PILOT_SMOKE_PASSWORD || `Smoke-${randomUUID()}!`)
if (!/^[A-Za-z0-9._-]{4,32}$/.test(username)) throw new Error('PILOT_SMOKE_USERNAME_INVALID')
if (password.length < 10 || password.length > 128) throw new Error('PILOT_SMOKE_PASSWORD_INVALID')

const cookies = new Map()
let accountCreated = false
let accountDeleted = false

function updateCookies(response) {
  const values = typeof response.headers.getSetCookie === 'function'
    ? response.headers.getSetCookie()
    : [response.headers.get('set-cookie')].filter(Boolean)
  for (const value of values) {
    const first = String(value || '').split(';', 1)[0]
    const separator = first.indexOf('=')
    if (separator <= 0) continue
    const name = first.slice(0, separator).trim()
    const cookieValue = first.slice(separator + 1).trim()
    if (!cookieValue || /max-age=0/i.test(String(value))) cookies.delete(name)
    else cookies.set(name, cookieValue)
  }
}

function cookieHeader() {
  return [...cookies.entries()].map(([name, value]) => `${name}=${value}`).join('; ')
}

async function request(path, { method = 'GET', body, expected = [200] } = {}) {
  const url = new URL(path, `${base.origin}/`)
  const headers = {
    Accept: 'application/json',
    Origin: base.origin,
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (cookies.size) headers.Cookie = cookieHeader()
  if (bypassSecret) {
    headers['x-vercel-protection-bypass'] = bypassSecret
    headers['x-vercel-set-bypass-cookie'] = 'true'
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: 'manual',
  })
  updateCookies(response)

  if (response.status >= 300 && response.status < 400) {
    throw new Error(`PREVIEW_PROTECTION_OR_REDIRECT:${response.status}`)
  }

  const text = await response.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      throw new Error(`NON_JSON_RESPONSE:${response.status}`)
    }
  }

  if (!expected.includes(response.status)) {
    const code = payload && typeof payload.error === 'string' ? payload.error : 'UNKNOWN'
    throw new Error(`HTTP_${response.status}:${code}`)
  }
  return { status: response.status, payload }
}

function assert(condition, code) {
  if (!condition) throw new Error(code)
}

function hasOwn(record, key) {
  return Boolean(record && typeof record === 'object' && Object.prototype.hasOwnProperty.call(record, key))
}

function assertPilotUser(payload, code) {
  const user = payload?.user
  assert(user && typeof user.username === 'string', `${code}:USERNAME`)
  assert(hasOwn(user, 'display_name'), `${code}:DISPLAY_NAME_MISSING`)
  assert(user.display_name === null || typeof user.display_name === 'string', `${code}:DISPLAY_NAME_INVALID`)
  assert(['OWNER', 'ADMIN', 'MEMBER'].includes(user.role), `${code}:ROLE`)
}

function findComponent(card, code) {
  const components = Array.isArray(card?.priority?.components) ? card.priority.components : []
  return components.find((item) => item?.code === code) || null
}

function scanForbiddenKeys(value, path = '$') {
  const forbidden = new Set(['password_hash', 'password_salt', 'token_hash', 'private_sessions'])
  if (Array.isArray(value)) {
    value.forEach((item, index) => scanForbiddenKeys(item, `${path}[${index}]`))
    return
  }
  if (!value || typeof value !== 'object') return
  for (const [key, child] of Object.entries(value)) {
    if (forbidden.has(key)) throw new Error(`ACCOUNT_EXPORT_SECRET_FIELD:${path}.${key}`)
    scanForbiddenKeys(child, `${path}.${key}`)
  }
}

async function cleanup() {
  if (!accountCreated || accountDeleted) return
  try {
    let session = await request('/api/auth/me', { expected: [200, 401] })
    if (session.status === 401) {
      await request('/api/auth/login', {
        method: 'POST',
        body: { username, password },
        expected: [200],
      })
      session = await request('/api/auth/me', { expected: [200] })
    }
    if (session.status === 200) {
      await request('/api/account/delete', {
        method: 'POST',
        body: { password },
        expected: [200],
      })
      accountDeleted = true
    }
  } catch (error) {
    console.error('Pilot smoke cleanup failed:', error instanceof Error ? error.message : 'UNKNOWN')
  }
}

async function main() {
  console.log(`Pilot Preview smoke target: ${base.origin}`)

  const anonymous = await request('/api/auth/me', { expected: [401, 503] })
  if (anonymous.status === 503) {
    throw new Error(`PILOT_BACKEND_NOT_READY:${anonymous.payload?.error || 'HTTP_503'}`)
  }
  assert(anonymous.payload?.error === 'AUTH_REQUIRED', 'ANONYMOUS_AUTH_CONTRACT_INVALID')

  const registered = await request('/api/auth/register', {
    method: 'POST',
    body: { invite_code: inviteCode, username, password },
    expected: [201],
  })
  accountCreated = true
  assertPilotUser(registered.payload, 'REGISTER_USER_CONTRACT_INVALID')

  const me = await request('/api/auth/me')
  assertPilotUser(me.payload, 'ME_USER_CONTRACT_INVALID')
  assert(me.payload.user.username === username, 'ME_USERNAME_MISMATCH')

  const emptyProfile = await request('/api/profile')
  assert(emptyProfile.payload?.mode === 'PRIVATE_CUSTOMER_PROFILE', 'PROFILE_MODE_INVALID')
  assert(Array.isArray(emptyProfile.payload?.profile?.product_capabilities), 'PROFILE_CAPABILITIES_INVALID')

  const initialToday = await request('/api/today')
  const initialPool = Array.isArray(initialToday.payload?.opportunity_pool)
    ? initialToday.payload.opportunity_pool
    : initialToday.payload?.cards
  assert(Array.isArray(initialPool) && initialPool.length > 0, 'TODAY_POOL_EMPTY')
  const target = initialPool[0]
  const opportunityId = target?.opportunity_id
  const projectName = target?.facts?.project_name
  const hospital = target?.facts?.hospital_name || target?.facts?.buyer_name
  assert(typeof opportunityId === 'string' && opportunityId, 'TARGET_OPPORTUNITY_ID_MISSING')
  assert(typeof projectName === 'string' && projectName.trim(), 'TARGET_PROJECT_NAME_MISSING')

  const savedProfile = await request('/api/profile', {
    method: 'PUT',
    body: {
      product_capabilities: [{ keyword: projectName, capability_type: 'DIRECT' }],
      hospital_relationships: hospital
        ? [{ hospital, department: null, relationship_strength: 'STRONG' }]
        : [],
      can_find_manufacturer: true,
      can_partner_channel: true,
      can_handle_lease: true,
    },
  })
  assert(savedProfile.payload?.profile?.product_capabilities?.length === 1, 'PROFILE_SAVE_FAILED')

  const personalizedToday = await request('/api/today')
  const personalizedPool = Array.isArray(personalizedToday.payload?.opportunity_pool)
    ? personalizedToday.payload.opportunity_pool
    : personalizedToday.payload?.cards
  const personalized = personalizedPool.find((item) => item?.opportunity_id === opportunityId)
  assert(personalized, 'PERSONALIZED_TARGET_MISSING')
  assert(personalized.priority?.score_scope === 'PERSONALIZED', 'PERSONALIZED_SCORE_SCOPE_INVALID')
  assert(
    Number(findComponent(personalized, 'PRODUCT_EXECUTION_CAPABILITY')?.points || 0) > 0,
    'PERSONALIZED_PRODUCT_POINTS_MISSING',
  )
  if (hospital) {
    assert(
      Number(findComponent(personalized, 'RELATIONSHIP')?.points || 0) > 0,
      'PERSONALIZED_RELATIONSHIP_POINTS_MISSING',
    )
  }

  await request(`/api/feedback/${encodeURIComponent(opportunityId)}`, {
    method: 'PUT',
    body: { value: 'NEW_WORTH_FOLLOWING' },
  })
  const feedback = await request(`/api/feedback/${encodeURIComponent(opportunityId)}`)
  assert(feedback.payload?.value === 'NEW_WORTH_FOLLOWING', 'FEEDBACK_PERSISTENCE_FAILED')

  const mutationId = `followup:${randomUUID()}`
  const followupBody = {
    status: 'REVIEWING',
    mutation_id: mutationId,
    note: 'Pilot Preview automated smoke test',
  }
  const firstFollowup = await request(`/api/followup/${encodeURIComponent(opportunityId)}`, {
    method: 'POST',
    body: followupBody,
  })
  assert(firstFollowup.payload?.mutation_inserted === true, 'FOLLOWUP_INSERT_FAILED')
  const repeatedFollowup = await request(`/api/followup/${encodeURIComponent(opportunityId)}`, {
    method: 'POST',
    body: followupBody,
  })
  assert(repeatedFollowup.payload?.mutation_inserted === false, 'FOLLOWUP_IDEMPOTENCY_FAILED')
  assert(repeatedFollowup.payload?.current_status === 'REVIEWING', 'FOLLOWUP_STATUS_INVALID')

  const followed = await request('/api/followed')
  assert(
    Array.isArray(followed.payload?.items) &&
      followed.payload.items.some((item) => item?.opportunity_id === opportunityId),
    'FOLLOWED_LIST_MISSING_TARGET',
  )

  const privateBoundary = await request('/api/ai/analyze', {
    method: 'POST',
    body: { opportunity_id: opportunityId, customer_context: {} },
    expected: [400],
  })
  assert(
    privateBoundary.payload?.error === 'PILOT_CUSTOMER_CONTEXT_SERVER_ONLY',
    'AI_PRIVATE_BOUNDARY_NOT_ENFORCED',
  )

  if (testAi) {
    const ai = await request('/api/ai/analyze', {
      method: 'POST',
      body: { opportunity_id: opportunityId },
      expected: [200],
    })
    assert(ai.payload?.decision && typeof ai.payload.decision.action === 'string', 'AI_DECISION_INVALID')
  }

  const exported = await request('/api/account/export')
  scanForbiddenKeys(exported.payload)
  assert(exported.payload?.account?.username === username, 'ACCOUNT_EXPORT_USERNAME_MISMATCH')

  await request('/api/auth/logout', { method: 'POST' })
  const loggedOut = await request('/api/auth/me', { expected: [401] })
  assert(loggedOut.payload?.error === 'AUTH_REQUIRED', 'LOGOUT_SESSION_NOT_CLEARED')

  const loggedIn = await request('/api/auth/login', {
    method: 'POST',
    body: { username, password },
  })
  assertPilotUser(loggedIn.payload, 'LOGIN_USER_CONTRACT_INVALID')
  const persistedProfile = await request('/api/profile')
  assert(
    persistedProfile.payload?.profile?.product_capabilities?.some((item) => item?.keyword === projectName.slice(0, 160)),
    'CROSS_SESSION_PROFILE_PERSISTENCE_FAILED',
  )

  const deleted = await request('/api/account/delete', {
    method: 'POST',
    body: { password },
  })
  assert(deleted.payload?.deleted === true, 'ACCOUNT_DELETE_FAILED')
  accountDeleted = true

  const afterDelete = await request('/api/auth/me', { expected: [401] })
  assert(afterDelete.payload?.error === 'AUTH_REQUIRED', 'DELETED_SESSION_STILL_ACTIVE')

  const reusedInvite = await request('/api/auth/register', {
    method: 'POST',
    body: { invite_code: inviteCode, username: `${username.slice(0, 27)}x`, password },
    expected: [401],
  })
  assert(reusedInvite.payload?.error === 'INVITE_INVALID_OR_EXPIRED', 'CONSUMED_INVITE_REUSED')

  console.log('Pilot Preview API smoke: PASS')
  console.log(`Opportunity exercised: ${opportunityId}`)
  console.log(`AI live call exercised: ${testAi ? 'yes' : 'no'}`)
}

try {
  await main()
} finally {
  await cleanup()
}
