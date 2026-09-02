import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

export const config = { maxDuration: 30 }

const PUBLIC_FIRST_PARTY_ORIGIN = 'https://medicalai.qd.je'
const DEFAULT_BASE_URL = 'https://apihub.agnes-ai.com/v1'
const MODEL_ID = 'agnes-2.5-flash'
const RATE_WINDOW_MS = 60 * 1000
const RATE_MAX_PER_CLIENT = 6
const PROVIDER_TIMEOUT_MS = 12_000
const SOURCE_TIMEOUT_MS = 8_000
const MAX_ANCHORS = 80
const rateBuckets = new Map()

const SOURCES = {
  TMUGH: {
    name: '天津医科大学总医院',
    url: 'https://www.tjmugh.com.cn/cgxxtzgg/index.shtml',
    hosts: new Set(['www.tjmugh.com.cn', 'tjmugh.com.cn']),
  },
  TJNOTHOP: {
    name: '天津市天津医院',
    url: 'https://www.tjnothop.cn/xwzx/index.shtml',
    hosts: new Set(['www.tjnothop.cn', 'tjnothop.cn']),
  },
  TEDA: {
    name: '天津泰达医院',
    url: 'https://www.tedahospital.com.cn/article/plist/9',
    hosts: new Set(['www.tedahospital.com.cn', 'tedahospital.com.cn']),
  },
}

const SIGNAL_TYPES = new Set([
  'DEMAND_RESEARCH',
  'SUPPLIER_RECRUITMENT',
  'TEST_ENTERPRISE_RECRUITMENT',
  'ARGUMENTATION_INVITATION',
  'PURCHASE_INTENTION',
  'OTHER_PREPROCUREMENT',
])

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.setHeader('Referrer-Policy', 'no-referrer')
  response.status(status).json(payload)
}

function firstHeader(value) {
  return Array.isArray(value) ? value[0] ?? null : typeof value === 'string' ? value : null
}

function sameOriginAllowed(request) {
  const origin = firstHeader(request.headers?.origin)
  if (!origin) return false
  if (origin === PUBLIC_FIRST_PARTY_ORIGIN) return true
  let parsed
  try {
    parsed = new URL(origin)
  } catch {
    return false
  }
  if (process.env.NODE_ENV === 'production' && parsed.protocol !== 'https:') return false
  const hosts = [firstHeader(request.headers?.['x-forwarded-host']), firstHeader(request.headers?.host)]
    .filter(Boolean)
    .map((item) => item.toLowerCase())
  return hosts.includes(parsed.host.toLowerCase())
}

function clientKey(request) {
  const forwarded = firstHeader(request.headers?.['x-forwarded-for'])
  return forwarded?.split(',')[0]?.trim() || firstHeader(request.headers?.['x-real-ip']) || 'unknown-client'
}

function rateLimited(request) {
  const now = Date.now()
  const key = clientKey(request)
  const current = rateBuckets.get(key)
  if (!current || now - current.startedAt >= RATE_WINDOW_MS) {
    rateBuckets.set(key, { startedAt: now, count: 1 })
    return false
  }
  current.count += 1
  if (rateBuckets.size > 500) {
    for (const [bucketKey, bucket] of rateBuckets) {
      if (now - bucket.startedAt >= RATE_WINDOW_MS) rateBuckets.delete(bucketKey)
    }
  }
  return current.count > RATE_MAX_PER_CLIENT
}

function bodyObject(request) {
  if (request.body && typeof request.body === 'object' && !Array.isArray(request.body)) return request.body
  if (typeof request.body === 'string' && request.body.length <= 4096) {
    try {
      const parsed = JSON.parse(request.body)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return null
}

function sourceIdFromBody(body) {
  const value = typeof body?.source_id === 'string' ? body.source_id.trim().toUpperCase() : ''
  return Object.prototype.hasOwnProperty.call(SOURCES, value) ? value : null
}

function htmlText(value) {
  return String(value || '')
    .replace(/<script\b[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;|&#160;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&#(\d+);/g, (_, number) => String.fromCodePoint(Number(number)))
    .replace(/\s+/g, ' ')
    .trim()
}

function canonicalOfficialUrl(value, baseUrl, allowedHosts) {
  let parsed
  try {
    parsed = new URL(value, baseUrl)
  } catch {
    return null
  }
  const host = parsed.hostname.toLowerCase()
  if (!allowedHosts.has(host)) return null
  if (parsed.protocol === 'http:') parsed.protocol = 'https:'
  if (parsed.protocol !== 'https:') return null
  parsed.hash = ''
  return parsed.toString()
}

function extractAnchors(html, source) {
  const regex = /<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi
  const seen = new Set()
  const rows = []
  let match
  while ((match = regex.exec(html)) !== null && rows.length < 400) {
    const title = htmlText(match[2]).slice(0, 220)
    if (!title) continue
    const url = canonicalOfficialUrl(match[1], source.url, source.hosts)
    if (!url || seen.has(url)) continue
    seen.add(url)
    rows.push({ title, url })
  }
  return rows
}

function textQuality(text) {
  const cjk = (text.match(/[\u3400-\u9fff]/g) || []).length
  const replacement = (text.match(/�/g) || []).length
  return cjk * 2 - replacement * 20
}

function decodeBody(buffer, declaredCharset) {
  const candidates = [declaredCharset, 'utf-8', 'gb18030']
  const decoded = []
  for (const encoding of candidates) {
    if (!encoding || decoded.some((item) => item.encoding === encoding.toLowerCase())) continue
    try {
      const text = new TextDecoder(encoding, { fatal: false }).decode(buffer)
      decoded.push({ encoding: encoding.toLowerCase(), text, score: textQuality(text) })
    } catch {
      // Try the next supported decoder.
    }
  }
  decoded.sort((a, b) => b.score - a.score)
  return decoded[0]?.text || new TextDecoder('utf-8').decode(buffer)
}

async function fetchOfficialIndex(source) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), SOURCE_TIMEOUT_MS)
  try {
    const response = await fetch(source.url, {
      signal: controller.signal,
      redirect: 'follow',
      headers: {
        'User-Agent': 'MedicalChannelAI/0.1 (+AI discovery radar)',
        Accept: 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
      },
    })
    if (!response.ok) throw new Error(`SOURCE_HTTP_${response.status}`)
    const finalUrl = canonicalOfficialUrl(response.url, source.url, source.hosts)
    if (!finalUrl) throw new Error('SOURCE_REDIRECT_REJECTED')
    const contentType = response.headers.get('content-type') || ''
    const declared = /charset\s*=\s*([^;\s]+)/i.exec(contentType)?.[1]?.replace(/["']/g, '') || null
    const buffer = await response.arrayBuffer()
    return decodeBody(buffer, declared)
  } finally {
    clearTimeout(timeout)
  }
}

function getApiKeys() {
  const raw = process.env.AGNES_API_KEYS || process.env.AGNES_API_KEY || ''
  return raw.split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean)
}

function stableIndex(text, length) {
  let hash = 2166136261
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0) % length
}

function buildMessages(source, anchors) {
  return [
    {
      role: 'system',
      content:
        '你是医疗采购前期商机发现器。只从输入的医院官方链接列表中挑选仍可能影响需求、测试、论证、方案或采购准备的前期窗口。' +
        '优先：需求调研、供应商征集、测试企业征集、论证邀请、采购意向。' +
        '排除：正式招标公告、成交/中标结果、评分细则、招聘、人事、党建、新闻宣传、纯制度通知。' +
        '禁止补全、改写、猜测URL；只能原样返回输入URL。不要把判断说成已验证事实。严格输出JSON，不要Markdown。',
    },
    {
      role: 'user',
      content: JSON.stringify({
        source: source.name,
        anchors,
        max_candidates: 12,
        output_schema: {
          candidates: [{
            title: '对应输入标题',
            url: '必须与输入URL完全一致',
            signal_type: Array.from(SIGNAL_TYPES),
            confidence: '0到1',
            reason: '不超过80个汉字',
          }],
        },
      }),
    },
  ]
}

async function callProvider(sourceId, source, anchors, keys) {
  const apiKey = keys[stableIndex(sourceId, keys.length)]
  const baseUrl = String(process.env.AGNES_API_BASE_URL || DEFAULT_BASE_URL).trim().replace(/\/+$/, '')
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), PROVIDER_TIMEOUT_MS)
  try {
    const response = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        model: MODEL_ID,
        messages: buildMessages(source, anchors),
        temperature: 0,
        max_tokens: 1400,
        stream: false,
      }),
    })
    if (!response.ok) throw new Error(`UPSTREAM_HTTP_${response.status}`)
    const payload = await response.json()
    const content = payload?.choices?.[0]?.message?.content
    if (typeof content !== 'string' || !content.trim()) throw new Error('UPSTREAM_CONTENT_EMPTY')
    return content
  } finally {
    clearTimeout(timeout)
  }
}

function jsonContent(content) {
  return content.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim()
}

function parseCandidates(content, anchors) {
  const allowed = new Map(anchors.map((item) => [item.url, item]))
  let payload
  try {
    payload = JSON.parse(jsonContent(content))
  } catch {
    throw new Error('AI_RESPONSE_INVALID')
  }
  if (!payload || typeof payload !== 'object' || !Array.isArray(payload.candidates)) {
    throw new Error('AI_RESPONSE_INVALID')
  }
  const accepted = []
  const seen = new Set()
  let rejectedUngrounded = 0
  let rejectedInvalid = 0
  for (const row of payload.candidates) {
    if (!row || typeof row !== 'object') {
      rejectedInvalid += 1
      continue
    }
    const rawUrl = typeof row.url === 'string' ? row.url.trim() : ''
    const anchor = allowed.get(rawUrl)
    if (!anchor) {
      rejectedUngrounded += 1
      continue
    }
    const signalType = typeof row.signal_type === 'string' ? row.signal_type.trim().toUpperCase() : ''
    const confidence = Number(row.confidence)
    const reason = typeof row.reason === 'string' ? row.reason.replace(/\s+/g, ' ').trim() : ''
    if (!SIGNAL_TYPES.has(signalType) || !Number.isFinite(confidence) || confidence < 0 || confidence > 1 || !reason) {
      rejectedInvalid += 1
      continue
    }
    if (seen.has(rawUrl)) continue
    seen.add(rawUrl)
    accepted.push({
      title: anchor.title,
      url: rawUrl,
      signal_type: signalType,
      confidence,
      reason: reason.slice(0, 160),
    })
  }
  return {
    candidates: accepted,
    rawCount: payload.candidates.length,
    rejectedUngrounded,
    rejectedInvalid,
  }
}

function verifiedUrlsForSource(snapshot, source) {
  const pool = Array.isArray(snapshot?.opportunity_pool) && snapshot.opportunity_pool.length
    ? snapshot.opportunity_pool
    : Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const urls = new Set()
  for (const card of pool) {
    if (card?.facts?.verification_status !== 'VERIFIED') continue
    for (const raw of Array.isArray(card?.evidence_source_urls) ? card.evidence_source_urls : []) {
      try {
        const url = new URL(raw)
        if (source.hosts.has(url.hostname.toLowerCase())) {
          url.hash = ''
          urls.add(url.toString())
        }
      } catch {
        // Ignore malformed historical evidence URLs.
      }
    }
  }
  return urls
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!sameOriginAllowed(request)) return sendJson(response, 403, { error: 'SAME_ORIGIN_REQUIRED' })
  if (rateLimited(request)) return sendJson(response, 429, { error: 'AI_RADAR_RATE_LIMITED' })

  const body = bodyObject(request)
  const sourceId = sourceIdFromBody(body)
  if (!sourceId) return sendJson(response, 400, { error: 'AI_RADAR_SOURCE_INVALID' })
  const keys = getApiKeys()
  if (!keys.length) return sendJson(response, 503, { error: 'AI_RADAR_NOT_CONFIGURED' })

  const source = SOURCES[sourceId]
  const scannedAt = new Date().toISOString()
  try {
    const html = await fetchOfficialIndex(source)
    const allAnchors = extractAnchors(html, source)
    const anchors = allAnchors.slice(0, MAX_ANCHORS)
    if (!anchors.length) return sendJson(response, 503, { error: 'AI_RADAR_SOURCE_EMPTY' })

    const content = await callProvider(sourceId, source, anchors, keys)
    const parsed = parseCandidates(content, anchors)
    let verifiedUrls = new Set()
    try {
      verifiedUrls = verifiedUrlsForSource(await loadVerifiedSnapshot(), source)
    } catch {
      // Discovery remains useful even when the independent benchmark snapshot is temporarily unavailable.
    }

    const knownHitCount = parsed.candidates.filter((item) => verifiedUrls.has(item.url)).length
    const knownRecall = verifiedUrls.size ? knownHitCount / verifiedUrls.size : null
    const groundedRate = parsed.rawCount ? (parsed.rawCount - parsed.rejectedUngrounded) / parsed.rawCount : 1
    const validRate = parsed.rawCount
      ? (parsed.rawCount - parsed.rejectedUngrounded - parsed.rejectedInvalid) / parsed.rawCount
      : 1
    const discoveryScore = knownRecall === null
      ? null
      : Math.round((0.75 * knownRecall + 0.20 * groundedRate + 0.05 * validRate) * 1000) / 10

    return sendJson(response, 200, {
      schema_version: '0.1',
      mode: 'AI_DISCOVERY_SHADOW',
      source_id: sourceId,
      source_name: source.name,
      source_url: source.url,
      scanned_at: scannedAt,
      official_anchor_count: allAnchors.length,
      analyzed_anchor_count: anchors.length,
      anchor_cap_applied: allAnchors.length > anchors.length,
      candidate_count: parsed.candidates.length,
      known_verified_count: verifiedUrls.size,
      known_verified_hit_count: knownHitCount,
      known_recall: knownRecall === null ? null : Math.round(knownRecall * 1000) / 1000,
      discovery_score: discoveryScore,
      rejected_ungrounded_count: parsed.rejectedUngrounded,
      rejected_invalid_count: parsed.rejectedInvalid,
      production_data_mutated: false,
      candidates: parsed.candidates.map((item) => ({
        ...item,
        verification_status: verifiedUrls.has(item.url) ? 'KNOWN_VERIFIED' : 'DISCOVERED_UNVERIFIED',
      })),
    })
  } catch (error) {
    console.error('AI discovery radar failed', {
      source_id: sourceId,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    const code = error instanceof Error && error.message === 'AI_RESPONSE_INVALID'
      ? 'AI_RADAR_RESPONSE_INVALID'
      : 'AI_RADAR_UNAVAILABLE'
    return sendJson(response, 503, { error: code })
  }
}
