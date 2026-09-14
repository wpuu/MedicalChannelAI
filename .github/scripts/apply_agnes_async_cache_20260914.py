from pathlib import Path

root = Path('app')


def replace_exact(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f'{label}: expected {count} matches, got {actual}')
    return text.replace(old, new)


# Root discovery: public source fetch stays request-path bounded; provider work becomes background cached.
path = root / 'web/api/ai/discover.js'
s = path.read_text(encoding='utf-8')
s = replace_exact(
    s,
    "import { isIP } from 'node:net'\n",
    "import { isIP } from 'node:net'\nimport { getCache, waitUntil } from '@vercel/functions'\n",
    'root vercel import',
)
s = replace_exact(s, "export const config = { maxDuration: 30 }", "export const config = { maxDuration: 45 }", 'root duration')
s = replace_exact(
    s,
    "const ANALYSIS_VERSION = 'agnes-discovery-live-v4-safe-next-page'",
    "const ANALYSIS_VERSION = 'agnes-discovery-live-v5-async-cache'",
    'root analysis version',
)
s = replace_exact(s, "const PROVIDER_TIMEOUT_MS = 12_000", "const BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000", 'root provider timeout')
s = replace_exact(
    s,
    "const MAX_COVERAGE_PAGES = 2\nconst rateBuckets = new Map()",
    "const MAX_COVERAGE_PAGES = 2\n"
    "const AI_CACHE_PREFIX = 'medicalchannelai:agnes-discovery:v1'\n"
    "const AI_CACHE_READY_TTL_SECONDS = 2 * 24 * 60 * 60\n"
    "const AI_CACHE_TRANSIENT_TTL_SECONDS = 60\n"
    "const AI_CACHE_PENDING_STALE_MS = 35_000\n"
    "const AI_CACHE_FAILURE_BACKOFF_MS = 15_000\n"
    "const rateBuckets = new Map()\n"
    "const aiRefreshInFlight = new Set()",
    'root cache constants',
)
s = replace_exact(
    s,
    "setTimeout(() => controller.abort(), PROVIDER_TIMEOUT_MS)",
    "setTimeout(() => controller.abort(), BACKGROUND_PROVIDER_TIMEOUT_MS)",
    'root provider timer',
)
s = replace_exact(
    s,
    "        temperature: 0,\n        max_tokens: 1400,\n        stream: false,",
    "        temperature: 0,\n        max_tokens: 1400,\n        stream: false,\n        chat_template_kwargs: { enable_thinking: false },",
    'root thinking off',
)

cache_helpers = r'''
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

async function writeAiCache(key, value, ttl) {
  if (!process.env.VERCEL_REGION) return
  await getCache().set(key, value, {
    ttl,
    tags: ['medicalchannelai-agnes-discovery'],
  })
}

async function runAiRefreshTask({ key, source, aiAnchors, fingerprint, keys, baseParsed, delta }) {
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
      parsed: {
        candidates: cachedCandidateRows(parsed),
        rawCount: parsed.rawCount,
        rejectedUngrounded: parsed.rejectedUngrounded,
        rejectedInvalid: parsed.rejectedInvalid,
      },
    }
    await writeAiCache(key, cacheValue, AI_CACHE_READY_TTL_SECONDS)
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

async function scheduleAiRefresh({ source, aiAnchors, fingerprint, keys, baseParsed, delta }) {
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
  const task = runAiRefreshTask({ key, source, aiAnchors, fingerprint, keys, baseParsed, delta })
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
'''
marker = 'function previousAnchorSnapshot(previous, source) {'
if marker not in s:
    raise SystemExit('root cache insertion marker missing')
s = s.replace(marker, cache_helpers + '\n' + marker, 1)

old_prev = "  const previous = body?.previous_scan\n  if (!previous || typeof previous !== 'object' || Array.isArray(previous)) return null"
new_prev = (
    "  const previous = body?.previous_scan\n"
    "  if (!previous || typeof previous !== 'object' || Array.isArray(previous)) return null\n"
    "  if (previous.ai_refresh_pending === true || ['AI_REFRESH_PENDING', 'STALE_WHILE_AI_REFRESH'].includes(previous.cache_status)) return null"
)
s = replace_exact(s, old_prev, new_prev, 'root pending previous guards', count=2)

old_score = """  const knownHits = parsed.candidates.filter((item) => benchmark.currentGold.has(item.url)).length
  const knownRecall = benchmark.currentGold.size ? knownHits / benchmark.currentGold.size : null
  const groundedRate = parsed.rawCount ? (parsed.rawCount - parsed.rejectedUngrounded) / parsed.rawCount : 1
  const validRate = parsed.rawCount
    ? (parsed.rawCount - parsed.rejectedUngrounded - parsed.rejectedInvalid) / parsed.rawCount
    : 1
  const discoveryScore = knownRecall === null
    ? null
    : Math.round((0.75 * knownRecall + 0.20 * groundedRate + 0.05 * validRate) * 1000) / 10
"""
new_score = """  const aiRefreshPending = ['AI_REFRESH_PENDING', 'STALE_WHILE_AI_REFRESH'].includes(cacheStatus)
  const knownHits = parsed.candidates.filter((item) => benchmark.currentGold.has(item.url)).length
  const knownRecall = aiRefreshPending ? null : benchmark.currentGold.size ? knownHits / benchmark.currentGold.size : null
  const groundedRate = parsed.rawCount ? (parsed.rawCount - parsed.rejectedUngrounded) / parsed.rawCount : 1
  const validRate = parsed.rawCount
    ? (parsed.rawCount - parsed.rejectedUngrounded - parsed.rejectedInvalid) / parsed.rawCount
    : 1
  const discoveryScore = aiRefreshPending || knownRecall === null
    ? null
    : Math.round((0.75 * knownRecall + 0.20 * groundedRate + 0.05 * validRate) * 1000) / 10
"""
s = replace_exact(s, old_score, new_score, 'root pending score')
s = replace_exact(
    s,
    "    ai_called: aiCalled,\n    content_fingerprint: fingerprint,",
    "    ai_called: aiCalled,\n    ai_refresh_pending: aiRefreshPending,\n    content_fingerprint: fingerprint,",
    'root pending payload',
)

old_sync = """    const keys = getApiKeys()
    if (!keys.length) return sendJson(response, 503, { error: 'AI_RADAR_NOT_CONFIGURED' })
    const aiAnchors = previous ? previous.deltaAnchors : anchors
    const content = await callProvider(source, aiAnchors, keys)
    const freshParsed = parseCandidates(content, aiAnchors)
    const parsed = previous ? mergeParsed(previous.reusedParsed, freshParsed) : freshParsed
    const delta = previous ?? {
      newCount: anchors.length,
      changedCount: 0,
      removedCount: 0,
      reusedCount: 0,
    }
    return sendJson(response, 200, resultPayload({
      source, checkedAt, analyzedAt: checkedAt, allAnchors, anchors, fingerprint, parsed, benchmark,
      aiCalled: true,
      cacheStatus: previous ? 'FRESH_DELTA_AI' : 'FRESH_AI',
      aiAnalyzedAnchorCount: aiAnchors.length,
      delta,
      coverage,
    }))
"""
new_async = """    const cached = await readAiCache(source, anchors, fingerprint)
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
    const baseParsed = previous?.reusedParsed || (cached?.state === 'READY' ? cached.parsed : emptyParsed())
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
      source, aiAnchors, fingerprint, keys, baseParsed, delta,
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
"""
s = replace_exact(s, old_sync, new_async, 'root async handler')
path.write_text(s, encoding='utf-8')

# Continuation: no extra async state machine in this patch. Fix contract + disable Thinking + version handshake.
path = root / 'web/api/ai/_discoverContinuation.js'
s = path.read_text(encoding='utf-8')
s = replace_exact(
    s,
    "const ROOT_ANALYSIS_VERSION = 'agnes-discovery-live-v4-safe-next-page'",
    "const ROOT_ANALYSIS_VERSION = 'agnes-discovery-live-v5-async-cache'",
    'continuation root version',
)
s = replace_exact(
    s,
    "const CONTINUATION_ANALYSIS_VERSION = 'agnes-discovery-continuation-v1'",
    "const CONTINUATION_ANALYSIS_VERSION = 'agnes-discovery-continuation-v2'",
    'continuation version',
)
old_schema = """        max_candidates: 12,
        output_schema: {
          candidates: [{
            title: '对应输入标题',
            url: '必须与输入URL完全一致',
            signal_type: Array.from(SIGNAL_TYPES),
            confidence: '0到1',
            reason: '不超过80个汉字',
          }],
        },
"""
new_schema = """        max_candidates: 12,
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
"""
s = replace_exact(s, old_schema, new_schema, 'continuation contract')
s = replace_exact(
    s,
    "        temperature: 0,\n        max_tokens: 1400,\n        stream: false,",
    "        temperature: 0,\n        max_tokens: 1400,\n        stream: false,\n        chat_template_kwargs: { enable_thinking: false },",
    'continuation thinking off',
)
path.write_text(s, encoding='utf-8')

# Root client contract.
path = root / 'web/src/services/discoveryRadarApi.ts'
s = path.read_text(encoding='utf-8')
s = replace_exact(
    s,
    "  | 'REUSED_PARTIAL_COVERAGE'",
    "  | 'REUSED_PARTIAL_COVERAGE'\n  | 'SERVER_AI_CACHE'\n  | 'AI_REFRESH_PENDING'\n  | 'STALE_WHILE_AI_REFRESH'",
    'client cache status union',
)
s = replace_exact(
    s,
    "  analyzed_at: string\n  cache_status: DiscoveryCacheStatus",
    "  analyzed_at: string | null\n  cache_status: DiscoveryCacheStatus",
    'client nullable analyzed_at',
)
s = replace_exact(
    s,
    "  ai_called: boolean\n  content_fingerprint: string",
    "  ai_called: boolean\n  ai_refresh_pending: boolean\n  content_fingerprint: string",
    'client pending field',
)
s = replace_exact(
    s,
    "function previousScanPayload(result: DiscoveryRadarResult | undefined) {\n  if (!result) return undefined",
    "function previousScanPayload(result: DiscoveryRadarResult | undefined) {\n  if (!result || result.ai_refresh_pending) return undefined",
    'client pending previous guard',
)
s = replace_exact(
    s,
    "      typeof body?.ai_called !== 'boolean' ||\n      typeof body?.new_anchor_count !== 'number' ||",
    "      typeof body?.ai_called !== 'boolean' ||\n      typeof body?.ai_refresh_pending !== 'boolean' ||\n      !(body?.analyzed_at === null || (typeof body?.analyzed_at === 'string' && Number.isFinite(Date.parse(body.analyzed_at)))) ||\n      typeof body?.new_anchor_count !== 'number' ||",
    'client pending response validation',
)
path.write_text(s, encoding='utf-8')

# Pending scans do not count as zero-yield success or mutate historical findings.
path = root / 'web/src/services/discoveryRadarStore.ts'
s = path.read_text(encoding='utf-8')
start = s.index('export function recordDiscoverySuccess(')
end = s.index('export function recordDiscoveryFailure(', start)
replacement = '''export function recordDiscoverySuccess(
  current: DiscoverySourceStats | undefined,
  result: DiscoveryRadarResult,
): DiscoverySourceStats {
  const base = current ?? blankStats()
  const pending = result.ai_refresh_pending === true
  const novel = result.candidates.filter((item) => item.verification_status === 'DISCOVERED_UNVERIFIED').length
  return {
    scan_count: base.scan_count + 1,
    ai_call_count: base.ai_call_count + (result.ai_called ? 1 : 0),
    cache_hit_count: base.cache_hit_count + (!result.ai_called && !pending ? 1 : 0),
    total_candidate_count: base.total_candidate_count + (pending ? 0 : result.candidate_count),
    total_novel_candidate_count: base.total_novel_candidate_count + (pending ? 0 : novel),
    consecutive_failure_count: 0,
    consecutive_zero_candidate_count: pending
      ? base.consecutive_zero_candidate_count
      : result.candidate_count === 0 ? base.consecutive_zero_candidate_count + 1 : 0,
    last_checked_at: result.checked_at,
    last_error: null,
  }
}

'''
s = s[:start] + replacement + s[end:]
path.write_text(s, encoding='utf-8')

# UI: explicit pending states and bounded automatic retries for a single-source scan only.
path = root / 'web/src/pages/DiscoveryRadarPage.tsx'
s = path.read_text(encoding='utf-8')
s = replace_exact(
    s,
    'const FINDINGS_RENDER_LIMIT = 500',
    'const FINDINGS_RENDER_LIMIT = 500\nconst AI_REFRESH_RETRY_DELAYS_MS = [4_000, 8_000, 12_000] as const',
    'ui retry delays',
)
s = replace_exact(
    s,
    "function cacheStatusText(result: DiscoveryRadarResult) {\n  if (result.cache_status === 'FRESH_DELTA_AI') {",
    "function cacheStatusText(result: DiscoveryRadarResult) {\n"
    "  if (result.cache_status === 'AI_REFRESH_PENDING') return 'AI后台分析中 · 当前没有把空结果当成无商机'\n"
    "  if (result.cache_status === 'STALE_WHILE_AI_REFRESH') return '先显示上次仍可复用结果 · AI正在后台刷新变化链接'\n"
    "  if (result.cache_status === 'SERVER_AI_CACHE') return 'AI后台结果已就绪 · 本次直接读取服务器缓存'\n"
    "  if (result.cache_status === 'FRESH_DELTA_AI') {",
    'ui cache text',
)
s = replace_exact(
    s,
    '  const scanOne = async (sourceId: string, options?: { preserveBusy?: boolean; forceAi?: boolean }) => {',
    '  const scanOne = async (sourceId: string, options?: { preserveBusy?: boolean; forceAi?: boolean; autoRetry?: boolean; retryAttempt?: number }) => {',
    'ui scan options',
)
old_success = """      setWorkspace((current) => ({
        ...current,
        results: { ...current.results, [sourceId]: result },
        stats: { ...current.stats, [sourceId]: recordDiscoverySuccess(current.stats[sourceId], result) },
        findings: mergeDiscoveryFindings(current.findings, result),
      }))
      return true
"""
new_success = """      setWorkspace((current) => ({
        ...current,
        results: { ...current.results, [sourceId]: result },
        stats: { ...current.stats, [sourceId]: recordDiscoverySuccess(current.stats[sourceId], result) },
        findings: result.ai_refresh_pending ? current.findings : mergeDiscoveryFindings(current.findings, result),
      }))
      if (result.ai_refresh_pending && options?.autoRetry !== false) {
        const attempt = options?.retryAttempt ?? 0
        const delay = AI_REFRESH_RETRY_DELAYS_MS[attempt]
        if (delay !== undefined) {
          window.setTimeout(() => {
            void scanOne(sourceId, { preserveBusy: true, autoRetry: true, retryAttempt: attempt + 1 })
          }, delay)
        }
      }
      return true
"""
s = replace_exact(s, old_success, new_success, 'ui pending success')
s = replace_exact(
    s,
    '      await scanOne(sources[index].id, { preserveBusy: true })',
    '      await scanOne(sources[index].id, { preserveBusy: true, autoRetry: false })',
    'ui multi scan no autopoll',
)
path.write_text(s, encoding='utf-8')

# Continuation client version handshake.
path = root / 'web/src/services/discoveryContinuationApi.ts'
s = path.read_text(encoding='utf-8')
s = replace_exact(
    s,
    "analysis_version: 'agnes-discovery-continuation-v1'",
    "analysis_version: 'agnes-discovery-continuation-v2'",
    'continuation client type',
)
s = replace_exact(
    s,
    "body?.analysis_version === 'agnes-discovery-continuation-v1'",
    "body?.analysis_version === 'agnes-discovery-continuation-v2'",
    'continuation client validator',
)
path.write_text(s, encoding='utf-8')

# Static regression guards for the new serving contract.
test_path = root / 'web/pipeline/tests/test_agnes_async_cache.py'
test_path.write_text(r'''from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class AgnesAsyncCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        cls.continuation = (WEB_ROOT / 'api' / 'ai' / '_discoverContinuation.js').read_text(encoding='utf-8')
        cls.client = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')
        cls.store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        cls.page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        cls.continuation_client = (WEB_ROOT / 'src' / 'services' / 'discoveryContinuationApi.ts').read_text(encoding='utf-8')

    def test_root_uses_wait_until_runtime_cache_and_longer_background_budget(self) -> None:
        self.assertIn("import { getCache, waitUntil } from '@vercel/functions'", self.root)
        self.assertIn('export const config = { maxDuration: 45 }', self.root)
        self.assertIn('BACKGROUND_PROVIDER_TIMEOUT_MS = 25_000', self.root)
        self.assertIn("AI_CACHE_PREFIX = 'medicalchannelai:agnes-discovery:v1'", self.root)
        self.assertIn('waitUntil(task)', self.root)
        self.assertIn("state: 'PENDING'", self.root)
        self.assertIn("state: 'READY'", self.root)
        self.assertIn("state: 'FAILED'", self.root)

    def test_root_cache_key_is_hashed_and_bound_to_analysis_and_content(self) -> None:
        start = self.root.index('function aiCacheKey(')
        end = self.root.index('function cachedCandidateRows', start)
        block = self.root[start:end]
        self.assertIn("createHash('sha256')", block)
        self.assertIn('ANALYSIS_VERSION', block)
        self.assertIn('fingerprint', block)
        self.assertIn('aiCacheSourceSignature(source)', block)
        self.assertNotIn('source.name}:', block)

    def test_agnes3_thinking_is_disabled_on_root_and_continuation(self) -> None:
        expected = 'chat_template_kwargs: { enable_thinking: false }'
        self.assertIn(expected, self.root)
        self.assertIn(expected, self.continuation)
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.root)
        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", self.continuation)

    def test_pending_is_explicit_and_never_reused_as_completed_scan(self) -> None:
        self.assertIn("'AI_REFRESH_PENDING'", self.client)
        self.assertIn("'STALE_WHILE_AI_REFRESH'", self.client)
        self.assertIn("'SERVER_AI_CACHE'", self.client)
        self.assertIn('ai_refresh_pending: boolean', self.client)
        self.assertIn('if (!result || result.ai_refresh_pending) return undefined', self.client)
        self.assertIn('previous.ai_refresh_pending === true', self.root)
        self.assertIn('AI后台分析中', self.page)
        self.assertIn('AI_REFRESH_RETRY_DELAYS_MS', self.page)

    def test_pending_does_not_claim_zero_yield_or_merge_findings(self) -> None:
        self.assertIn('const pending = result.ai_refresh_pending === true', self.store)
        self.assertIn('pending ? 0 : result.candidate_count', self.store)
        self.assertIn('base.consecutive_zero_candidate_count', self.store)
        self.assertIn('result.ai_refresh_pending ? current.findings : mergeDiscoveryFindings', self.page)

    def test_multi_scan_does_not_spawn_client_poll_storm(self) -> None:
        self.assertIn('{ preserveBusy: true, autoRetry: false }', self.page)

    def test_continuation_contract_is_single_enum_and_versioned_with_root(self) -> None:
        self.assertIn("ROOT_ANALYSIS_VERSION = 'agnes-discovery-live-v5-async-cache'", self.continuation)
        self.assertIn("CONTINUATION_ANALYSIS_VERSION = 'agnes-discovery-continuation-v2'", self.continuation)
        self.assertIn('allowed_signal_types: Array.from(SIGNAL_TYPES)', self.continuation)
        self.assertIn("signal_type: '单个字符串枚举值'", self.continuation)
        self.assertNotIn('signal_type: Array.from(SIGNAL_TYPES)', self.continuation)
        self.assertIn("analysis_version: 'agnes-discovery-continuation-v2'", self.continuation_client)


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')

print('async-cache patch prepared locally')
