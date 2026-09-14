import { createHash } from 'node:crypto'
import { lookup } from 'node:dns/promises'
import { isIP } from 'node:net'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'

export const config = { maxDuration: 30 }

const PUBLIC_FIRST_PARTY_ORIGIN = 'https://medicalai.qd.je'
const DEFAULT_BASE_URL = 'https://apihub.agnes-ai.com/v1'
const MODEL_ID = 'agnes-3.0-flash'
const ROOT_ANALYSIS_VERSION = 'agnes-discovery-live-v5-async-cache'
const CONTINUATION_ANALYSIS_VERSION = 'agnes-discovery-continuation-v2'
const RATE_WINDOW_MS = 60 * 1000
const RATE_MAX_PER_CLIENT = 12
const PROVIDER_TIMEOUT_MS = 12_000
const PAGE_TIMEOUT_MS = 4_000
const MAX_SOURCE_BYTES = 2_000_000
const MAX_REQUEST_BODY_BYTES = 262_144
const MAX_SEGMENT_ANCHORS = 80
const MAX_SEGMENT_PAGE_FETCHES = 3
const MAX_PRIOR_SEGMENTS = 5
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

const NEXT_PAGE_LABELS = new Set(['下一页', '下页', '下一頁', 'next', 'next page'])

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
  if (typeof request.body === 'string' && request.body.length <= MAX_REQUEST_BODY_BYTES) {
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
    a === 0 || a === 10 || a === 127 ||
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
  if (!records.length || records.some((item) => privateIp(item.address))) throw new Error('SOURCE_NETWORK_REJECTED')
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

function extractAnchors(html, source, baseUrl) {
  const regex = /<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi
  const seen = new Set()
  const rows = []
  let match
  while ((match = regex.exec(html)) !== null && rows.length < 400) {
    const title = htmlText(match[2]).slice(0, 220)
    if (!title) continue
    const url = canonicalOfficialUrl(match[1], baseUrl, source.hosts)
    if (!url || seen.has(url)) continue
    seen.add(url)
    rows.push({ title, url })
  }
  return rows
}

function anchorAttribute(attributes, name) {
  const pattern = new RegExp(`\\b${name}\\s*=\\s*["']([^"']+)["']`, 'i')
  return pattern.exec(attributes)?.[1] ?? null
}

function extractNextPageUrl(html, source, baseUrl) {
  const linkRegex = /<link\b([^>]*?)>/gi
  let linkMatch
  while ((linkMatch = linkRegex.exec(html)) !== null) {
    const rel = (anchorAttribute(linkMatch[1], 'rel') || '').toLowerCase().split(/\s+/)
    if (!rel.includes('next')) continue
    const href = anchorAttribute(linkMatch[1], 'href')
    const url = href ? canonicalOfficialUrl(href, baseUrl, source.hosts) : null
    if (url && url !== baseUrl) return url
  }
  const anchorRegex = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi
  let anchorMatch
  while ((anchorMatch = anchorRegex.exec(html)) !== null) {
    const attributes = anchorMatch[1]
    const href = anchorAttribute(attributes, 'href')
    if (!href) continue
    const rel = (anchorAttribute(attributes, 'rel') || '').toLowerCase().split(/\s+/)
    const label = htmlText(anchorMatch[2]).toLowerCase().replace(/\s+/g, ' ').trim()
    if (!rel.includes('next') && !NEXT_PAGE_LABELS.has(label)) continue
    const url = canonicalOfficialUrl(href, baseUrl, source.hosts)
    if (url && url !== baseUrl) return url
  }
  return null
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
      // Try next decoder.
    }
  }
  decoded.sort((a, b) => b.score - a.score)
  return decoded[0]?.text || new TextDecoder('utf-8').decode(buffer)
}

async function fetchOfficialPage(source, pageUrl) {
  let currentUrl = pageUrl
  for (let redirectCount = 0; redirectCount <= MAX_REDIRECTS; redirectCount += 1) {
    const parsed = new URL(currentUrl)
    if (!source.hosts.has(parsed.hostname.toLowerCase())) throw new Error('SOURCE_REDIRECT_REJECTED')
    await assertPublicHostname(parsed.hostname)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), PAGE_TIMEOUT_MS)
    let response
    try {
      response = await fetch(currentUrl, {
        signal: controller.signal,
        redirect: 'manual',
        headers: {
          'User-Agent': 'MedicalChannelAI/0.4 (+bounded public continuation radar)',
          Accept: 'text/html,application/xhtml+xml',
          'Accept-Language': 'zh-CN,zh;q=0.9',
        },
      })
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw new Error('SOURCE_TIMEOUT')
      throw error
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
    return { html: decodeBody(buffer, declared), url: currentUrl }
  }
  throw new Error('SOURCE_REDIRECT_REJECTED')
}

function anchorFingerprint(anchors) {
  const stable = anchors
    .map((item) => [item.url, item.title])
    .sort((a, b) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]))
  return createHash('sha256').update(JSON.stringify(stable)).digest('hex').slice(0, 32)
}

function normalizeAnchors(rows, source, limit = MAX_SEGMENT_ANCHORS) {
  if (!Array.isArray(rows) || rows.length > limit) return null
  const seen = new Set()
  const result = []
  for (const row of rows) {
    if (!row || typeof row !== 'object') return null
    const title = typeof row.title === 'string' ? row.title.replace(/\s+/g, ' ').trim().slice(0, 220) : ''
    const rawUrl = typeof row.url === 'string' ? row.url.trim() : ''
    const url = canonicalOfficialUrl(rawUrl, source.url, source.hosts)
    if (!title || !url || rawUrl !== url || seen.has(url)) return null
    seen.add(url)
    result.push({ title, url })
  }
  return result
}

function normalizePageUrls(rows, source, maxCount) {
  if (!Array.isArray(rows) || rows.length < 1 || rows.length > maxCount) return null
  const result = []
  for (const raw of rows) {
    if (typeof raw !== 'string') return null
    const value = raw.trim()
    const url = canonicalOfficialUrl(value, source.url, source.hosts)
    if (!url || url !== value) return null
    result.push(url)
  }
  return result
}

function rootScanFromBody(body, source) {
  const raw = body?.root_scan
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  if (raw.analysis_version !== ROOT_ANALYSIS_VERSION || raw.source_id !== source.id) return null
  if (canonicalSourceUrl(raw.source_url) !== source.url) return null
  if (raw.coverage_partial !== false) return null
  if (raw.coverage_page_limit_applied !== true && raw.anchor_cap_applied !== true) return null
  const anchors = normalizeAnchors(raw.anchor_snapshot, source)
  const pageUrls = normalizePageUrls(raw.coverage_page_urls, source, 2)
  if (!anchors?.length || !pageUrls) return null
  const fingerprint = typeof raw.content_fingerprint === 'string' ? raw.content_fingerprint : ''
  if (fingerprint !== anchorFingerprint(anchors)) return null
  return { anchors, pageUrls, fingerprint }
}

function previousSegmentsFromBody(body, source, root) {
  const rows = body?.previous_segments ?? []
  if (!Array.isArray(rows) || rows.length > MAX_PRIOR_SEGMENTS) return null
  const segments = []
  const seenAnchors = new Set(root.anchors.map((item) => item.url))
  for (let index = 0; index < rows.length; index += 1) {
    const raw = rows[index]
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
    if (raw.analysis_version !== CONTINUATION_ANALYSIS_VERSION || raw.source_id !== source.id) return null
    if (canonicalSourceUrl(raw.source_url) !== source.url || raw.root_content_fingerprint !== root.fingerprint) return null
    if (raw.segment_index !== index + 1 || raw.partial !== false) return null
    const anchors = normalizeAnchors(raw.anchor_snapshot, source)
    const pageUrls = normalizePageUrls(raw.page_urls, source, MAX_SEGMENT_PAGE_FETCHES)
    if (!anchors || !pageUrls) return null
    if (raw.content_fingerprint !== anchorFingerprint(anchors)) return null
    for (const anchor of anchors) {
      if (seenAnchors.has(anchor.url)) return null
      seenAnchors.add(anchor.url)
    }
    const resumeFrom = canonicalOfficialUrl(raw.resume_from_page_url, source.url, source.hosts)
    const nextResume = raw.next_resume_from_page_url === null
      ? null
      : canonicalOfficialUrl(raw.next_resume_from_page_url, source.url, source.hosts)
    if (!resumeFrom || (raw.next_resume_from_page_url !== null && !nextResume)) return null
    const exhausted = raw.exhausted === true
    if (exhausted && nextResume !== null) return null
    if (!exhausted && !nextResume) return null
    if (index < rows.length - 1 && exhausted) return null
    segments.push({ anchors, pageUrls, resumeFrom, nextResume, exhausted })
  }
  return { segments, seenAnchors }
}

async function scanContinuationPages(source, resumeFromPageUrl, seenAnchorUrls) {
  const anchors = []
  const checkedPageUrls = []
  const visitedThisRequest = new Set()
  let currentUrl = resumeFromPageUrl
  let nextResumeFromPageUrl = null
  let exhausted = false

  for (let fetchIndex = 0; fetchIndex < MAX_SEGMENT_PAGE_FETCHES; fetchIndex += 1) {
    if (visitedThisRequest.has(currentUrl)) {
      exhausted = true
      break
    }
    visitedThisRequest.add(currentUrl)
    const page = await fetchOfficialPage(source, currentUrl)
    checkedPageUrls.push(page.url)
    const pageAnchors = extractAnchors(page.html, source, page.url)
    const unseen = pageAnchors.filter((item) => !seenAnchorUrls.has(item.url) && !anchors.some((row) => row.url === item.url))
    const room = MAX_SEGMENT_ANCHORS - anchors.length
    anchors.push(...unseen.slice(0, room))

    if (unseen.length > room) {
      nextResumeFromPageUrl = page.url
      break
    }

    const nextUrl = extractNextPageUrl(page.html, source, page.url)
    if (!nextUrl || nextUrl === page.url) {
      exhausted = true
      break
    }
    if (anchors.length >= MAX_SEGMENT_ANCHORS || fetchIndex + 1 >= MAX_SEGMENT_PAGE_FETCHES) {
      nextResumeFromPageUrl = page.url
      break
    }
    currentUrl = nextUrl
  }

  if (!exhausted && !nextResumeFromPageUrl && checkedPageUrls.length) {
    nextResumeFromPageUrl = checkedPageUrls[checkedPageUrls.length - 1]
  }
  return { anchors, checkedPageUrls, nextResumeFromPageUrl, exhausted }
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
        '你是医疗行业公开商机发现器。只从输入的官方公开来源链接列表中挑选仍可能影响需求、测试、论证、方案或采购准备的前期窗口。' +
        '优先：需求调研、供应商征集、测试企业征集、论证邀请、采购意向。排除正式招标公告、成交/中标结果、招聘、人事、党建、新闻宣传。' +
        '禁止补全、改写、猜测URL；只能原样返回输入URL。不要把判断说成已验证事实。严格输出JSON，不要Markdown。',
    },
    {
      role: 'user',
      content: JSON.stringify({
        source: source.name,
        source_kind: source.kind,
        continuation_segment: true,
        anchors,
        max_candidates: 12,
        allowed_signal_types: Array.from(SIGNAL_TYPES),
        output_rules: [
          'candidates只包含判断为采购前期窗口的链接',
          '每个candidate的signal_type必须是单个字符串，且只能取allowed_signal_types中的一个值',
          'confidence必须是0到1之间的数字',
          'reason不超过30个汉字',
          '不要返回title字段',
        ],
        output_schema: {
          candidates: [{
            url: '必须与输入URL完全一致',
            signal_type: '单个字符串枚举值',
            confidence: 0.95,
            reason: '不超过30个汉字',
          }],
        },
      }),
    },
  ]
}

async function callProvider(source, anchors, keys, segmentIndex) {
  const apiKey = keys[stableIndex(`${source.id}:${source.url}:segment:${segmentIndex}`, keys.length)]
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
        chat_template_kwargs: { enable_thinking: false },
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

function parseCandidates(content, anchors) {
  let payload
  try {
    payload = JSON.parse(content.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim())
  } catch {
    throw new Error('AI_RESPONSE_INVALID')
  }
  if (!payload || typeof payload !== 'object' || !Array.isArray(payload.candidates)) throw new Error('AI_RESPONSE_INVALID')
  const allowed = new Map(anchors.map((item) => [item.url, item]))
  const seen = new Set()
  const accepted = []
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
    accepted.push({ title: anchor.title, url: rawUrl, signal_type: signalType, confidence, reason: reason.slice(0, 160) })
  }
  return { candidates: accepted, rawCount: payload.candidates.length, rejectedUngrounded, rejectedInvalid }
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

async function benchmarkMap(source) {
  try {
    return verifiedOpportunityMapForSource(await loadVerifiedSnapshot(), source)
  } catch {
    return new Map()
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
  const root = rootScanFromBody(body, source)
  if (!root) return sendJson(response, 409, { error: 'AI_RADAR_CONTINUATION_NOT_ELIGIBLE' })
  const previous = previousSegmentsFromBody(body, source, root)
  if (!previous) return sendJson(response, 400, { error: 'AI_RADAR_CONTINUATION_LEDGER_INVALID' })
  if (previous.segments.length >= MAX_PRIOR_SEGMENTS) return sendJson(response, 409, { error: 'AI_RADAR_CONTINUATION_LIMIT_REACHED' })

  const lastSegment = previous.segments.at(-1)
  if (lastSegment?.exhausted) return sendJson(response, 409, { error: 'AI_RADAR_CONTINUATION_EXHAUSTED' })
  const resumeFromPageUrl = lastSegment?.nextResume ?? root.pageUrls[root.pageUrls.length - 1]
  const checkedAt = new Date().toISOString()

  try {
    const scan = await scanContinuationPages(source, resumeFromPageUrl, previous.seenAnchors)
    const segmentIndex = previous.segments.length + 1
    const fingerprint = anchorFingerprint(scan.anchors)
    let parsed = { candidates: [], rawCount: 0, rejectedUngrounded: 0, rejectedInvalid: 0 }
    let aiCalled = false
    if (scan.anchors.length) {
      const keys = getApiKeys()
      if (!keys.length) return sendJson(response, 503, { error: 'AI_RADAR_NOT_CONFIGURED' })
      parsed = parseCandidates(await callProvider(source, scan.anchors, keys, segmentIndex), scan.anchors)
      aiCalled = true
    }
    const verified = await benchmarkMap(source)
    const segmentId = createHash('sha256')
      .update(`${source.id}\u0000${root.fingerprint}\u0000${segmentIndex}\u0000${fingerprint}`)
      .digest('hex')
      .slice(0, 24)

    return sendJson(response, 200, {
      schema_version: '0.1',
      mode: 'AI_DISCOVERY_CONTINUATION_SHADOW',
      analysis_version: CONTINUATION_ANALYSIS_VERSION,
      segment_id: segmentId,
      segment_index: segmentIndex,
      source_id: source.id,
      source_name: source.name,
      source_url: source.url,
      root_content_fingerprint: root.fingerprint,
      checked_at: checkedAt,
      analyzed_at: aiCalled ? checkedAt : null,
      resume_from_page_url: resumeFromPageUrl,
      page_urls: scan.checkedPageUrls,
      next_resume_from_page_url: scan.exhausted ? null : scan.nextResumeFromPageUrl,
      exhausted: scan.exhausted,
      partial: false,
      error_code: null,
      content_fingerprint: fingerprint,
      anchor_snapshot: scan.anchors,
      analyzed_anchor_count: scan.anchors.length,
      ai_called: aiCalled,
      raw_candidate_count: parsed.rawCount,
      candidate_count: parsed.candidates.length,
      rejected_ungrounded_count: parsed.rejectedUngrounded,
      rejected_invalid_count: parsed.rejectedInvalid,
      production_data_mutated: false,
      candidates: parsed.candidates.map((item) => ({
        ...item,
        verification_status: verified.has(item.url) ? 'KNOWN_VERIFIED' : 'DISCOVERED_UNVERIFIED',
        opportunity_id: verified.get(item.url) || null,
      })),
    })
  } catch (error) {
    console.error('AI discovery continuation failed', {
      source_id: source.id,
      source_host: new URL(source.url).hostname,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    const message = error instanceof Error ? error.message : ''
    const code = message === 'AI_RESPONSE_INVALID'
      ? 'AI_RADAR_RESPONSE_INVALID'
      : message.startsWith('SOURCE_')
        ? message
        : 'AI_RADAR_CONTINUATION_UNAVAILABLE'
    return sendJson(response, 503, { error: code })
  }
}
