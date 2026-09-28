import { createHash } from 'node:crypto'
import { privateDatabaseConfigured, privateDb } from './_privateDb.js'

/**
 * Cross-instance rate limiting for scarce AI provider work.
 *
 * Vercel runs many concurrent function instances, so a per-instance Map lets
 * one client exceed the intended budget by N×. This helper keeps the cheap
 * in-memory limiter as a first line (and as the fallback), and — when the
 * Neon database is configured — also counts hits in a shared fixed-window
 * table with a single atomic upsert.
 *
 * Fail-open by design: a slow or failing database never blocks users; the
 * per-instance limiter still applies. Client IPs are stored only as salted
 * SHA-256 digests.
 */

export const RATE_LIMIT_DB_TIMEOUT_MS = 1500
const LOCAL_BUCKET_SWEEP_THRESHOLD = 500
const CLEANUP_PROBABILITY = 0.02
const RETENTION_INTERVAL = '1 hour'

const localBuckets = new Map()
let tablePromise = null

function firstHeader(value) {
  if (Array.isArray(value)) return value[0]
  return typeof value === 'string' ? value : undefined
}

export function clientRateKey(request) {
  const forwarded = firstHeader(request?.headers?.['x-forwarded-for'])
  return forwarded?.split(',')[0]?.trim() || firstHeader(request?.headers?.['x-real-ip']) || 'unknown-client'
}

function bucketDigest(scope, key) {
  const salt = String(process.env.RATE_LIMIT_SALT || 'medicalchannelai-rate-limit-v1')
  return createHash('sha256').update(`${salt}\0${scope}\0${key}`).digest('hex')
}

function localExceeded(scope, key, limit, windowMs, now) {
  const bucketKey = `${scope}\0${key}`
  const current = localBuckets.get(bucketKey)
  if (!current || now - current.startedAt >= windowMs) {
    localBuckets.set(bucketKey, { startedAt: now, count: 1, windowMs })
  } else {
    current.count += 1
  }
  if (localBuckets.size > LOCAL_BUCKET_SWEEP_THRESHOLD) {
    for (const [itemKey, bucket] of localBuckets) {
      if (now - bucket.startedAt >= bucket.windowMs) localBuckets.delete(itemKey)
    }
  }
  return localBuckets.get(bucketKey).count > limit
}

function sharedStoreEnabled() {
  if (String(process.env.MCAI_RATE_LIMIT_STORE || '').trim().toLowerCase() === 'memory') return false
  return privateDatabaseConfigured()
}

async function ensureTable(sql) {
  if (!tablePromise) {
    tablePromise = (async () => {
      // Check first so warm starts don't emit "already exists" notices.
      const rows = await sql`SELECT to_regclass('mcai_rate_limits') IS NOT NULL AS present`
      if (rows[0]?.present) return
      await sql`
        CREATE TABLE IF NOT EXISTS mcai_rate_limits (
          bucket text NOT NULL,
          window_start timestamptz NOT NULL,
          hits integer NOT NULL,
          PRIMARY KEY (bucket, window_start)
        )
      `
    })().catch((error) => {
      tablePromise = null
      throw error
    })
  }
  return tablePromise
}

function withTimeout(promise, ms) {
  let timer = null
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('RATE_LIMIT_DB_TIMEOUT')), ms)
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer))
}

async function sharedHits(scope, key, windowMs, now) {
  const sql = privateDb()
  await ensureTable(sql)
  const windowStart = new Date(Math.floor(now / windowMs) * windowMs)
  const rows = await sql`
    INSERT INTO mcai_rate_limits (bucket, window_start, hits)
    VALUES (${bucketDigest(scope, key)}, ${windowStart}, 1)
    ON CONFLICT (bucket, window_start)
    DO UPDATE SET hits = mcai_rate_limits.hits + 1
    RETURNING hits
  `
  if (Math.random() < CLEANUP_PROBABILITY) {
    sql`DELETE FROM mcai_rate_limits WHERE window_start < now() - ${RETENTION_INTERVAL}::interval`.catch(() => {})
  }
  return Number(rows[0]?.hits) || 1
}

/**
 * Records one hit for (scope, client) and reports whether it exceeds `limit`
 * within `windowMs`. Returns { limited, source } where source is
 * 'local' | 'database' | 'local-fallback'.
 */
export async function consumeRateLimit(request, { scope, limit, windowMs }) {
  const now = Date.now()
  const key = clientRateKey(request)
  if (localExceeded(scope, key, limit, windowMs, now)) return { limited: true, source: 'local' }
  if (!sharedStoreEnabled()) return { limited: false, source: 'local' }
  try {
    const hits = await withTimeout(sharedHits(scope, key, windowMs, now), RATE_LIMIT_DB_TIMEOUT_MS)
    return { limited: hits > limit, source: 'database' }
  } catch {
    return { limited: false, source: 'local-fallback' }
  }
}

export function resetRateLimitForTests() {
  localBuckets.clear()
  tablePromise = null
}
