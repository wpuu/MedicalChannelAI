import { createHash } from 'node:crypto'
import { lookup } from 'node:dns/promises'
import { isIP } from 'node:net'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

export const config = { maxDuration: 30 }

const PUBLIC_FIRST_PARTY_ORIGIN = 'https://medicalai.qd.je'
const DEFAULT_BASE_URL = 'https://apihub.agnes-ai.com/v1'
const MODEL_ID = 'agnes-2.5-flash'
const ANALYSIS_VERSION = 'agnes-discovery-live-v2'
const RATE_WINDOW_MS = 60 * 1000
const RATE_MAX_PER_CLIENT = 30
const PROVIDER_TIMEOUT_MS = 12_000
const SOURCE_TIMEOUT_MS = 8_000
const MAX_SOURCE_BYTES = 2_000_000
const MAX_ANCHORS = 80
const MAX_REDIRECTS = 3
const rateBuckets = new Map()

const SOURCE_KINDS = new Set([
  'HOSPITAL_OFFICIAL',
  'GOVERNMENT_PROCUREMENT',
  'PUBLIC_RESOURCE',
  'HEALTH_AUTHORITY',
  'OTHER_OFFICIAL',
])

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
  if (typeof request.body === 'string' && request.body.length <= 65_536) {
    try {
      const parsed = JSON.parse(request.body)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return null
}

function blockedHostname(hostname) {
  const host = hostname.toLowerCase().replace(/\.$/, '')
  if (!host || host === 'localhost') return true
  return ['.localhost', '.local', '.internal', '.test', '.invalid', '.example'].some((suffix) => host.endsWith(suffix))
}

function privateIpv4(address) {
  const parts = address.split('.').map(Number)
  if (parts.length !== 4 || parts.some((item) => !Number.isInteger(item) || item < 0 || item > 255)) return true
  const [a, b] = parts
  return (
    a === 0 ||
    a === 10 ||
    a === 127 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 0) ||
    (a === 192 && b === 168) ||
    (a === 198 && (b === 18 || b === 19)) ||
    (a === 192 && b === 0 && parts[2] === 2) ||
    (a === 198 && b === 51 && parts[2] === 100) ||
    (a === 203 && b === 0 && parts[2] === 113) ||
    a >= 224
  )
}

function privateIp(address) {
  const version = isIP(address)
  if (version === 4) return privateIpv4(address)
  if (version !== 6) return true
  const value = address.toLowerCase()
  if (value === '::' || value === '::1') return true
  if (value.startsWith('fc') || value.startsWith('fd')) return true
  if (/^fe[89ab]/.test(value)) return true
  if (value.startsWith('ff')) return true
  if (value.startsWith('2001:db8:')) return true
  const mapped = value.match(/::ffff:(\d+\.\d+\.\d+\.\d+)$/)
  return mapped ? privateIpv4(mapped[1]) : false
}

async function assertPublicHostname(hostname) {
  if (blockedHostname(hostname) || isIP(hostname)) throw new Error('SOURCE_HOST_REJECTED')
  let records
  try {
    records = await lookup(hostname, { all: true, verbatim: true })
  } catch {
    throw new Error('SOURCE_DNS_UNRESOLVED')
  }
  if (!records.length || records.some((item) => privateIp(item.address))) {
    throw new Error('SOURCE_NETWORK_REJECTED')
  }
}

function canonicalSourceUrl(value) {
  let parsed
  try {
    parsed = new URL(value)
  } catch {
    return null
  }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return null
  if (parsed.port && parsed.port !== '443') return null
  if (blockedHostname(parsed.hostname) || isIP(parsed.hostname)) return null
  parsed.hash = ''
  if (parsed.pathname !== '/') parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/'
  return parsed.toString()
}

function hostVariants(hostname) {
  const host = hostname.toLowerCase()
  const result = new Set([host])
  if (host.startsWith('www.')) result.add(host.slice(4))
  else result.add(`www.${host}`)
  return result
}

function sourceFromBody(body) {
  const raw = body?.source
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const id = typeof raw.id === 'string' ? raw.id.trim() : ''
  const name = typeof raw.name === 'string' ? raw.name.replace(/\s+/g, ' ').trim() : ''
  const kind = typeof raw.kind === 'string' ? raw.kind.trim().toUpperCase() : ''
  const url = canonicalSourceUrl(typeof raw.url === 'string' ? raw.url.trim() : '')
  if (!id || id.length > 96 || !/^[A-Za-z0-9._:-]+$/.test(id)) return null
  if (!name || name.length > 100 || !url || !SOURCE_KINDS.has(kind)) return null
  const parsed = new URL(url)
  return { id, name, kind, url, hosts: hostVariants(parsed.hostname) }
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
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return null
  if (parsed.port && parsed.port !== '443') return null
  parsed.hash = ''
  if (parsed.pathname !== '/') parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/'
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
  let currentUrl = source.url
  for (let redirectCount = 0; redirectCount <= MAX_REDIRECTS; redirectCount += 1) {
    const parsed = new URL(currentUrl)
    if (!source.hosts.has(parsed.hostname.toLowerCase())) throw new Error('SOURCE_REDIRECT_REJECTED')
    await assertPublicHostname(parsed.hostname)

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), SOURCE_TIMEOUT_MS)
    let response
    try {
      response = await fetch(currentUrl, {
        signal: controller.signal,
        redirect: 'manual',
        headers: {
          'User-Agent': 'MedicalChannelAI/0.2 (+user-managed public source radar)',
          Accept: 'text/html,application/xhtml+xml',
          'Accept-Language': 'zh-CN,zh;q=0.9',
        },
      })
    } finally {
      clearTimeout(timeout)
    }

    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get('location')
      if (!location || redirectCount === MAX_REDIRECTS) throw new Error('SOURCE_REDIRECT_REJECTED')
      const nextUrl = canonicalOfficialUrl(location, currentUrl, source.hosts)
      if (!nextUrl) throw new Error('SOURCE_REDIRECT_REJECTED')
      currentUrl = nextUrl
      continue
    }
    if (!response.ok) throw new Error(`SOURCE_HTTP_${response.status}`)

    const contentLength = Number(response.headers.get('content-length') || '0')
    if (Number.isFinite(contentLength) && contentLength > MAX_SOURCE_BYTES) throw new Error('SOURCE_TOO_LARGE')
    const contentType = response.headers.get('content-type') || ''
    const declared = /charset\s*=\s*([^;\s]+)/i.exec(contentType)?.[1]?.replace(/["']/g, '') || null
    const buffer = await response.arrayBuffer()
    if (buffer.byteLength > MAX_SOURCE_BYTES) throw new Error('SOURCE_TOO_LARGE')
    return decodeBody(buffer, declared)
  }
  throw new Error('SOURCE_REDIRECT_REJECTED')
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

function anchorFingerprint(anchors) {
  return createHash('sha256')
    .update(JSON.stringify(anchors.map((item) => [item.title, item.url])))
    .digest('hex')
    .slice(0, 32)
}

function buildMessages(source, anchors) {
  return [
    {
      role: 'system',
      content:
        '你是医疗行业公开商机发现器。只从输入的官方公开来源链接列表中挑选仍可能影响需求、测试、论证、方案或采购准备的前期窗口。' +
        '优先：需求调研、供应商征集、测试企业征集、论证邀请、采购意向。' +
        '排除：正式招标公告、成交/中标结果、评分细则、招聘、人事、党建、新闻宣传、纯制度通知。' +
        '禁止补全、改写、猜测URL；只能原样返回输入URL。不要把判断说成已验证事实。严格输出JSON，不要Markdown。',
    },
    {
      role: 'user',
      content: JSON.stringify({
        source: source.name,
        source_kind: source.kind,
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

async function callProvider(source, anchors, keys) {
  const apiKey = keys[stableIndex(`${source.id}:${source.url}`, keys.length)]
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

function parseCandidateRows(rows, anchors, rawCount = rows.length) {
  const allowed = new Map(anchors.map((item) => [item.url, item]))
  const accepted = []
  const seen = new Set()
  let rejectedUngrounded = 0
  let rejectedInvalid = 0
  for (const row of rows) {
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
  return { candidates: accepted, rawCount, rejectedUngrounded, rejectedInvalid }
}

function parseCandidates(content, anchors) {
  let payload
  try {
    payload = JSON.parse(jsonContent(content))
  } catch {
    throw new Error('AI_RESPONSE_INVALID')
  }
  if (!payload || typeof payload !== 'object' || !Array.isArray(payload.candidates)) {
    throw new Error('AI_RESPONSE_INVALID')
  }
  return parseCandidateRows(payload.candidates, anchors, payload.candidates.length)
}

function reusablePreviousScan(body, source, anchors, fingerprint) {
  if (body?.force_ai === true) return null
  const previous = body?.previous_scan
  if (!previous || typeof previous !== 'object' || Array.isArray(previous)) return null
  if (previous.analysis_version !== ANALYSIS_VERSION || previous.content_fingerprint !== fingerprint) return null
  if (canonicalSourceUrl(previous.source_url) !== source.url) return null
  if (!Array.isArray(previous.candidates) || previous.candidates.length > 12) return null
  const rawCount = Number(previous.raw_candidate_count)
  if (!Number.isInteger(rawCount) || rawCount < previous.candidates.length || rawCount > 50) return null
  const parsed = parseCandidateRows(previous.candidates, anchors, rawCount)
  if (parsed.rejectedUngrounded || parsed.rejectedInvalid || parsed.candidates.length !== previous.candidates.length) return null
  const analyzedAt = typeof previous.analyzed_at === 'string' && Number.isFinite(Date.parse(previous.analyzed_at))
    ? previous.analyzed_at
    : null
  if (!analyzedAt) return null
  return parsed
}

function verifiedOpportunityMapForSource(snapshot, source) {
  const pool = Array.isArray(snapshot?.opportunity_pool) && snapshot.opportunity_pool.length
    ? snapshot.opportunity_pool
    : Array.isArray(snapshot?.cards) ? snapshot.cards : []
  const byUrl = new Map()
  for (const card of pool) {
    if (card?.facts?.verification_status !== 'VERIFIED') continue
    const opportunityId = typeof card?.opportunity_id === 'string' ? card.opportunity_id : null
    if (!opportunityId) continue
    for (const raw of Array.isArray(card?.evidence_source_urls) ? card.evidence_source_urls : []) {
      if (typeof raw !== 'string') continue
      const url = canonicalOfficialUrl(raw, source.url, source.hosts)
      if (url) byUrl.set(url, opportunityId)
    }
  }
  return byUrl
}

function currentBenchmarkUrls(verifiedUrls, anchors) {
  const analyzedUrlSet = new Set(anchors.map((item) => item.url))
  return new Set(Array.from(verifiedUrls).filter((url) => analyzedUrlSet.has(url)))
}

async function benchmarkContext(source, anchors) {
  try {
    const snapshot = await loadVerifiedSnapshot()
    const map = verifiedOpportunityMapForSource(snapshot, source)
    return { map, currentGold: currentBenchmarkUrls(map.keys(), anchors) }
  } catch {
    return { map: new Map(), currentGold: new Set() }
  }
}

function resultPayload({ source, checkedAt, analyzedAt, allAnchors, anchors, fingerprint, parsed, benchmark, aiCalled }) {
  const knownHits = parsed.candidates.filter((item) => benchmark.currentGold.has(item.url)).length
  const knownRecall = benchmark.currentGold.size ? knownHits / benchmark.currentGold.size : null
  const groundedRate = parsed.rawCount ? (parsed.rawCount - parsed.rejectedUngrounded) / parsed.rawCount : 1
  const validRate = parsed.rawCount
    ? (parsed.rawCount - parsed.rejectedUngrounded - parsed.rejectedInvalid) / parsed.rawCount
    : 1
  const discoveryScore = knownRecall === null
    ? null
    : Math.round((0.75 * knownRecall + 0.20 * groundedRate + 0.05 * validRate) * 1000) / 10

  return {
    schema_version: '0.2',
    mode: 'AI_DISCOVERY_SHADOW',
    analysis_version: ANALYSIS_VERSION,
    source_id: source.id,
    source_name: source.name,
    source_kind: source.kind,
    source_url: source.url,
    checked_at: checkedAt,
    scanned_at: checkedAt,
    analyzed_at: analyzedAt,
    cache_status: aiCalled ? 'FRESH_AI' : 'REUSED_UNCHANGED',
    ai_called: aiCalled,
    content_fingerprint: fingerprint,
    official_anchor_count: allAnchors.length,
    analyzed_anchor_count: anchors.length,
    anchor_cap_applied: allAnchors.length > anchors.length,
    raw_candidate_count: parsed.rawCount,
    candidate_count: parsed.candidates.length,
    historical_known_verified_count: benchmark.map.size,
    known_verified_count: benchmark.currentGold.size,
    known_verified_hit_count: knownHits,
    known_recall: knownRecall === null ? null : Math.round(knownRecall * 1000) / 1000,
    discovery_score: discoveryScore,
    benchmark_scope: 'CURRENT_ANALYZED_OFFICIAL_LINKS',
    rejected_ungrounded_count: parsed.rejectedUngrounded,
    rejected_invalid_count: parsed.rejectedInvalid,
    production_data_mutated: false,
    candidates: parsed.candidates.map((item) => ({
      ...item,
      verification_status: benchmark.map.has(item.url) ? 'KNOWN_VERIFIED' : 'DISCOVERED_UNVERIFIED',
      opportunity_id: benchmark.map.get(item.url) || null,
    })),
  }
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!sameOriginAllowed(request)) return sendJson(response, 403, { error: 'SAME_ORIGIN_REQUIRED' })
  if (rateLimited(request)) return sendJson(response, 429, { error: 'AI_RADAR_RATE_LIMITED' })

  const body = bodyObject(request)
  const source = sourceFromBody(body)
  if (!source) return sendJson(response, 400, { error: 'AI_RADAR_SOURCE_INVALID' })
  const checkedAt = new Date().toISOString()

  try {
    const html = await fetchOfficialIndex(source)
    const allAnchors = extractAnchors(html, source)
    const anchors = allAnchors.slice(0, MAX_ANCHORS)
    if (!anchors.length) return sendJson(response, 503, { error: 'AI_RADAR_SOURCE_EMPTY' })

    const fingerprint = anchorFingerprint(anchors)
    const benchmark = await benchmarkContext(source, anchors)
    const cached = reusablePreviousScan(body, source, anchors, fingerprint)
    if (cached) {
      return sendJson(response, 200, resultPayload({
        source,
        checkedAt,
        analyzedAt: body.previous_scan.analyzed_at,
        allAnchors,
        anchors,
        fingerprint,
        parsed: cached,
        benchmark,
        aiCalled: false,
      }))
    }

    const keys = getApiKeys()
    if (!keys.length) return sendJson(response, 503, { error: 'AI_RADAR_NOT_CONFIGURED' })
    const content = await callProvider(source, anchors, keys)
    const parsed = parseCandidates(content, anchors)
    return sendJson(response, 200, resultPayload({
      source,
      checkedAt,
      analyzedAt: checkedAt,
      allAnchors,
      anchors,
      fingerprint,
      parsed,
      benchmark,
      aiCalled: true,
    }))
  } catch (error) {
    console.error('AI discovery radar failed', {
      source_id: source.id,
      source_host: new URL(source.url).hostname,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    const message = error instanceof Error ? error.message : ''
    const code = message === 'AI_RESPONSE_INVALID'
      ? 'AI_RADAR_RESPONSE_INVALID'
      : message.startsWith('SOURCE_')
        ? message
        : 'AI_RADAR_UNAVAILABLE'
    return sendJson(response, 503, { error: code })
  }
}
