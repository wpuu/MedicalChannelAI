import assert from 'node:assert/strict'
import { checkPreviewBinding, DIAGNOSTIC_BRANCH } from '../api/_previewBindingCheck.js'

const env = {
  VERCEL_ENV: 'preview', VERCEL_GIT_COMMIT_REF: DIAGNOSTIC_BRANCH,
  VERCEL_GIT_COMMIT_SHA: '1'.repeat(40), DATABASE_URL: 'synthetic-secret-url',
}
let passed = 0
async function test(name, run) { await run(); passed++; console.log('PASS ' + name) }
const forbidden = () => { throw new Error('UNEXPECTED_CONNECTION') }
for (const [name, method, patch, diagnostic] of [
  ['POST makes no connection', 'POST', {}, 'GET_ONLY'],
  ['production makes no connection', 'GET', { VERCEL_ENV: 'production' }, 'PREVIEW_BRANCH_REQUIRED'],
  ['other branch makes no connection', 'GET', { VERCEL_GIT_COMMIT_REF: 'main' }, 'PREVIEW_BRANCH_REQUIRED'],
  ['unknown commit makes no connection', 'GET', { VERCEL_GIT_COMMIT_SHA: '' }, 'DEPLOYED_COMMIT_UNCONFIRMED'],
  ['missing URL makes no connection', 'GET', { DATABASE_URL: '' }, 'DATABASE_BINDING_UNCONFIGURED'],
]) await test(name, async () => {
  const r = await checkPreviewBinding(method, { ...env, ...patch }, forbidden)
  assert.equal(r.body.diagnostic, diagnostic); assert.equal(r.body.stopped, true)
})

function fixture(rows, fail = false) {
  const calls = []
  return { calls, connect(url, options) {
    calls.push({ url, options })
    return {
      async begin(mode, run) {
        calls.push({ mode })
        return run(async (strings, ...values) => {
          calls.push({ query: strings.join(''), values })
          if (fail) throw new Error('synthetic-secret-url synthetic-key')
          return rows
        })
      },
      async end(options) { calls.push({ end: options }) },
    }
  } }
}
for (const [name, rows, status, stopped] of [
  ['confirmed neondb', [{ matches_neondb: true, transaction_read_only: true }], 200, false],
  ['other database stops', [{ matches_neondb: false, transaction_read_only: true }], 409, true],
  ['read-only unconfirmed stops', [{ matches_neondb: true, transaction_read_only: false }], 503, true],
  ['missing row stops', [], 503, true],
]) await test(name, async () => {
  const f = fixture(rows); const r = await checkPreviewBinding('GET', env, f.connect)
  assert.equal(r.status, status); assert.equal(r.body.stopped, stopped)
  assert.equal(f.calls[0].options.connection.default_transaction_read_only, 'on')
  assert.equal(f.calls[1].mode, 'read only')
  assert.match(f.calls[2].query, /SELECT current_database\(\) = 'neondb'/)
  assert.doesNotMatch(f.calls[2].query, /\bFROM\b|\b(?:INSERT|UPDATE|DELETE|CREATE|ALTER)\b/i)
  assert.deepEqual(f.calls[2].values, []); assert.equal(f.calls.length, 4)
  assert.ok(!JSON.stringify(r).includes(env.DATABASE_URL))
})
await test('driver failure stops without disclosing error or retry', async () => {
  const f = fixture([], true); const r = await checkPreviewBinding('GET', env, f.connect)
  assert.equal(r.status, 503); assert.equal(r.body.stopped, true)
  assert.ok(!JSON.stringify(r).includes('synthetic-key')); assert.equal(f.calls.length, 4)
})
console.log(JSON.stringify({ test_kind: 'synthetic_diagnostic_unit', passed, failed: 0,
  live_database_queries: 0, business_data_writes: 0 }))
