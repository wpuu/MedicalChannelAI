import { createHash } from 'node:crypto'
import { lookup } from 'node:dns/promises'
import { isIP } from 'node:net'
import { getCache, waitUntil } from '@vercel/functions'
import { authenticatedUser } from '../_auth.js'
import { privateDatabaseConfigured } from '../_privateDb.js'
import { loadVerifiedSnapshot } from '../_verifiedSnapshot.js'
import continuationDiscoveryHandler from './_discoverContinuation.js'

export const config = { maxDuration: 45 }

const PUBLIC_FIRST_PARTY_ORIGIN = 'https://medicalai.qd.je'
const DEFAULT_BASE_URL = 'https://apihub.agnes-ai.com/v1'
const MODEL_ID = 'agnes-3.0-flash'
const ANALYSIS_VERSION = 'agnes-discovery-live-v5-async-cache'
const RATE_WINDOW_MS = 60 * 1000
const RATE_MAX_PER_CLIENT = 30
const BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000
const SOURCE_TIMEOUT_MS = 8_000
const OPTIONAL_PAGE_TIMEOUT_MS = 4_000
const MAX_SOURCE_BYTES = 2_000_000
const MAX_REQUEST_BODY_BYTES = 262_144
const MAX_ANCHORS = 80
const MAX_REDIRECTS = 3
const MAX_COVERAGE_PAGES = 2
const AI_CACHE_PREFIX = 'medicalchannelai:agnes-discovery:v1'
const AI_CACHE_LATEST_PREFIX = 'medicalchannelai:agnes-discovery-latest:v1'
const AI_CACHE_READY_TTL_SECONDS = 2 * 24 * 60 * 60
const AI_CACHE_TRANSIENT_TTL_SECONDS = 60
const AI_CACHE_PENDING_STALE_MS = 35_000
const AI_CACHE_FAILURE_BACKOFF_MS = 15_000
const rateBuckets = new Map()
const aiRefreshInFlight = new Set()

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

const NEXT_PAGE_LABELS = new Set([
  '下一页',
  '下页',
  '下一頁',
  'next',
  'next page',
])

function sendJson(response, status, payload) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.setHeader('Referrer-Policy', 'no-referrer')
  response.status(status).json(payload)
}

function privatePilotEnabled() {
  return ['1', 'true', 'yes', 'on'].includes(
    String(process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED || '').trim().toLowerCase(),
  )
}

async function requirePrivatePilotSession(request, response) {
  if (!privatePilotEnabled()) return true
  if (!privateDatabaseConfigured()) {
    sendJson(response, 503, { error: 'PRIVATE_DATABASE_NOT_CONFIGURED' })
    return false
  }
  try {
    const user = await authenticatedUser(request)
    if (user) return true
    sendJson(response, 401, { error: 'AUTH_REQUIRED' })
    return false
  } catch (error) {
    console.error('pilot radar session lookup failed', {
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    sendJson(response, 503, { error: 'SESSION_LOOKUP_FAILED' })
    return false
  }
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

function extractAnchors(html, source, baseUrl = source.url) {
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

async function fetchOfficialPage(source, pageUrl, timeoutMs = SOURCE_TIMEOUT_MS) {
  let currentUrl = pageUrl
  for (let redirectCount = 0; redirectCount <= MAX_REDIRECTS; redirectCount += 1) {
    const parsed = new URL(currentUrl)
    if (!source.hosts.has(parsed.hostname.toLowerCase())) throw new Error('SOURCE_REDIRECT_REJECTED')
    await assertPublicHostname(parsed.hostname)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), timeoutMs)
    let response
    try {
      response = await fetch(currentUrl, {
        signal: controller.signal,
        redirect: 'manual',
        headers: {
          'User-Agent': 'MedicalChannelAI/0.4 (+incremental public source radar)',
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

function optionalCoverageErrorCode(error) {
  const message = error instanceof Error ? error.message : ''
  if (/^SOURCE_[A-Z0-9_]+$/.test(message) && message.length <= 80) return message
  return 'OPTIONAL_PAGE_UNAVAILABLE'
}

async function fetchOfficialCoverage(source) {
  const seenPageUrls = new Set()
  const anchorByUrl = new Map()
  const pageUrls = []
  let nextPageDetected = false
  let pageLimitApplied = false
  let partial = false
  let errorCode = null
  let currentUrl = source.url

  for (let pageIndex = 0; pageIndex < MAX_COVERAGE_PAGES; pageIndex += 1) {
    if (seenPageUrls.has(currentUrl)) break
    seenPageUrls.add(currentUrl)
    let page
    try {
      page = await fetchOfficialPage(
        source,
        currentUrl,
        pageIndex === 0 ? SOURCE_TIMEOUT_MS : OPTIONAL_PAGE_TIMEOUT_MS,
      )
    } catch (error) {
      if (pageIndex === 0) throw error
      partial = true
      errorCode = optionalCoverageErrorCode(error)
      break
    }
    pageUrls.push(page.url)
    for (const anchor of extractAnchors(page.html, source, page.url)) {
      if (!anchorByUrl.has(anchor.url)) anchorByUrl.set(anchor.url, anchor)
    }
    if (anchorByUrl.size >= MAX_ANCHORS) break

    const nextUrl = extractNextPageUrl(page.html, source, page.url)
    if (!nextUrl || seenPageUrls.has(nextUrl)) break
    nextPageDetected = true
    if (pageIndex + 1 >= MAX_COVERAGE_PAGES) {
      pageLimitApplied = true
      break
    }
    currentUrl = nextUrl
  }

  return {
    anchors: Array.from(anchorByUrl.values()),
    pageUrls,
    nextPageDetected,
    pageLimitApplied,
    partial,
    errorCode,
    scannedAnchorCount: anchorByUrl.size,
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

function anchorFingerprint(anchors) {
  const stable = anchors
    .map((item) => [item.url, item.title])
    .sort((a, b) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]))
  return createHash('sha256').update(JSON.stringify(stable)).digest('hex').slice(0, 32)
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

async function callProvider(source, anchors, keys) {
  const apiKey = keys[stableIndex(`${source.id}:${source.url}`, keys.length)]
  const baseUrl = String(process.env.AGNES_API_BASE_URL || DEFAULT_BASE_URL).trim().replace(/\/+$/, '')
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), BACKGROUND_PROVIDER_TIMEOUT_MS)
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
    accepted.push({ title: anchor.title, url: rawUrl, signal_type: signalType, confidence, reason: reason.slice(0, 160) })
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
  if (!payload || typeof payload !== 'object' || !Array.isArray(payload.candidates)) throw new Error('AI_RESPONSE_INVALID')
  return parseCandidateRows(payload.candidates, anchors, payload.candidates.length)
}

function mergeParsed(reused, fresh) {
  const byUrl = new Map()
  for (const candidate of [...reused.candidates, ...fresh.candidates]) byUrl.set(candidate.url, candidate)
  return {
    candidates: Array.from(byUrl.values()),
    rawCount: reused.rawCount + fresh.rawCount,
    rejectedUngrounded: reused.rejectedUngrounded + fresh.rejectedUngrounded,
    rejectedInvalid: reused.rejectedInvalid + fresh.rejectedInvalid,
  }
}


function emptyParsed() {
  return { candidates: [], rawCount: 0, rejectedUngrounded: 0, rejectedInvalid: 0 }
}

function aiCacheSourceSignature(source) {
  return createHash('sha256')
    .update(`${source.url}\u0000${source.kind}\u0000${source.name}`)
    .digest('hex')
    .slice(0, 32)
}

function aiCacheKey(source, fingerprint) {
  return `${AI_CACHE_PREFIX}:${createHash('sha256')
    .update(`${ANALYSIS_VERSION}\u0000${aiCacheSourceSignature(source)}\u0000${fingerprint}`)
    .digest('hex')
    .slice(0, 40)}`
}

function aiLatestCacheKey(source) {
  return `${AI_CACHE_LATEST_PREFIX}:${createHash('sha256')
    .update(`${ANALYSIS_VERSION}\u0000${aiCacheSourceSignature(source)}`)
    .digest('hex')
    .slice(0, 40)}`
}

function cachedCandidateRows(parsed) {
  return parsed.candidates.map((item) => ({
    url: item.url,
    signal_type: item.signal_type,
    confidence: item.confidence,
    reason: item.reason,
  }))
}

function normalizeCacheDelta(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const fields = ['newCount', 'changedCount', 'removedCount', 'reusedCount']
  const result = {}
  for (const field of fields) {
    const number = Number(value[field])
    if (!Number.isInteger(number) || number < 0 || number > MAX_ANCHORS * 2) return null
    result[field] = number
  }
  return result
}

function validateAiCacheEntry(value, source, anchors, fingerprint) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  if (value.schema_version !== '0.1' || value.analysis_version !== ANALYSIS_VERSION) return null
  if (value.source_signature !== aiCacheSourceSignature(source) || value.content_fingerprint !== fingerprint) return null
  if (value.state === 'PENDING') {
    const startedAt = Date.parse(value.started_at || '')
    return Number.isFinite(startedAt) ? { state: 'PENDING', startedAt } : null
  }
  if (value.state === 'FAILED') {
    const retryAfter = Date.parse(value.retry_after || '')
    return Number.isFinite(retryAfter) ? { state: 'FAILED', retryAfter } : null
  }
  if (value.state !== 'READY' || !value.parsed || typeof value.parsed !== 'object') return null
  const rawCount = Number(value.parsed.rawCount)
  const rejectedUngrounded = Number(value.parsed.rejectedUngrounded)
  const rejectedInvalid = Number(value.parsed.rejectedInvalid)
  if (![rawCount, rejectedUngrounded, rejectedInvalid].every((item) => Number.isInteger(item) && item >= 0)) return null
  if (!Array.isArray(value.parsed.candidates) || value.parsed.candidates.length > 60) return null
  const reparsed = parseCandidateRows(value.parsed.candidates, anchors, rawCount)
  if (reparsed.rejectedUngrounded || reparsed.rejectedInvalid || reparsed.candidates.length !== value.parsed.candidates.length) return null
  const analyzedAt = typeof value.analyzed_at === 'string' && Number.isFinite(Date.parse(value.analyzed_at))
    ? value.analyzed_at
    : null
  const aiAnalyzedAnchorCount = Number(value.ai_analyzed_anchor_count)
  const delta = normalizeCacheDelta(value.delta)
  if (!analyzedAt || !Number.isInteger(aiAnalyzedAnchorCount) || aiAnalyzedAnchorCount < 0 || aiAnalyzedAnchorCount > MAX_ANCHORS || !delta) return null
  return {
    state: 'READY',
    analyzedAt,
    aiAnalyzedAnchorCount,
    delta,
    parsed: {
      candidates: reparsed.candidates,
      rawCount,
      rejectedUngrounded,
      rejectedInvalid,
    },
  }
}

async function readAiCache(source, anchors, fingerprint) {
  if (!process.env.VERCEL_REGION) return null
  try {
    const value = await getCache().get(aiCacheKey(source, fingerprint))
    return validateAiCacheEntry(value, source, anchors, fingerprint)
  } catch {
    return null
  }
}

function validateLatestAiCacheEntry(value, source) {
  const anchors = previousAnchorSnapshot(value, source)
  if (!anchors?.length) return null
  const fingerprint = typeof value?.content_fingerprint === 'string' ? value.content_fingerprint : ''
  if (!fingerprint || anchorFingerprint(anchors) !== fingerprint) return null
  const ready = validateAiCacheEntry(value, source, anchors, fingerprint)
  return ready?.state === 'READY' ? { ...ready, anchors, fingerprint } : null
}

async function readLatestAiCache(source) {
  if (!process.env.VERCEL_REGION) return null
  try {
    const value = await getCache().get(aiLatestCacheKey(source))
    return validateLatestAiCacheEntry(value, source)
  } catch {
    return null
  }
}

async function writeAiCache(key, value, ttl) {
  if (!process.env.VERCEL_REGION) return
  await getCache().set(key, value, {
    ttl,
    tags: ['medicalchannelai-agnes-discovery'],
  })
}

async function runAiRefreshTask({ key, source, aiAnchors, snapshotAnchors, fingerprint, keys, baseParsed, delta }) {
  try {
    const content = await callProvider(source, aiAnchors, keys)
    const freshParsed = parseCandidates(content, aiAnchors)
    const parsed = mergeParsed(baseParsed, freshParsed)
    const analyzedAt = new Date().toISOString()
    const cacheValue = {
      schema_version: '0.1',
      state: 'READY',
      analysis_version: ANALYSIS_VERSION,
      source_signature: aiCacheSourceSignature(source),
      content_fingerprint: fingerprint,
      analyzed_at: analyzedAt,
      ai_analyzed_anchor_count: aiAnchors.length,
      delta: {
        newCount: delta.newCount,
        changedCount: delta.changedCount,
        removedCount: delta.removedCount,
        reusedCount: delta.reusedCount,
      },
      anchor_snapshot: snapshotAnchors.map((item) => ({ title: item.title, url: item.url })),
      parsed: {
        candidates: cachedCandidateRows(parsed),
        rawCount: parsed.rawCount,
        rejectedUngrounded: parsed.rejectedUngrounded,
        rejectedInvalid: parsed.rejectedInvalid,
      },
    }
    await writeAiCache(key, cacheValue, AI_CACHE_READY_TTL_SECONDS)
    try {
      await writeAiCache(aiLatestCacheKey(source), cacheValue, AI_CACHE_READY_TTL_SECONDS)
    } catch {
      // Fingerprint cache remains authoritative; latest cache is resilience-only.
    }
    return {
      state: 'READY',
      analyzedAt,
      aiAnalyzedAnchorCount: aiAnchors.length,
      delta: cacheValue.delta,
      parsed,
    }
  } catch (error) {
    try {
      await writeAiCache(key, {
        schema_version: '0.1',
        state: 'FAILED',
        analysis_version: ANALYSIS_VERSION,
        source_signature: aiCacheSourceSignature(source),
        content_fingerprint: fingerprint,
        retry_after: new Date(Date.now() + AI_CACHE_FAILURE_BACKOFF_MS).toISOString(),
      }, AI_CACHE_TRANSIENT_TTL_SECONDS)
    } catch {
      // Cache failure must not turn a slow provider into a request-path failure.
    }
    console.warn('AI discovery background refresh deferred', {
      source_host: new URL(source.url).hostname,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
    return null
  } finally {
    aiRefreshInFlight.delete(key)
  }
}

async function scheduleAiRefresh({ source, aiAnchors, snapshotAnchors, fingerprint, keys, baseParsed, delta }) {
  const key = aiCacheKey(source, fingerprint)
  if (aiRefreshInFlight.has(key)) return { scheduled: false, ready: null }
  aiRefreshInFlight.add(key)
  try {
    await writeAiCache(key, {
      schema_version: '0.1',
      state: 'PENDING',
      analysis_version: ANALYSIS_VERSION,
      source_signature: aiCacheSourceSignature(source),
      content_fingerprint: fingerprint,
      started_at: new Date().toISOString(),
    }, AI_CACHE_TRANSIENT_TTL_SECONDS)
  } catch {
    // Background work may still complete in this warm instance even if cache marking fails.
  }
  const task = runAiRefreshTask({ key, source, aiAnchors, snapshotAnchors, fingerprint, keys, baseParsed, delta })
  if (process.env.VERCEL) {
    try {
      waitUntil(task)
      return { scheduled: true, ready: null }
    } catch {
      // Fall through to awaited local-style execution if background scheduling is unavailable.
    }
  }
  const ready = await task
  return { scheduled: true, ready }
}

function previousAnchorSnapshot(previous, source) {
  if (!Array.isArray(previous?.anchor_snapshot) || previous.anchor_snapshot.length > MAX_ANCHORS) return null
  const seen = new Set()
  const rows = []
  for (const row of previous.anchor_snapshot) {
    if (!row || typeof row !== 'object') return null
    const title = typeof row.title === 'string' ? row.title.replace(/\s+/g, ' ').trim().slice(0, 220) : ''
    const rawUrl = typeof row.url === 'string' ? row.url.trim() : ''
    const url = canonicalOfficialUrl(rawUrl, source.url, source.hosts)
    if (!title || !url || url !== rawUrl || seen.has(url)) return null
    seen.add(url)
    rows.push({ title, url })
  }
  return rows
}

function reusablePreviousSnapshot(body, source) {
  const previous = body?.previous_scan
  if (!previous || typeof previous !== 'object' || Array.isArray(previous)) return null
  if (previous.ai_refresh_pending === true || ['AI_REFRESH_PENDING', 'STALE_WHILE_AI_REFRESH'].includes(previous.cache_status)) return null
  if (previous.analysis_version !== ANALYSIS_VERSION || canonicalSourceUrl(previous.source_url) !== source.url) return null
  if (!Array.isArray(previous.candidates) || previous.candidates.length > 60) return null
  const anchors = previousAnchorSnapshot(previous, source)
  if (!anchors?.length) return null
  const fingerprint = typeof previous.content_fingerprint === 'string' ? previous.content_fingerprint : ''
  if (fingerprint !== anchorFingerprint(anchors)) return null
  const rawCount = Number(previous.raw_candidate_count)
  if (!Number.isInteger(rawCount) || rawCount < previous.candidates.length || rawCount > 200) return null
  const analyzedAt = typeof previous.analyzed_at === 'string' && Number.isFinite(Date.parse(previous.analyzed_at))
    ? previous.analyzed_at
    : null
  if (!analyzedAt) return null
  const parsed = parseCandidateRows(previous.candidates, anchors, rawCount)
  if (parsed.rejectedUngrounded || parsed.rejectedInvalid || parsed.candidates.length !== previous.candidates.length) return null
  return { anchors, fingerprint, analyzedAt, parsed }
}

function previousScanContext(body, source, anchors, fingerprint) {
  if (body?.force_ai === true) return null
  const previous = body?.previous_scan
  if (!previous || typeof previous !== 'object' || Array.isArray(previous)) return null
  if (previous.ai_refresh_pending === true || ['AI_REFRESH_PENDING', 'STALE_WHILE_AI_REFRESH'].includes(previous.cache_status)) return null
  if (previous.analysis_version !== ANALYSIS_VERSION || canonicalSourceUrl(previous.source_url) !== source.url) return null
  if (!Array.isArray(previous.candidates) || previous.candidates.length > 60) return null
  const rawCount = Number(previous.raw_candidate_count)
  if (!Number.isInteger(rawCount) || rawCount < previous.candidates.length || rawCount > 200) return null
  const analyzedAt = typeof previous.analyzed_at === 'string' && Number.isFinite(Date.parse(previous.analyzed_at))
    ? previous.analyzed_at
    : null
  if (!analyzedAt) return null
  const oldAnchors = previousAnchorSnapshot(previous, source)
  if (!oldAnchors) return null

  const currentMap = new Map(anchors.map((item) => [item.url, item]))
  const oldMap = new Map(oldAnchors.map((item) => [item.url, item]))
  const newAnchors = anchors.filter((item) => !oldMap.has(item.url))
  const changedAnchors = anchors.filter((item) => {
    const old = oldMap.get(item.url)
    return old && old.title !== item.title
  })
  const reusedAnchors = anchors.filter((item) => {
    const old = oldMap.get(item.url)
    return old && old.title === item.title
  })
  const removedAnchors = oldAnchors.filter((item) => !currentMap.has(item.url))
  const reusableRows = previous.candidates.filter((row) => {
    if (!row || typeof row !== 'object' || typeof row.url !== 'string') return false
    const current = currentMap.get(row.url)
    const old = oldMap.get(row.url)
    return Boolean(current && old && current.title === old.title)
  })
  const reusedParsed = parseCandidateRows(reusableRows, anchors, reusableRows.length)
  if (reusedParsed.rejectedUngrounded || reusedParsed.rejectedInvalid || reusedParsed.candidates.length !== reusableRows.length) return null

  let exactParsed = null
  if (previous.content_fingerprint === fingerprint) {
    exactParsed = parseCandidateRows(previous.candidates, anchors, rawCount)
    if (exactParsed.rejectedUngrounded || exactParsed.rejectedInvalid || exactParsed.candidates.length !== previous.candidates.length) return null
  }
  return {
    analyzedAt,
    exactParsed,
    reusedParsed,
    deltaAnchors: [...newAnchors, ...changedAnchors],
    newCount: newAnchors.length,
    changedCount: changedAnchors.length,
    removedCount: removedAnchors.length,
    reusedCount: reusedAnchors.length,
  }
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

function resultPayload({
  source, checkedAt, analyzedAt, allAnchors, anchors, fingerprint, parsed, benchmark,
  aiCalled, cacheStatus, aiAnalyzedAnchorCount, delta, coverage,
}) {
  const aiRefreshPending = ['AI_REFRESH_PENDING', 'STALE_WHILE_AI_REFRESH'].includes(cacheStatus)
  const knownHits = parsed.candidates.filter((item) => benchmark.currentGold.has(item.url)).length
  const knownRecall = aiRefreshPending ? null : benchmark.currentGold.size ? knownHits / benchmark.currentGold.size : null
  const groundedRate = parsed.rawCount ? (parsed.rawCount - parsed.rejectedUngrounded) / parsed.rawCount : 1
  const validRate = parsed.rawCount
    ? (parsed.rawCount - parsed.rejectedUngrounded - parsed.rejectedInvalid) / parsed.rawCount
    : 1
  const discoveryScore = aiRefreshPending || knownRecall === null
    ? null
    : Math.round((0.75 * knownRecall + 0.20 * groundedRate + 0.05 * validRate) * 1000) / 10

  return {
    schema_version: '0.3',
    mode: 'AI_DISCOVERY_SHADOW',
    analysis_version: ANALYSIS_VERSION,
    source_id: source.id,
    source_name: source.name,
    source_kind: source.kind,
    source_url: source.url,
    checked_at: checkedAt,
    scanned_at: checkedAt,
    analyzed_at: analyzedAt,
    cache_status: cacheStatus,
    ai_called: aiCalled,
    ai_refresh_pending: aiRefreshPending,
    content_fingerprint: fingerprint,
    official_anchor_count: allAnchors.length,
    analyzed_anchor_count: anchors.length,
    ai_analyzed_anchor_count: aiAnalyzedAnchorCount,
    new_anchor_count: delta.newCount,
    changed_anchor_count: delta.changedCount,
    removed_anchor_count: delta.removedCount,
    reused_anchor_count: delta.reusedCount,
    anchor_cap_applied: allAnchors.length > anchors.length,
    anchor_snapshot: anchors,
    coverage_page_count: coverage.pageUrls.length,
    coverage_page_urls: coverage.pageUrls,
    coverage_next_page_detected: coverage.nextPageDetected,
    coverage_page_limit_applied: coverage.pageLimitApplied,
    coverage_partial: coverage.partial,
    coverage_error_code: coverage.errorCode,
    coverage_scanned_anchor_count: coverage.scannedAnchorCount,
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
  const route = request.query?.route
  const routeName = Array.isArray(route) ? route[0] : typeof route === 'string' ? route : null

  if (request.method !== 'POST') {
    if (routeName === 'continuation') return continuationDiscoveryHandler(request, response)
    response.setHeader('Allow', 'POST')
    return sendJson(response, 405, { error: 'METHOD_NOT_ALLOWED' })
  }
  if (!sameOriginAllowed(request)) return sendJson(response, 403, { error: 'SAME_ORIGIN_REQUIRED' })
  if (!await requirePrivatePilotSession(request, response)) return
  if (routeName === 'continuation') return continuationDiscoveryHandler(request, response)
  if (rateLimited(request)) return sendJson(response, 429, { error: 'AI_RADAR_RATE_LIMITED' })

  const body = bodyObject(request)
  const source = sourceFromBody(body)
  if (!source) return sendJson(response, 400, { error: 'AI_RADAR_SOURCE_INVALID' })
  const checkedAt = new Date().toISOString()

  try {
    let coverage
    try {
      coverage = await fetchOfficialCoverage(source)
    } catch (sourceError) {
      const sourceMessage = sourceError instanceof Error ? sourceError.message : ''
      if (sourceMessage.startsWith('SOURCE_') && body?.force_ai !== true) {
        const latest = await readLatestAiCache(source)
        if (latest?.state === 'READY') {
          const benchmark = await benchmarkContext(source, latest.anchors)
          const fallbackCoverage = {
            pageUrls: [],
            nextPageDetected: false,
            pageLimitApplied: false,
            partial: true,
            errorCode: sourceMessage,
            scannedAnchorCount: 0,
          }
          return sendJson(response, 200, resultPayload({
            source, checkedAt, analyzedAt: latest.analyzedAt,
            allAnchors: latest.anchors, anchors: latest.anchors, fingerprint: latest.fingerprint,
            parsed: latest.parsed, benchmark, aiCalled: false,
            cacheStatus: 'SERVER_AI_CACHE_SOURCE_UNAVAILABLE',
            aiAnalyzedAnchorCount: latest.aiAnalyzedAnchorCount, delta: latest.delta,
            coverage: fallbackCoverage,
          }))
        }
      }
      throw sourceError
    }
    const currentAllAnchors = coverage.anchors
    const currentAnchors = currentAllAnchors.slice(0, MAX_ANCHORS)
    if (!currentAnchors.length) return sendJson(response, 503, { error: 'AI_RADAR_SOURCE_EMPTY' })

    if (coverage.partial && body?.force_ai !== true) {
      const saved = reusablePreviousSnapshot(body, source)
      if (saved) {
        const benchmark = await benchmarkContext(source, saved.anchors)
        return sendJson(response, 200, resultPayload({
          source,
          checkedAt,
          analyzedAt: saved.analyzedAt,
          allAnchors: saved.anchors,
          anchors: saved.anchors,
          fingerprint: saved.fingerprint,
          parsed: saved.parsed,
          benchmark,
          aiCalled: false,
          cacheStatus: 'REUSED_PARTIAL_COVERAGE',
          aiAnalyzedAnchorCount: 0,
          delta: { newCount: 0, changedCount: 0, removedCount: 0, reusedCount: saved.anchors.length },
          coverage,
        }))
      }
    }

    const allAnchors = currentAllAnchors
    const anchors = currentAnchors
    const fingerprint = anchorFingerprint(anchors)
    const benchmark = await benchmarkContext(source, anchors)
    const previous = previousScanContext(body, source, anchors, fingerprint)

    if (previous?.exactParsed) {
      return sendJson(response, 200, resultPayload({
        source, checkedAt, analyzedAt: previous.analyzedAt, allAnchors, anchors, fingerprint,
        parsed: previous.exactParsed, benchmark, aiCalled: false, cacheStatus: 'REUSED_UNCHANGED',
        aiAnalyzedAnchorCount: 0,
        delta: { newCount: 0, changedCount: 0, removedCount: 0, reusedCount: anchors.length },
        coverage,
      }))
    }

    if (previous && previous.deltaAnchors.length === 0) {
      return sendJson(response, 200, resultPayload({
        source, checkedAt, analyzedAt: previous.analyzedAt, allAnchors, anchors, fingerprint,
        parsed: previous.reusedParsed, benchmark, aiCalled: false, cacheStatus: 'REUSED_NO_NEW_LINKS',
        aiAnalyzedAnchorCount: 0, delta: previous, coverage,
      }))
    }

    const cached = await readAiCache(source, anchors, fingerprint)
    if (cached?.state === 'READY' && body?.force_ai !== true) {
      return sendJson(response, 200, resultPayload({
        source, checkedAt, analyzedAt: cached.analyzedAt, allAnchors, anchors, fingerprint,
        parsed: cached.parsed, benchmark, aiCalled: false, cacheStatus: 'SERVER_AI_CACHE',
        aiAnalyzedAnchorCount: cached.aiAnalyzedAnchorCount, delta: cached.delta, coverage,
      }))
    }

    const now = Date.now()
    const cacheBlocksRefresh = body?.force_ai !== true && (
      (cached?.state === 'PENDING' && now - cached.startedAt < AI_CACHE_PENDING_STALE_MS) ||
      (cached?.state === 'FAILED' && now < cached.retryAfter)
    )
    const baseParsed = body?.force_ai === true
      ? emptyParsed()
      : previous?.reusedParsed || (cached?.state === 'READY' ? cached.parsed : emptyParsed())
    const delta = previous ?? {
      newCount: anchors.length,
      changedCount: 0,
      removedCount: 0,
      reusedCount: 0,
    }
    const aiAnchors = previous ? previous.deltaAnchors : anchors

    if (cacheBlocksRefresh) {
      return sendJson(response, 200, resultPayload({
        source, checkedAt, analyzedAt: previous?.analyzedAt || cached?.analyzedAt || null,
        allAnchors, anchors, fingerprint, parsed: baseParsed, benchmark, aiCalled: false,
        cacheStatus: baseParsed.candidates.length ? 'STALE_WHILE_AI_REFRESH' : 'AI_REFRESH_PENDING',
        aiAnalyzedAnchorCount: 0, delta, coverage,
      }))
    }

    const keys = getApiKeys()
    if (!keys.length) return sendJson(response, 503, { error: 'AI_RADAR_NOT_CONFIGURED' })
    const scheduled = await scheduleAiRefresh({
      source, aiAnchors, snapshotAnchors: anchors, fingerprint, keys, baseParsed, delta,
    })
    if (scheduled.ready) {
      return sendJson(response, 200, resultPayload({
        source, checkedAt, analyzedAt: scheduled.ready.analyzedAt, allAnchors, anchors, fingerprint,
        parsed: scheduled.ready.parsed, benchmark, aiCalled: true,
        cacheStatus: previous ? 'FRESH_DELTA_AI' : 'FRESH_AI',
        aiAnalyzedAnchorCount: aiAnchors.length, delta, coverage,
      }))
    }
    return sendJson(response, 200, resultPayload({
      source, checkedAt, analyzedAt: previous?.analyzedAt || cached?.analyzedAt || null,
      allAnchors, anchors, fingerprint, parsed: baseParsed, benchmark,
      aiCalled: scheduled.scheduled,
      cacheStatus: baseParsed.candidates.length ? 'STALE_WHILE_AI_REFRESH' : 'AI_REFRESH_PENDING',
      aiAnalyzedAnchorCount: scheduled.scheduled ? aiAnchors.length : 0,
      delta, coverage,
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
