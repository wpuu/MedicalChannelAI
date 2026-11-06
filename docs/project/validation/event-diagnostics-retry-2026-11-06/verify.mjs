// Offline evidence check: node docs/project/validation/event-diagnostics-retry-2026-11-06/verify.mjs
import {readFileSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
import {dirname,join,basename} from 'node:path'
import {createHash} from 'node:crypto'
import assert from 'node:assert/strict'
const dir=dirname(fileURLToPath(import.meta.url))
const raw=name=>readFileSync(join(dir,name)),read=name=>JSON.parse(raw(name))
const hash=bytes=>createHash('sha256').update(bytes).digest('hex')
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v
const micros=value=>{
  const iso=value.replace(' ','T').replace(/([+-]\d{2})$/,'$1:00')
  const fraction=iso.match(/\.(\d{1,6})/)?.[1]||''
  const ms=Date.parse(iso.replace(/\.\d+/,''));assert(Number.isFinite(ms))
  return BigInt(ms)*1000n+BigInt(fraction.padEnd(6,'0'))
}
const manifest=read('manifest.json')
for(const f of manifest.files){assert.equal(basename(f.path),f.path);const bytes=raw(f.path);assert.equal(bytes.length,f.bytes);assert.equal(hash(bytes),f.sha256)}
const proof=read('publication-proof.json'),terminal=read('deep-terminal.json'),snapshot=read('published-snapshot.json'),browser=read('browser-smoke-report.json')
const digest=hash(JSON.stringify(canonical(snapshot)))
assert.equal(hash(JSON.stringify(canonical(read('deep-published-snapshot.json')))),proof.deep_publish.sha256)
assert.equal(digest,proof.serving_sha256);assert.equal(digest,browser.payload_sha256)
const row=read('database-publication-metadata.json').find(row=>row.snapshot_hash===digest);assert(row)
assert.equal(micros(row.sql_as_of),micros(row.payload_as_of));assert.equal(micros(row.payload_as_of),micros(snapshot.snapshot_as_of))
assert.equal(terminal.collector.active_cycle_id,null);assert.equal(terminal.collector.stages.publish.status,'COMPLETED')
assert.equal(Object.keys(terminal.collector.stages).length,25);assert(Object.values(terminal.collector.stages).every(row=>['COMPLETED','DEGRADED'].includes(row.status)))
assert.equal(browser.checks.length,6);assert.equal(browser.pass,true);assert.equal(browser.pool,snapshot.opportunity_pool.length)
const status=read('published-status.json').response;assert.equal(status.commit,manifest.scope.commit.slice(0,7));assert.equal(status.preview_epoch,manifest.scope.preview_epoch);assert.equal(status.snapshot.source_mode,'DATABASE')
assert.equal(browser.scope.commit,manifest.ui_scope.commit);assert.equal(browser.ui_status.commit,manifest.ui_scope.commit.slice(0,7));assert.equal(browser.ui_status.preview_epoch,manifest.scope.preview_epoch)
const retry=read('retry-diagnostics-proof.json');assert(retry.profiles.length>0)
for(const item of retry.profiles){const seconds=Number(micros(item.terminal_completed_at)-micros(item.last_failed_at))/1e6;assert(seconds>=0&&seconds<30);assert(Math.abs(seconds-item.failure_to_terminal_seconds)<1e-9);assert.equal(item.actual_attempt_count,2)}
assert(retry.event_failure_observations.length>0)
for(const row of retry.event_failure_observations){const d=row.diagnostics;assert(d.failure_count>0);assert.equal(Object.values(d.reason_counts).reduce((a,b)=>a+b,0),d.failure_count);assert.equal(Object.values(d.phase_counts).reduce((a,b)=>a+b,0),d.failure_count);assert(d.samples.length<=5);for(const sample of d.samples){assert(/^[a-f0-9]{64}$/.test(sample.candidate_ref));assert(/^[A-Z][A-Z0-9_]*$/.test(sample.reason));assert(['event_search','event_detail','event_scan'].includes(sample.phase));assert.deepEqual(Object.keys(sample).sort(),['candidate_ref','phase','reason'])}}
assert.equal(read('production-boundary.json').unchanged,true);assert.equal(read('access-cleanup.json').current_preview_share_revoked,true)
console.log(JSON.stringify({pass:true,artifact_count:manifest.files.length,executable_commit:manifest.scope.commit,payload_sha256:digest,sql_full_microseconds:true,native_retry_stages:retry.profiles.length,browser_checks:browser.checks.length}))
