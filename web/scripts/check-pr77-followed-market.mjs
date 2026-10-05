// Synthetic source -> actual save/read routes -> actual API/local projections -> matcher.
// SQL, authentication, HTTP and browser storage are in-memory; no DB or network.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

function moduleUrl(path, prelude = '', exports = '') {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8')
  const parsed = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true)
  const statements = parsed.statements.filter(node => !ts.isImportDeclaration(node))
  const printed = ts.createPrinter().printFile(ts.factory.updateSourceFile(parsed, statements))
  const js = ts.transpileModule(prelude + printed + exports, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  return `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
}
const evidence = new URL('../shared/awardEvidence.js', import.meta.url).href
const ids = moduleUrl('../src/utils/opportunityId.ts')
const numbers = moduleUrl('../src/utils/projectNumber.ts')
const storageUrl = moduleUrl('../src/services/localFollowupStore.ts')
const store = await import(storageUrl)
const { ApiTodayActionsService } = await import(moduleUrl('../src/services/ApiTodayActionsService.ts',
  `import { normalizeAwardEvidenceSnapshot } from ${JSON.stringify(evidence)};`))
const { findAwardForProject } = await import(moduleUrl('../src/services/verifiedOpportunityPool.ts',
  `import { normalizeProjectNumber } from ${JSON.stringify(numbers)};`))
function followedModule(apiMode) {
  return import(moduleUrl('../src/services/followedApi.ts', `
    import { isStableOpportunityId } from ${JSON.stringify(ids)};
    import { listStoredFollowups } from ${JSON.stringify(storageUrl)};
    const isApiMode = ${apiMode}; const apiBaseUrl = '/offline';
    const todayActionsService = { getTodayActions: async () => ({cards: []}) };
  `))
}
const api = await followedModule(true)
const local = await followedModule(false)
const backend = await import(moduleUrl('../api/_privateCore.js', `
  import { createHash, randomUUID } from 'node:crypto';
  const privateDatabaseConfigured = () => true;
  const privateDb = () => globalThis.__pr77Followed.sql;
  const authenticatedUser = async () => globalThis.__pr77Followed.user;
  const readJsonBody = request => request.body;
  const sendJson = (response, status, body) => { response.status = status; response.body = body; };
  const loadVerifiedSnapshot = async () => globalThis.__pr77Followed.snapshot;
  const findVerifiedSnapshotCard = (snapshot, id) => snapshot.cards.find(card => card.opportunity_id === id && card.facts.verification_status === 'VERIFIED');
`))
const originalFetch = globalThis.fetch
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
const memory = new Map()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: key => memory.get(key) ?? null,
  setItem: (key, value) => memory.set(key, value), removeItem: key => memory.delete(key),
}})
const base = JSON.parse(readFileSync(new URL('./fixtures/pr77-legacy-award-snapshot.json', import.meta.url), 'utf8'))
const sourceCard = structuredClone(base.cards[0])
sourceCard.opportunity_id = 'synthetic_tj_followed_market'
Object.assign(sourceCard.facts, { market_code: 'TJ', project_number: 'SYNTHETIC-2026-001',
  project_name: '合成公开设备项目', hospital_name: '合成医院', buyer_name: '合成医院',
  region: '天津（合成）', verification_status: 'VERIFIED' })
sourceCard.evidence_source_urls = ['https://official.invalid/synthetic']
const snapshot = { ...base, cards: [sourceCard], opportunity_pool: [sourceCard], award_ledger: [],
  awarded_project_count: 0, award_price_reference: null }
const user = { id: 'synthetic-user', organization_id: 'synthetic-org' }
const when = '2026-10-04T00:00:00Z'
let row = null
let events = []
async function sql(strings, ...values) {
  const query = strings.join('?').replace(/\s+/g, ' ').trim()
  if (query.startsWith('INSERT INTO private_followups')) {
    row = { id: values[0], opportunity_id: values[3], status: 'NEW', remind_at: null,
      public_snapshot: values[4], updated_at: when, latest_note: null }
    return []
  }
  if (query.startsWith('INSERT INTO private_followup_events')) {
    events.push({ id: values[0], status: values[4], note: values[5], reason: values[6], remind_at: values[7], created_at: when })
    return [{ id: values[0] }]
  }
  if (query.startsWith('UPDATE private_followups')) {
    Object.assign(row, { status: values[0], remind_at: values[1], public_snapshot: values[2] })
    return []
  }
  if (query.includes('FROM private_followup_events') && query.includes('mutation_id')) return []
  if (query.startsWith('SELECT id, status, note, reason, remind_at, created_at')) return structuredClone(events)
  if (query.includes('FROM private_followups')) return row ? [structuredClone(row)] : []
  throw new Error('UNEXPECTED_SYNTHETIC_SQL')
}
sql.json = value => JSON.parse(JSON.stringify(value))
sql.begin = operation => operation(sql)
globalThis.__pr77Followed = { sql, snapshot, user }
async function route(name, query = {}, body, method = 'GET') {
  const response = { setHeader() {} }
  await backend.default({ method, query: { route: name, ...query }, body }, response)
  assert.equal(response.status, 200, JSON.stringify(response.body))
  return structuredClone(response.body)
}
globalThis.fetch = async (value) => {
  const url = new URL(String(value), 'https://offline.invalid')
  const data = url.pathname.endsWith('/today') ? structuredClone(snapshot)
    : url.pathname === '/offline/followed' ? await route('followed', Object.fromEntries(url.searchParams))
    : url.pathname.startsWith('/offline/followup/') ? await route('followup', { id: decodeURIComponent(url.pathname.split('/').pop()) })
    : (() => { throw new Error('UNEXPECTED_SYNTHETIC_HTTP') })()
  return { ok: true, status: 200, json: async () => data }
}
const entries = [{ project_number: sourceCard.facts.project_number, market_code: 'HE', award_id: 'he' },
                 { project_number: sourceCard.facts.project_number, market_code: 'TJ', award_id: 'tj' }]
const failures = []
let checks = 0
async function check(name, operation) {
  checks++
  try { await operation(); console.log(`${name}: PASS`) }
  catch (error) { failures.push(name); console.error(`${name}: FAIL: ${error.message}`) }
}
function match(item, projectField = 'project_number') {
  return findAwardForProject(entries, item.facts[projectField], item.facts.market_code)
}
function storedFixture(market = 'TJ') {
  row = { id: 'synthetic-row', opportunity_id: sourceCard.opportunity_id, status: 'REVIEWING',
    remind_at: null, updated_at: when, latest_note: null,
    public_snapshot: { facts: { ...sourceCard.facts, budget_cny: null }, evidence_source_urls: sourceCard.evidence_source_urls } }
  if (market === undefined) delete row.public_snapshot.facts.market_code
  else row.public_snapshot.facts.market_code = market
}
try {
  const card = (await new ApiTodayActionsService('/source').getTodayActions()).cards[0]
  assert.equal(card.facts.market_code, 'TJ', 'source adapter already preserves market')
  card.followup_status = 'REVIEWING'
  await check('API verified source -> mutation JSON -> followed list/exact/history -> same-market award', async () => {
    row = null; events = []
    await route('followup', { id: sourceCard.opportunity_id }, {
      status: 'REVIEWING', mutation_id: 'followup:00000000-0000-4000-8000-000000000001', market_code: 'HE',
    }, 'POST')
    assert.equal(row.public_snapshot.facts.market_code, 'TJ', 'saved snapshot lost source market')
    for (const item of [(await api.getFollowedOpportunities())[0], await api.getFollowedOpportunityById(card.opportunity_id)]) {
      assert.equal(item.facts.market_code, 'TJ'); assert.equal(match(item), entries[1])
    }
    const history = await api.getHistoricalFollowedOpportunityCard(card.opportunity_id)
    assert.equal(history.facts.market_code, 'TJ'); assert.equal(match(history, 'project_code'), entries[1])
  })
  await check('API stored market survives server sanitizer and historical projection', async () => {
    storedFixture('TJ')
    assert.equal((await route('followed', { id: card.opportunity_id })).item.facts.market_code, 'TJ')
    assert.equal((await api.getHistoricalFollowedOpportunityCard(card.opportunity_id)).facts.market_code, 'TJ')
  })
  await check('API strict facts accepts only legacy or optional nullable market extension', async () => {
    storedFixture()
    const payload = await route('followed', { id: card.opportunity_id })
    payload.item.facts.market_code = 'TJ'
    const savedFetch = globalThis.fetch
    try {
      globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => structuredClone(payload) })
      assert.equal((await api.getFollowedOpportunityById(card.opportunity_id)).facts.market_code, 'TJ')
      payload.item.facts.market_code = null
      assert.equal((await api.getFollowedOpportunityById(card.opportunity_id)).facts.market_code, null)
      delete payload.item.facts.market_code
      assert.equal((await api.getFollowedOpportunityById(card.opportunity_id)).facts.market_code ?? null, null)
      for (const changed of [{ market_code: 42 }, { market_code: {} }, { market_code: ['TJ'] }, { unexpected: 'x' }]) {
        const before = structuredClone(payload.item.facts)
        Object.assign(payload.item.facts, changed)
        await assert.rejects(() => api.getFollowedOpportunityById(card.opportunity_id), /FOLLOWED_RESPONSE_INVALID/)
        payload.item.facts = before
      }
      delete payload.item.facts.region
      await assert.rejects(() => api.getFollowedOpportunityById(card.opportunity_id), /FOLLOWED_RESPONSE_INVALID/)
    } finally { globalThis.fetch = savedFetch }
  })
  await check('Local actual persist -> JSON read -> followed list/exact/history -> same-market award', async () => {
    memory.clear(); store.persistLocalFollowup(card)
    assert.equal(store.readLocalFollowups()[card.opportunity_id].public_snapshot.facts.market_code, 'TJ')
    for (const item of [(await local.getFollowedOpportunities())[0], await local.getFollowedOpportunityById(card.opportunity_id)]) {
      assert.equal(item.facts.market_code, 'TJ'); assert.equal(match(item), entries[1])
    }
    const history = store.getStoredHistoricalOpportunityCard(card.opportunity_id)
    assert.equal(history.facts.market_code, 'TJ'); assert.equal(match(history, 'project_code'), entries[1])
  })
  await check('Local saved market survives reload without current source-card backfill', async () => {
    memory.clear(); store.persistLocalFollowup(card)
    const encoded = JSON.parse(memory.values().next().value)
    encoded[card.opportunity_id].public_snapshot.facts.market_code = 'TJ'
    memory.set('medopp.pipeline-followups.v1', JSON.stringify(encoded))
    assert.equal((await local.getFollowedOpportunities())[0].facts.market_code, 'TJ')
    assert.equal(store.getStoredHistoricalOpportunityCard(card.opportunity_id).facts.market_code, 'TJ')
  })
  await check('Missing/legacy market remains unmatched despite TJ id/region/buyer cues', async () => {
    storedFixture(null)
    delete row.public_snapshot.facts.market_code
    assert.equal(match((await api.getFollowedOpportunities())[0]), null)
    assert.equal(match(await api.getHistoricalFollowedOpportunityCard(card.opportunity_id), 'project_code'), null)
    memory.clear()
    const old = structuredClone(card); delete old.facts.market_code
    store.persistLocalFollowup(old)
    assert.equal(match((await local.getFollowedOpportunities())[0]), null)
    assert.equal(match(store.getStoredHistoricalOpportunityCard(card.opportunity_id), 'project_code'), null)
    const encoded = JSON.parse(memory.values().next().value)
    encoded[card.opportunity_id].public_snapshot.facts.market_code = 42
    memory.set('medopp.pipeline-followups.v1', JSON.stringify(encoded))
    assert.equal(match((await local.getFollowedOpportunities())[0]), null)
  })
  await check('Same-number different markets and marketless award entries never substitute', async () => {
    storedFixture('BJ')
    assert.equal(match((await api.getFollowedOpportunities())[0]), null)
    const he = structuredClone(card); he.facts.market_code = 'HE'
    memory.clear(); store.persistLocalFollowup(he)
    assert.equal(match((await local.getFollowedOpportunities())[0]), entries[0])
    assert.equal(findAwardForProject([{ ...entries[1], market_code: undefined }], card.facts.project_code, 'TJ'), null)
  })
  await check('Historical projection changes only market field; other snapshot facts preserved', async () => {
    memory.clear(); store.persistLocalFollowup(card)
    const history = store.getStoredHistoricalOpportunityCard(card.opportunity_id)
    assert.equal(history.facts.project_code, card.facts.project_code)
    assert.equal(history.facts.project_name, card.facts.project_name)
    assert.equal(history.facts.hospital, card.facts.hospital)
    assert.deepEqual(history.evidence_source_urls, card.evidence_source_urls)
    assert.equal(history.match_status, 'ARCHIVE')
  })
} finally {
  globalThis.fetch = originalFetch
  if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage)
  else delete globalThis.localStorage
  delete globalThis.__pr77Followed
}
console.log(`Followed market-chain regression: ${checks} cases, ${failures.length} failures`)
assert.deepEqual(failures, [])
