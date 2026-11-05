import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('../src/services/runtimeStatusApi.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } })
const { runtimeSnapshotWarning, runtimeAutomationUnavailableReason } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const fresh = {
  ready: true, degraded: false,
  snapshot: { source_mode: 'DATABASE', available: true, freshness: 'FRESH', age_minutes: 1 },
}
assert.equal(runtimeSnapshotWarning(fresh), null)
const degraded = { ...fresh, degraded: true }
assert.match(runtimeSnapshotWarning(degraded), /部分信息源/)
assert.equal(runtimeAutomationUnavailableReason(degraded), null, 'source-specific analysis stays server-authoritative')
const stale = { ...degraded, snapshot: { ...fresh.snapshot, freshness: 'STALE', age_minutes: 31 * 60 } }
assert.match(runtimeSnapshotWarning(stale), /31 小时/)
assert.match(runtimeAutomationUnavailableReason(stale), /已暂停/)
assert.equal(runtimeSnapshotWarning(degraded, false), null)
assert.match(runtimeAutomationUnavailableReason(null), /无法确认/)
console.log('Runtime degradation user messaging: PASS')
