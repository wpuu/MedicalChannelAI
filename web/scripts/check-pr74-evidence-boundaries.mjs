import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { refreshLegalWindows } from '../api/_legalWindows.js'

const legacy = [{ code: 'DOCUMENT_CHALLENGE', anchor_date: '2026-09-22', deadline_date: '2026-10-09', remaining_working_days: 4, status: 'OPEN' }]
const before = structuredClone(legacy)
const refreshed = refreshLegalWindows(legacy, Date.parse('2026-09-29T00:00:00Z'))
assert.equal(refreshed[0].status, 'UNKNOWN')
assert.equal(refreshed[0].deadline_date, null)
assert.deepEqual(legacy, before)
console.log('PR74 server evidence boundary: PASS')

// Exercise the actual browser helper and rendered compact/full component.
const require = createRequire(import.meta.url)
function compile(source, fileName) {
  return ts.transpileModule(source, {
    fileName,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX },
  }).outputText
}
const utilitySource = readFileSync(new URL('../src/utils/legalWindows.ts', import.meta.url), 'utf8')
const utilityUrl = `data:text/javascript;base64,${Buffer.from(compile(utilitySource, 'legalWindows.ts')).toString('base64')}`
const utility = await import(utilityUrl)
assert.equal(utility.refreshLegalWindows(legacy, Date.now(), null)[0].status, 'UNKNOWN')
assert.equal(utility.legalWindowSummary({ legal_windows: legacy }).status, 'UNKNOWN')
const componentSource = readFileSync(new URL('../src/components/shared/LegalWindowNotice.tsx', import.meta.url), 'utf8')
let componentJs = compile(componentSource, 'LegalWindowNotice.tsx')
for (const [specifier, destination] of [
  ['@/utils/legalWindows', utilityUrl],
  ['react/jsx-runtime', pathToFileURL(require.resolve('react/jsx-runtime')).href],
  ['lucide-react', pathToFileURL(require.resolve('lucide-react')).href],
]) componentJs = componentJs.replaceAll(`"${specifier}"`, JSON.stringify(destination)).replaceAll(`'${specifier}'`, JSON.stringify(destination))
const { LegalWindowNotice } = await import(`data:text/javascript;base64,${Buffer.from(componentJs).toString('base64')}`)
for (const compact of [true, false]) {
  const html = renderToStaticMarkup(React.createElement(LegalWindowNotice, { card: { legal_windows: legacy, recommendation_mode: 'LATE_WINDOW' }, compact }))
  const visible = html.replace(/<[^>]+>/g, '')
  assert(visible.includes('条件性推算'))
  assert(visible.includes('非官方截止时间'))
  assert(visible.includes('尚待核验'))
  assert(!visible.includes('还剩') && !visible.includes('已过') && !visible.includes('最后一个工作日'))
}
console.log('PR74 browser and rendered UI evidence boundary: PASS')

// Load the actual service code with only network/storage imports replaced by fixtures.
const projectSource = readFileSync(new URL('../src/utils/projectNumber.ts', import.meta.url), 'utf8')
const projectUrl = `data:text/javascript;base64,${Buffer.from(compile(projectSource, 'projectNumber.ts')).toString('base64')}`
const serviceSource = readFileSync(new URL('../src/services/verifiedOpportunityPool.ts', import.meta.url), 'utf8')
const parsed = ts.createSourceFile('verifiedOpportunityPool.ts', serviceSource, ts.ScriptTarget.Latest, true)
const withoutImports = ts.factory.updateSourceFile(parsed, parsed.statements.filter((statement) => !ts.isImportDeclaration(statement)))
const fixtureKey = '__pr74EvidenceSnapshot'
const serviceJs = `import { refreshLegalWindows } from ${JSON.stringify(utilityUrl)};
import { normalizeProjectNumber } from ${JSON.stringify(projectUrl)};
const verifiedSnapshotUrl = 'offline:fixture';
const loadVerifiedSnapshotPayload = async () => globalThis[${JSON.stringify(fixtureKey)}];
${compile(ts.createPrinter().printFile(withoutImports), 'verifiedOpportunityPool.ts')}`
const service = await import(`data:text/javascript;base64,${Buffer.from(serviceJs).toString('base64')}`)
const entries = [
  { project_number: 'TJ-1', market_code: undefined, items: [{ unit_price_cny: 312000 }], legal_windows: legacy },
  { project_number: 'TJ-1', market_code: 'TJ', items: [{ unit_price_cny: 100, unit_price_basis: 'EXPLICIT_UNIT' }], legal_windows: legacy },
]
assert.equal(service.findAwardForProject(entries, 'TJ-1', 'HE'), null)
assert.equal(service.findAwardForProject(entries, 'TJ-1', undefined), null)
assert.equal(service.findAwardForProject(entries, 'ＴＪ－１', 'tj'), entries[1])
const ledger = service.refreshAwardLedger(entries, Date.now(), null)
assert.equal(ledger[0].items[0].unit_price_cny, null)
assert.equal(ledger[1].items[0].unit_price_cny, 100)
globalThis[fixtureKey] = {
  schema_version: '0.1', mode: 'TODAY_ACTIONS', cards: [], snapshot_as_of: '2026-09-29T00:00:00Z',
  award_price_reference: { families: [], rows: [{ family: 'OTHER', unit_price_cny: 312000 }, { family: 'CT', unit_price_cny: 100, unit_price_basis: 'EXPLICIT_UNIT' }] },
}
try {
  const { reference } = await service.getAwardPriceReference()
  assert.equal(reference.row_count, 1)
  assert.equal(reference.rows[0].unit_price_cny, 100)
  assert.deepEqual(reference.family_row_counts, { CT: 1 })
} finally { delete globalThis[fixtureKey] }
console.log('PR74 browser price and market boundary: PASS')
