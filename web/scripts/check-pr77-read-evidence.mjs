import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
import ts from 'typescript'
import { spawnSync } from 'node:child_process'
import { AWARD_EVIDENCE_VERSION, normalizeAwardLedger, normalizeAwardEvidenceSnapshot } from '../shared/awardEvidence.js'

process.on('uncaughtException', (e) => { console.error(e.message); process.exitCode = 1 })
const legacy = JSON.parse(readFileSync(new URL('./fixtures/pr77-legacy-award-snapshot.json', import.meta.url), 'utf8'))
const bundle = JSON.parse(readFileSync(new URL('../public/data/today-actions.public.json', import.meta.url), 'utf8'))
const original = structuredClone(legacy)
const source = readFileSync(new URL('../api/_verifiedSnapshot.js', import.meta.url), 'utf8')
const apiDirectory = resolve(new URL('../api', import.meta.url).pathname)
const isolated = source
  .replace(/^import \{ getCache \}.*$/m, 'const getCache = () => globalThis.__pr77Cache')
  .replace(/^import \{ latestPublicVerifiedSnapshotIfChanged \}.*$/m, 'const latestPublicVerifiedSnapshotIfChanged = async () => globalThis.__pr77Db')
  .replace(/^import bundledSnapshot .*$/m, `const bundledSnapshot = ${JSON.stringify(bundle)}`)
  .replace(/from '(\.\.?\/[^']+)'/g, (_, p) => `from ${JSON.stringify(pathToFileURL(resolve(apiDirectory, p)).href)}`)
const loader = await import(`data:text/javascript;base64,${Buffer.from(isolated).toString('base64')}`)
const saved = { fetch: globalThis.fetch, remote: process.env.VERIFIED_SNAPSHOT_URL, region: process.env.VERCEL_REGION, publicRemote: process.env.VITE_VERIFIED_SNAPSHOT_URL }
const failures = []
function check(name, operation) { try { operation(); console.log(`${name}: PASS`) } catch (e) { failures.push(`${name}: ${e.message}`) } }
function safe(snapshot) {
  for (const entry of snapshot.award_ledger ?? []) {
    for (const window of entry.legal_windows ?? []) assert.equal(window.status, 'UNKNOWN')
    assert.equal(entry.total_amount_cny, null)
    for (const pkg of entry.packages ?? []) assert.equal(pkg.amount_cny, null)
    for (const item of entry.items ?? []) assert.equal(item.unit_price_cny, null)
  }
  for (const card of [...(snapshot.cards ?? []), ...(snapshot.opportunity_pool ?? [])])
    for (const window of card.legal_windows ?? []) assert.equal(window.status, 'UNKNOWN')
  assert.equal(snapshot.awarded_project_count, 0)
}
try {
  process.env.VITE_VERIFIED_SNAPSHOT_URL = ''
  for (const mode of ['DATABASE', 'REMOTE', 'RUNTIME_CACHE', 'BUNDLE']) {
    loader.clearVerifiedSnapshotCacheForTests()
    process.env.VERIFIED_SNAPSHOT_URL = mode === 'REMOTE' ? 'https://offline.invalid/snapshot' : ''
    process.env.VERCEL_REGION = mode === 'RUNTIME_CACHE' ? 'offline' : ''
    globalThis.__pr77Db = mode === 'DATABASE' ? { snapshot_hash: 'a'.repeat(64), payload: legacy } : null
    const newer = { ...structuredClone(legacy), snapshot_as_of: new Date(Date.parse(bundle.snapshot_as_of) + 60000).toISOString() }
    globalThis.__pr77Cache = { get: async key => key.includes(':published:') ? newer : bundle, set: async () => {}, delete: async () => {} }
    globalThis.fetch = async () => ({ ok: true, headers: { get: () => null }, text: async () => JSON.stringify(newer) })
    const selected = await loader.loadVerifiedSnapshot()
    check(`${mode} rejects old derived closure and returns safe data`, () => safe(selected))
  }
  const projection = spawnSync('python3', ['-c', `
import json, sys
sys.path[:0] = ['.', 'tests']
from test_ccgp_award import _parse, TJ_MULTI_URL
from test_public_snapshot_awards import AS_OF
from medical_channel_pipeline.ccgp_award import public_award_ledger_entry
from medical_channel_pipeline.award_price_reference import build_award_price_reference
award = _parse('ccgp_award_tianjin_multi_package.html', TJ_MULTI_URL, market_code='TJ')
print(json.dumps({'ledger': public_award_ledger_entry(award, AS_OF), 'reference': build_award_price_reference([award], AS_OF)}))
`], { cwd: resolve(new URL('../pipeline', import.meta.url).pathname), encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } })
  assert.equal(projection.status, 0, projection.stderr)
  const explicit = JSON.parse(projection.stdout)
  const positive = { ...structuredClone(legacy), award_projection_version: AWARD_EVIDENCE_VERSION, awarded_project_count: 0, award_ledger: [explicit.ledger], award_price_reference: explicit.reference }
  function known(snapshot) {
    const entry = snapshot.award_ledger[0]
    assert.equal(entry.total_amount_cny, 9320000)
    assert.equal(entry.packages[0].amount_cny, 2375000)
    assert.equal(entry.items[0].unit_price_cny, 2375000)
    assert.equal(snapshot.award_price_reference.row_count, 4)
    for (const card of [...snapshot.cards, ...(snapshot.opportunity_pool ?? [])])
      for (const window of card.legal_windows ?? []) assert.equal(window.status, 'UNKNOWN')
    for (const window of entry.legal_windows ?? []) assert.equal(window.status, 'UNKNOWN')
  }
  for (const [kind, candidate, verify] of [
    ['legacy zero retirement', { ...structuredClone(legacy), awarded_project_count: 0 }, safe],
    ['current explicit evidence', positive, known],
  ]) {
    for (const mode of ['DATABASE', 'REMOTE', 'RUNTIME_CACHE']) {
      loader.clearVerifiedSnapshotCacheForTests()
      process.env.VERIFIED_SNAPSHOT_URL = mode === 'REMOTE' ? 'https://offline.invalid/snapshot' : ''
      process.env.VERCEL_REGION = mode === 'RUNTIME_CACHE' ? 'offline' : ''
      const input = structuredClone(candidate)
      // DATABASE deliberately uses the exact bundled revision. Other lanes use
      // a newer clock; neither a hash nor a clock substitutes for field evidence.
      if (mode !== 'DATABASE') input.snapshot_as_of = new Date(Date.parse(bundle.snapshot_as_of) + 60000).toISOString()
      globalThis.__pr77Db = mode === 'DATABASE' ? { snapshot_hash: 'b'.repeat(64), payload: input } : null
      globalThis.__pr77Cache = { get: async key => key.includes(':published:') ? input : bundle, set: async () => {}, delete: async () => {} }
      globalThis.fetch = async () => ({ ok: true, headers: { get: () => null }, text: async () => JSON.stringify(input) })
      const output = await loader.loadVerifiedSnapshot()
      check(`${mode} ${kind}`, () => verify(output))
      const expectedMode = mode === 'DATABASE' ? 'DATABASE' : mode
      assert.equal(loader.verifiedSnapshotSourceMode(), expectedMode)
      assert.deepEqual(input.award_ledger, candidate.award_ledger)
    }
  }
  const oldLabel = structuredClone(legacy.award_ledger)
  oldLabel[0].items[0].unit_price_basis = 'EXPLICIT_UNIT'
  const masked = normalizeAwardLedger(oldLabel)
  assert.equal(masked[0].items[0].unit_price_cny, null, 'old price label lacks the checked projection contract')
  assert.equal(masked[0].total_amount_cny, null)
  assert.equal(masked[0].packages[0].amount_cny, null)
  assert.throws(() => normalizeAwardEvidenceSnapshot(legacy), /AWARD_EVIDENCE_LEGACY_RETIRED_POOL/)
  const noFieldBasis = structuredClone(positive)
  delete noFieldBasis.award_ledger[0].total_amount_basis
  delete noFieldBasis.award_ledger[0].packages[0].amount_basis
  const noBasis = normalizeAwardEvidenceSnapshot(noFieldBasis)
  assert.equal(noBasis.award_ledger[0].total_amount_cny, null)
  assert.equal(noBasis.award_ledger[0].packages[0].amount_cny, null)
  const bareCard = normalizeAwardEvidenceSnapshot(legacy.cards[0])
  for (const window of bareCard.legal_windows ?? []) assert.equal(window.status, 'UNKNOWN')
  // Actual API-mode service with only transport stubbed. Legacy retirement must
  // be rejected; a zero-retirement payload still needs amount/window masking.
  const serviceSource = readFileSync(new URL('../src/services/ApiTodayActionsService.ts', import.meta.url), 'utf8')
  const serviceJs = ts.transpileModule(serviceSource, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
    .replace(/from '(\.\.?\/[^']+)'/g, (_, p) => `from ${JSON.stringify(pathToFileURL(resolve(new URL('../src/services', import.meta.url).pathname, p)).href)}`)
  const { ApiTodayActionsService } = await import(`data:text/javascript;base64,${Buffer.from(serviceJs).toString('base64')}`)
  globalThis.fetch = async () => ({ ok: true, json: async () => structuredClone(legacy) })
  let rejected = false
  try { await new ApiTodayActionsService('offline:fixture').getTodayActions() } catch { rejected = true }
  check('API rejects a legacy already-retired pool', () => assert(rejected))
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ ...structuredClone(legacy), awarded_project_count: 0 }) })
  const api = await new ApiTodayActionsService('offline:fixture').getTodayActions()
  check('API masks total/package/unit and card/pool/ledger windows', () => safe(api))
  globalThis.fetch = async () => ({ ok: true, json: async () => structuredClone(positive) })
  const knownApi = await new ApiTodayActionsService('offline:fixture').getTodayActions()
  check('API preserves explicit total/package/unit evidence', () => { assert.equal(knownApi.award_ledger[0].total_amount_cny, 9320000); assert.equal(knownApi.award_ledger[0].items[0].unit_price_cny, 2375000) })
  // Exercise the real deduplicated browser loader, static Today service and
  // pool service. Only local customer/follow-up state is replaced by identity
  // functions; the evidence and card projections are the production code.
  function browserModule(path, prelude = '') {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')
    const parsed = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true)
    const statements = parsed.statements.filter(node => !ts.isImportDeclaration(node))
    const output = ts.transpileModule(prelude + ts.createPrinter().printFile(ts.factory.updateSourceFile(parsed, statements)), {
      compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    }).outputText
    return `data:text/javascript;base64,${Buffer.from(output).toString('base64')}`
  }
  const evidenceUrl = new URL('../shared/awardEvidence.js', import.meta.url).href
  const clientUrl = browserModule('../src/services/verifiedSnapshotClient.ts', `
    import { normalizeAwardEvidenceSnapshot } from ${JSON.stringify(evidenceUrl)};
    const verifiedSnapshotUrl = 'offline:fixture';
  `)
  const legalUrl = browserModule('../src/utils/legalWindows.ts')
  const projectUrl = browserModule('../src/utils/projectNumber.ts')
  const localState = `
    const backfillLocalFollowupSnapshots = () => {};
    const hydrateLocalFollowups = cards => cards;
    const personalizeTrialCards = cards => cards;
    const persistLocalFollowup = () => { throw new Error('READ_ONLY_TEST'); };
  `
  const poolUrl = browserModule('../src/services/verifiedOpportunityPool.ts', `
    import { normalizeAwardLedger, normalizeAwardPriceReference, normalizeEvidenceLegalWindows } from ${JSON.stringify(evidenceUrl)};
    import { normalizeProjectNumber } from ${JSON.stringify(projectUrl)};
    import { loadVerifiedSnapshotPayload } from ${JSON.stringify(clientUrl)};
    const verifiedSnapshotUrl = 'offline:fixture';
    ${localState}
  `)
  const staticUrl = browserModule('../src/services/StaticSnapshotTodayActionsService.ts', `
    import { refreshLegalWindows } from ${JSON.stringify(legalUrl)};
    import { refreshAwardLedger } from ${JSON.stringify(poolUrl)};
    import { loadVerifiedSnapshotPayload } from ${JSON.stringify(clientUrl)};
    ${localState}
  `)
  const client = await import(clientUrl)
  const pool = await import(poolUrl)
  const { StaticSnapshotTodayActionsService } = await import(staticUrl)
  // Keep actionability active independently of when this offline test is run.
  const activeDate = new Date(Date.now() + 30 * 86400000).toISOString()
  const browserLegacy = { ...structuredClone(legacy), awarded_project_count: 0 }
  for (const card of [...browserLegacy.cards, ...browserLegacy.opportunity_pool]) {
    card.facts.bid_deadline = activeDate
    card.facts.registration_deadline = activeDate
  }
  for (const [name, input, expectedAmount] of [
    ['legacy without retired projects', browserLegacy, null],
    ['current explicit evidence', { ...browserLegacy, award_projection_version: AWARD_EVIDENCE_VERSION, award_ledger: positive.award_ledger, award_price_reference: positive.award_price_reference }, 9320000],
  ]) {
    client.resetVerifiedSnapshotClient()
    globalThis.fetch = async () => ({ ok: true, json: async () => structuredClone(input) })
    const staticData = await new StaticSnapshotTodayActionsService('offline:fixture').getTodayActions()
    const poolData = await pool.getVerifiedOpportunityPool()
    const prices = await pool.getAwardPriceReference()
    check(`STATIC and POOL ${name}`, () => {
      for (const output of [staticData, poolData]) {
        assert.equal(output.award_ledger[0].total_amount_cny, expectedAmount)
        for (const card of output.cards) for (const window of card.legal_windows ?? []) assert.equal(window.status, 'UNKNOWN')
      }
      assert.equal(prices.reference.row_count, expectedAmount === null ? 0 : 4)
    })
  }
  client.resetVerifiedSnapshotClient()
  globalThis.fetch = async () => ({ ok: true, json: async () => structuredClone(legacy) })
  await assert.rejects(() => new StaticSnapshotTodayActionsService('offline:fixture').getTodayActions(), /AWARD_EVIDENCE_LEGACY_RETIRED_POOL/)
  client.resetVerifiedSnapshotClient()
  await assert.rejects(() => pool.getVerifiedOpportunityPool(), /AWARD_EVIDENCE_LEGACY_RETIRED_POOL/)
  // A failed load isn't memoized: retry with a safe snapshot at the same URL.
  globalThis.fetch = async () => ({ ok: true, json: async () => structuredClone(browserLegacy) })
  assert((await pool.getVerifiedOpportunityPool()).cards.length > 0)
  assert.deepEqual(legacy, original, 'canonical legacy evidence must not be mutated')
} finally {
  globalThis.fetch = saved.fetch
  for (const [key, value] of [['VERIFIED_SNAPSHOT_URL', saved.remote], ['VERCEL_REGION', saved.region], ['VITE_VERIFIED_SNAPSHOT_URL', saved.publicRemote]]) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value
  }
  delete globalThis.__pr77Db; delete globalThis.__pr77Cache
}
assert.deepEqual(failures, [])
console.log('PR77 legacy evidence read paths: PASS')
