// Regression checks for the AI provider latency strategy (MCAI-AI-RELIABILITY-001).
//
// Background: the previous design aborted every provider attempt after 12s and
// retried from scratch, switching to the alternate (.cn) region on its own
// timeout. Slow-but-valid answers became AI_TIMEOUT and users had to click the
// analyze button several times. These checks pin the replacement behavior:
//   - a slow first attempt is hedged by one parallel attempt on the same route
//   - the first valid answer wins and the loser is aborted
//   - our own timeout never reroutes to the alternate region
//   - one invalid model sample is retried once
//   - 401/403/429 stop immediately; attempts never exceed two
import { readFileSync } from 'node:fs'
import {
  callProviderWithTransientRetry,
  sanitizeSnapshotFacts,
} from '../api/ai/_analyzeCore.js'

const snapshot = JSON.parse(
  readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'),
)
const card = snapshot.cards?.[0]
if (!card) throw new Error('AI_HEDGE_TEST_NO_VERIFIED_CARD')

const providerArgs = {
  baseUrl: 'https://apihub.agnes-ai.com/v1',
  facts: sanitizeSnapshotFacts(card.facts),
  evidenceUrls: (card.evidence_source_urls || []).filter((url) => /^https:\/\//.test(url)),
  customerContext: null,
  windowStatus: 'OPEN',
  analysisAsOf: new Date().toISOString(),
}
const keys = ['fake-key-hedge']
const timing = { hedgeAfterMs: 40, totalBudgetMs: 400 }

function okResponse(actionCodes = ['VERIFY_REQUIREMENTS']) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ choices: [{ message: { content: JSON.stringify({ action_codes: actionCodes }) } }] }),
  }
}

function invalidResponse() {
  return {
    ok: true,
    status: 200,
    json: async () => ({ choices: [{ message: { content: 'not json at all' } }] }),
  }
}

// Resolves after `ms` unless aborted first (then rejects like real fetch).
function delayed(ms, value, signal, onAbort) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve(value), ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      onAbort?.()
      const error = new Error('aborted')
      error.name = 'AbortError'
      reject(error)
    }, { once: true })
  })
}

const savedFetch = globalThis.fetch
let attempts
let urls
let aborted

function reset(fetchImpl) {
  attempts = 0
  urls = []
  aborted = 0
  globalThis.fetch = async (url, options = {}) => {
    attempts += 1
    urls.push(String(url))
    return fetchImpl(attempts, options.signal)
  }
}

async function expectReject(promise, predicate, label) {
  try {
    await promise
  } catch (error) {
    if (!predicate(error)) throw new Error(`${label}: unexpected error ${error?.code || error?.message}`)
    return error
  }
  throw new Error(`${label}: expected rejection`)
}

try {
  // 1. Fast answer: no hedge is launched.
  reset((attempt, signal) => delayed(5, okResponse(), signal))
  await callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing)
  await new Promise((resolve) => setTimeout(resolve, 80))
  if (attempts !== 1) throw new Error(`AI_HEDGE_FAST_ANSWER_ATTEMPTS:${attempts}`)

  // 2. Slow first attempt: hedge wins, first attempt aborted, same route.
  reset((attempt, signal) =>
    attempt === 1
      ? delayed(10_000, okResponse(), signal, () => { aborted += 1 })
      : delayed(10, okResponse(), signal))
  const started = Date.now()
  const hedged = await callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing)
  if (!hedged?.action) throw new Error('AI_HEDGE_WINNER_DECISION_MISSING')
  if (attempts !== 2) throw new Error(`AI_HEDGE_ATTEMPTS:${attempts}`)
  if (aborted !== 1) throw new Error(`AI_HEDGE_LOSER_NOT_ABORTED:${aborted}`)
  if (new Set(urls).size !== 1) throw new Error('AI_HEDGE_CHANGED_ROUTE')
  if (Date.now() - started > 300) throw new Error('AI_HEDGE_TOO_SLOW')

  // 3. Slow first attempt still wins if it answers before the hedge.
  reset((attempt, signal) =>
    attempt === 1
      ? delayed(60, okResponse(), signal)
      : delayed(10_000, okResponse(), signal, () => { aborted += 1 }))
  await callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing)
  if (attempts !== 2 || aborted !== 1) throw new Error(`AI_HEDGE_FIRST_WINS:${attempts}/${aborted}`)

  // 4. Both attempts silent: AI_TIMEOUT after the budget, never the .cn route.
  reset((attempt, signal) => delayed(10_000, okResponse(), signal, () => { aborted += 1 }))
  const timeoutError = await expectReject(
    callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing),
    (error) => error?.code === 'AI_TIMEOUT' && Number(error?.status) === 408,
    'AI_HEDGE_TOTAL_BUDGET',
  )
  if (!timeoutError) throw new Error('AI_HEDGE_TOTAL_BUDGET_NO_ERROR')
  if (attempts !== 2) throw new Error(`AI_HEDGE_TIMEOUT_ATTEMPTS:${attempts}`)
  if (aborted !== 2) throw new Error(`AI_HEDGE_TIMEOUT_NOT_ABORTED:${aborted}`)
  if (urls.some((url) => url.includes('agnes-ai.cn'))) throw new Error('AI_TIMEOUT_MUST_NOT_SWITCH_REGION')

  // 5. One invalid model sample is retried once on the same route.
  reset((attempt, signal) => delayed(5, attempt === 1 ? invalidResponse() : okResponse(), signal))
  await callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing)
  if (attempts !== 2) throw new Error(`AI_INVALID_SAMPLE_RETRY_ATTEMPTS:${attempts}`)
  if (new Set(urls).size !== 1) throw new Error('AI_INVALID_SAMPLE_RETRY_CHANGED_ROUTE')

  // 6. Two invalid samples: surface AI_RESPONSE_INVALID, no third attempt.
  reset((attempt, signal) => delayed(5, invalidResponse(), signal))
  await expectReject(
    callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing),
    (error) => error?.code === 'AI_RESPONSE_INVALID',
    'AI_INVALID_TWICE',
  )
  await new Promise((resolve) => setTimeout(resolve, 80))
  if (attempts !== 2) throw new Error(`AI_INVALID_TWICE_ATTEMPTS:${attempts}`)

  // 7. Rate limit stops immediately and cancels the hedge.
  reset((attempt, signal) => delayed(5, { ok: false, status: 429 }, signal))
  await expectReject(
    callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing),
    (error) => Number(error?.status) === 429,
    'AI_429',
  )
  await new Promise((resolve) => setTimeout(resolve, 80))
  if (attempts !== 1) throw new Error(`AI_429_ATTEMPTS:${attempts}`)

  // 8. DNS failure still falls back to the alternate region exactly once.
  reset((attempt, signal) => {
    if (attempt === 1) {
      const error = new TypeError('fetch failed')
      error.cause = { code: 'ENOTFOUND' }
      return Promise.reject(error)
    }
    return delayed(5, okResponse(), signal)
  })
  await callProviderWithTransientRetry(providerArgs, keys, card.opportunity_id, timing)
  if (attempts !== 2) throw new Error(`AI_DNS_FALLBACK_ATTEMPTS:${attempts}`)
  if (!urls[1]?.startsWith('https://apihub.agnes-ai.cn/v1/')) throw new Error('AI_DNS_FALLBACK_ROUTE')

  // 9. Budget must stay inside the function maxDuration with headroom for DB/auth.
  const core = readFileSync(new URL('../api/ai/_analyzeCore.js', import.meta.url), 'utf8')
  const vercel = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  const maxDuration = vercel.functions?.['api/ai/analyze.js']?.maxDuration
  const budget = Number(core.match(/PROVIDER_TOTAL_BUDGET_MS = ([\d_]+)/)?.[1].replace(/_/g, ''))
  if (!maxDuration || !budget || budget / 1000 > maxDuration - 10) {
    throw new Error(`AI_PROVIDER_BUDGET_EXCEEDS_FUNCTION_LIMIT:${budget}/${maxDuration}`)
  }
  const db = readFileSync(new URL('../api/_publicIntelligenceDb.js', import.meta.url), 'utf8')
  const briefFn = db.slice(db.indexOf('export async function getOrCreateSharedPublicAiBrief'))
  const briefBody = briefFn.slice(0, briefFn.indexOf('\n}\n'))
  if (/sql\.begin|pg_advisory/.test(briefBody)) {
    throw new Error('AI_BRIEF_MUST_NOT_HOLD_TRANSACTION_DURING_GENERATION')
  }

  console.log('AI provider hedge/timeout strategy: PASS')
} finally {
  globalThis.fetch = savedFetch
}
