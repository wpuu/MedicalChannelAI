// AI endpoints must use the cross-instance limiter (Neon-backed with an
// in-memory fallback) instead of per-instance Maps that scale with instance
// count. Behavior without a database is covered by check-ai-boundary.mjs.
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
const failures = []
const endpoints = {
  'api/ai/_analyzeCore.js': { scope: 'ai-analyze', call: 'await warmRateLimitExceeded(request)' },
  'api/ai/discover.js': { scope: 'ai-discover', call: 'await rateLimited(request)' },
  'api/ai/_discoverContinuation.js': { scope: 'ai-discover-continuation', call: 'await rateLimited(request)' },
}
for (const [path, { scope, call }] of Object.entries(endpoints)) {
  const source = read(path)
  if (!source.includes("from '../_sharedRateLimit.js'")) failures.push(`${path} must import _sharedRateLimit.js`)
  if (!source.includes(`scope: '${scope}'`)) failures.push(`${path} must use rate-limit scope ${scope}`)
  if (/rateBuckets\s*=\s*new Map/.test(source)) failures.push(`${path} still keeps a per-instance rate Map`)
  if (!source.includes(call)) failures.push(`${path} must call ${call}`)
}
const limiter = read('api/_sharedRateLimit.js')
for (const needle of [
  'ON CONFLICT (bucket, window_start)',
  'RATE_LIMIT_DB_TIMEOUT_MS',
  "source: 'local-fallback'",
  "createHash('sha256')",
  'MCAI_RATE_LIMIT_STORE',
]) {
  if (!limiter.includes(needle)) failures.push(`_sharedRateLimit.js missing: ${needle}`)
}
if (failures.length) {
  console.error('Shared rate limit check failed:\n- ' + failures.join('\n- '))
  process.exit(1)
}
console.log('Shared rate limit check passed.')
