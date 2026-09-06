import {
  createDecipheriv,
  createECDH,
  createHash,
  createHmac,
} from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import aiCoreHandler from '../api/ai/_analyzeCore.js'

const EXPECTED_BRANCH = 'chatgpt/preview-54495b1'
const OPPORTUNITY_ID = 'ccgp_bf77073fba23504b'
const DERIVATION_SALT = 'mcai-preview-ai-v3-20260906-f31b5f5e'
const ENVELOPE_AAD = 'MedicalChannelAI Preview AI selector v3 selftest'
const scriptDir = dirname(fileURLToPath(import.meta.url))
const envelopePath = resolve(scriptDir, '.preview-ai-build-envelope.json')

function enabled() {
  return String(process.env.VERCEL_ENV || '').trim() === 'preview' &&
    String(process.env.VERCEL_GIT_COMMIT_REF || '').trim() === EXPECTED_BRANCH
}

function derivedServerEcdh(secret) {
  for (let counter = 0; counter < 8; counter += 1) {
    const candidate = createHmac('sha256', secret)
      .update(`${DERIVATION_SALT}:${counter}`)
      .digest()
    const ecdh = createECDH('secp256k1')
    try {
      ecdh.setPrivateKey(candidate)
      return ecdh
    } catch {
      // Retry only for the negligible invalid-scalar case.
    }
  }
  throw new Error('PREVIEW_AI_BUILD_ECDH_DERIVATION_FAILED')
}

function mockResponse() {
  return {
    statusCode: null,
    body: null,
    headers: {},
    setHeader(name, value) {
      this.headers[String(name).toLowerCase()] = value
    },
    status(code) {
      this.statusCode = code
      return this
    },
    json(payload) {
      this.body = payload
      return this
    },
  }
}

function decryptEnvelope(ecdh, envelope) {
  if (
    envelope?.schema_version !== '1' ||
    typeof envelope.client_public_key !== 'string' ||
    typeof envelope.iv !== 'string' ||
    typeof envelope.tag !== 'string' ||
    typeof envelope.ciphertext !== 'string'
  ) {
    throw new Error('PREVIEW_AI_BUILD_ENVELOPE_INVALID')
  }
  const shared = ecdh.computeSecret(Buffer.from(envelope.client_public_key, 'base64url'))
  const key = createHash('sha256')
    .update(shared)
    .update(`\0${DERIVATION_SALT}`)
    .digest()
  const decipher = createDecipheriv('aes-256-gcm', key, Buffer.from(envelope.iv, 'base64url'))
  decipher.setAAD(Buffer.from(ENVELOPE_AAD, 'utf8'))
  decipher.setAuthTag(Buffer.from(envelope.tag, 'base64url'))
  const clear = Buffer.concat([
    decipher.update(Buffer.from(envelope.ciphertext, 'base64url')),
    decipher.final(),
  ]).toString('utf8').trim()
  if (!clear || clear.length > 300) throw new Error('PREVIEW_AI_BUILD_KEY_INVALID')
  return clear
}

async function main() {
  if (!enabled()) return
  const serverSecret = String(process.env.DATABASE_URL || process.env.POSTGRES_URL || '').trim()
  if (!serverSecret) throw new Error('PREVIEW_AI_BUILD_SERVER_SECRET_MISSING')

  const server = derivedServerEcdh(serverSecret)
  console.log(`PREVIEW_AI_BUILD_SERVER_PUBLIC_B64=${server.getPublicKey().toString('base64url')}`)

  if (!existsSync(envelopePath)) {
    console.log('Preview AI build selftest: WAITING_FOR_ENCRYPTED_ENVELOPE')
    return
  }

  const envelope = JSON.parse(readFileSync(envelopePath, 'utf8'))
  const apiKey = decryptEnvelope(server, envelope)
  const savedSingle = process.env.AGNES_API_KEY
  const savedMany = process.env.AGNES_API_KEYS
  const response = mockResponse()
  process.env.AGNES_API_KEY = apiKey
  process.env.AGNES_API_KEYS = ''
  try {
    await aiCoreHandler({
      method: 'POST',
      query: {},
      body: { opportunity_id: OPPORTUNITY_ID },
      headers: {
        host: 'preview-build-selftest.local',
        'x-forwarded-host': 'preview-build-selftest.local',
        origin: 'https://preview-build-selftest.local',
        'x-forwarded-for': '198.51.100.254',
      },
    }, response)
  } finally {
    if (savedSingle === undefined) delete process.env.AGNES_API_KEY
    else process.env.AGNES_API_KEY = savedSingle
    if (savedMany === undefined) delete process.env.AGNES_API_KEYS
    else process.env.AGNES_API_KEYS = savedMany
  }

  if (response.statusCode !== 200) {
    throw new Error(`PREVIEW_AI_BUILD_SELFTEST_FAILED:${response.statusCode}:${response.body?.error || 'UNKNOWN'}`)
  }
  const serialized = JSON.stringify(response.body?.decision || {})
  for (const forbidden of [
    '通常存在一定竞争',
    '提前获取完整招标需求',
    '官方未披露医院既往',
    '中标不确定性较高',
    '品牌倾向性',
  ]) {
    if (serialized.includes(forbidden)) throw new Error(`PREVIEW_AI_BUILD_SELFTEST_UNGROUNDED:${forbidden}`)
  }
  if (response.body?.shared_public_cache?.prompt_version !== 'decision-action-selector-v3-public-v1') {
    throw new Error('PREVIEW_AI_BUILD_SELFTEST_PROMPT_VERSION_MISMATCH')
  }
  console.log(`PREVIEW_AI_BUILD_SELFTEST_RESULT=${JSON.stringify({
    status: response.statusCode,
    opportunity_id: response.body?.opportunity_id,
    snapshot_as_of: response.body?.snapshot_as_of,
    decision_source: response.body?.decision_source,
    prompt_version: response.body?.shared_public_cache?.prompt_version,
    decision: response.body?.decision,
  })}`)
  console.log('Preview AI build selftest: PASS')
}

await main()
