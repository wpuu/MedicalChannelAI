import { constants, privateDecrypt } from 'node:crypto'
import privateCoreHandler from './_privateCore.js'
import aiCoreHandler from './ai/_analyzeCore.js'
import {
  previewAiSelftestPrivateKey,
  previewAiSelftestPublicKey,
} from './_previewAiSelftestKey.js'
import {
  procurementIntentFollowupSummary,
  procurementIntentSuccessorPairs,
} from './_procurementIntentFollowup.js'
import { countFormalCandidatesNeedingAction } from './_procurementIntentFollowupDisplay.js'

const PREVIEW_AI_SELFTEST_OPPORTUNITY = 'ccgp_bf77073fba23504b'

function firstQuery(request, key) {
  const raw = request.query?.[key]
  return Array.isArray(raw) ? raw[0] : raw
}

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  return response.status(status).json(payload)
}

function previewSelftestReady() {
  return Boolean(previewAiSelftestPrivateKey && previewAiSelftestPublicKey)
}

async function maybeHandlePreviewAiSelftest(request, response) {
  const route = firstQuery(request, 'route')
  if (route === 'preview-ai-selftest-key' && request.method === 'GET') {
    if (!previewSelftestReady()) return sendJson(response, 404, { error: 'PREVIEW_AI_SELFTEST_NOT_PREPARED' })
    return sendJson(response, 200, {
      schema_version: '0.1',
      public_key_pem: previewAiSelftestPublicKey,
    })
  }
  if (route !== 'preview-ai-selftest-run' || request.method !== 'GET') return false
  if (!previewSelftestReady()) return sendJson(response, 404, { error: 'PREVIEW_AI_SELFTEST_NOT_PREPARED' })

  const cipher = String(firstQuery(request, 'cipher') || '').trim()
  if (!cipher || cipher.length > 512 || !/^[A-Za-z0-9_-]+$/.test(cipher)) {
    return sendJson(response, 400, { error: 'PREVIEW_AI_SELFTEST_CIPHER_INVALID' })
  }

  let apiKey
  try {
    apiKey = privateDecrypt(
      {
        key: previewAiSelftestPrivateKey,
        padding: constants.RSA_PKCS1_OAEP_PADDING,
        oaepHash: 'sha256',
      },
      Buffer.from(cipher, 'base64url'),
    ).toString('utf8').trim()
  } catch {
    return sendJson(response, 400, { error: 'PREVIEW_AI_SELFTEST_DECRYPT_FAILED' })
  }
  if (!apiKey || apiKey.length > 300) return sendJson(response, 400, { error: 'PREVIEW_AI_SELFTEST_KEY_INVALID' })

  const savedSingle = process.env.AGNES_API_KEY
  const savedMany = process.env.AGNES_API_KEYS
  const host = String(request.headers?.['x-forwarded-host'] || request.headers?.host || '').split(',')[0].trim()
  if (!host) return sendJson(response, 400, { error: 'PREVIEW_AI_SELFTEST_HOST_MISSING' })

  process.env.AGNES_API_KEY = apiKey
  process.env.AGNES_API_KEYS = ''
  try {
    return await aiCoreHandler({
      ...request,
      method: 'POST',
      query: {},
      body: { opportunity_id: PREVIEW_AI_SELFTEST_OPPORTUNITY },
      headers: {
        ...request.headers,
        origin: `https://${host}`,
        host,
        'x-forwarded-host': host,
      },
    }, response)
  } finally {
    if (savedSingle === undefined) delete process.env.AGNES_API_KEY
    else process.env.AGNES_API_KEY = savedSingle
    if (savedMany === undefined) delete process.env.AGNES_API_KEYS
    else process.env.AGNES_API_KEYS = savedMany
  }
}

function shouldProjectLightToday(request) {
  if (request.method !== 'GET') return false
  if (firstQuery(request, 'route') !== 'today') return false
  return firstQuery(request, 'include_pool') !== '1'
}

function projectLightTodayPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload
  if (payload.mode !== 'TODAY_ACTIONS') return payload
  if (!Object.prototype.hasOwnProperty.call(payload, 'opportunity_pool')) return payload
  const { opportunity_pool: fullPool, ...lightPayload } = payload
  const pairs = procurementIntentSuccessorPairs(fullPool)
  const projected = {
    ...lightPayload,
    procurement_intent_followup_summary: procurementIntentFollowupSummary(fullPool),
  }
  // Account-private display state only. It suppresses repeated homepage nudges
  // after an explicit follow-up decision, but never changes public lineage.
  projected.procurement_intent_followup_summary.formal_candidates_needing_action =
    countFormalCandidatesNeedingAction(fullPool, pairs)
  return projected
}

export default async function handler(request, response) {
  const selftest = await maybeHandlePreviewAiSelftest(request, response)
  if (selftest !== false) return selftest

  if (!shouldProjectLightToday(request) || typeof response.json !== 'function') {
    return privateCoreHandler(request, response)
  }

  const originalJson = response.json
  response.json = function projectedJson(payload) {
    return originalJson.call(this, projectLightTodayPayload(payload))
  }
  try {
    return await privateCoreHandler(request, response)
  } finally {
    response.json = originalJson
  }
}