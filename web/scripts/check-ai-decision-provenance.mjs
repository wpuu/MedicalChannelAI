import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../src/services/aiDecisionApi.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText

const decision = {
  action: '核对官方公告中的要求',
  reasons: ['依据已核验公开事实'],
  risks: [],
  needs_human_confirmation: ['执行前由人工核实'],
}
const asOf0 = '2026-10-03T01:00:00.000Z'
const asOf1 = '2026-10-03T02:00:00.000Z'

function meta({ asOf = asOf0, source = 'DATABASE', origin = null, degraded = false, complete = true } = {}) {
  return {
    snapshot_as_of: asOf,
    source,
    runtime_origin: origin,
    degraded,
    reason: null,
    collection_coverage: {
      complete,
      last_complete_as_of: complete ? asOf : null,
      updated_source_ids: ['tjmugh'],
      failed_source_ids: [],
    },
  }
}

function card(id, snapshotMeta = meta()) {
  return {
    opportunity_id: id,
    model_decision_status: 'AWAITING_MODEL',
    decision: null,
    snapshot_meta: snapshotMeta,
    customer_context: {
      target_hospital: null,
      hospital_relationship: null,
      matching_product_capabilities: [],
      partnering_policy: {
        can_find_manufacturer: null,
        can_partner_channel: null,
        can_handle_lease: null,
      },
    },
    facts: { registration_deadline: null, bid_deadline: null },
    match_status: 'MATCHED',
    recommendation_mode: 'OPEN_WINDOW',
  }
}

function createClient({ apiMode = true, respond }) {
  const storage = new Map()
  let requests = 0
  const fetch = async (_url, options) => {
    requests += 1
    const body = JSON.parse(options.body)
    const payload = await respond(body, requests)
    return { ok: true, status: 200, json: async () => payload }
  }
  const module = { exports: {} }
  const context = vm.createContext({
    exports: module.exports,
    module,
    require(name) {
      if (name === './apiConfig') return { isApiMode: apiMode }
      if (name === './aiRequestGate') return { beginAiRequest: () => true, endAiRequest() {} }
      throw new Error(`Unexpected import: ${name}`)
    },
    fetch,
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    Date,
    JSON,
    Object,
    Array,
    Map,
    Set,
    Number,
    String,
    Boolean,
    Math,
    Error,
    TypeError,
    setTimeout,
  })
  vm.runInContext(compiled, context, { filename: 'aiDecisionApi.js' })
  return { api: module.exports, storage, requests: () => requests }
}

function response(snapshotMeta, items) {
  return {
    snapshot_as_of: snapshotMeta.snapshot_as_of,
    snapshot_source_mode: snapshotMeta.source,
    snapshot_runtime_origin: snapshotMeta.runtime_origin,
    requested_count: items.length,
    ready_count: items.filter((item) => item.status === 'READY').length,
    cache_hit_count: 0,
    items,
  }
}

{
  const currentMeta = meta({ asOf: asOf1 })
  const client = createClient({
    respond: async () => response(currentMeta, [
      { opportunity_id: 'current', status: 'READY', decision },
      { opportunity_id: 'old', status: 'READY', decision },
    ]),
  })
  const result = await client.api.requestAiDecisionBatch([
    card('current', currentMeta),
    card('old', meta({ asOf: asOf0 })),
  ])
  assert.equal(result.decisions.current.action, decision.action)
  assert.equal(result.decisions.old, undefined)
  assert.equal(result.errors.old, 'AI_SNAPSHOT_VERSION_MISMATCH')
  assert.equal(client.requests(), 1)
}

{
  const client = createClient({ respond: async () => response(meta(), [{ opportunity_id: 'external', status: 'READY', decision }]) })
  const result = await client.api.requestAiDecisionBatch([
    card('external', meta({ source: 'EXTERNAL' })),
  ])
  assert.equal(result.decisions.external, undefined)
  assert.equal(result.errors.external, 'AI_SNAPSHOT_PROVENANCE_UNAVAILABLE')
  assert.equal(client.requests(), 0)
}

{
  const unsuitableCards = [
    card('degraded', meta({ degraded: true })),
    card('partial', meta({ complete: false })),
    card('runtime-origin-unknown', meta({ source: 'RUNTIME_CACHE' })),
  ]
  const client = createClient({ respond: async () => response(meta(), []) })
  const result = await client.api.requestAiDecisionBatch(unsuitableCards)
  for (const item of unsuitableCards) {
    assert.equal(result.errors[item.opportunity_id], 'AI_SNAPSHOT_PROVENANCE_UNAVAILABLE')
  }
  assert.equal(client.requests(), 0)
}

{
  const runtimeMeta = meta({ source: 'RUNTIME_CACHE', origin: 'PUBLISHED' })
  const client = createClient({
    respond: async () => response(meta({ source: 'RUNTIME_CACHE', origin: 'BUNDLED' }), [
      { opportunity_id: 'runtime', status: 'READY', decision },
    ]),
  })
  const result = await client.api.requestAiDecisionBatch([card('runtime', runtimeMeta)])
  assert.equal(result.decisions.runtime, undefined)
  assert.equal(result.errors.runtime, 'AI_SNAPSHOT_VERSION_MISMATCH')
}

{
  const client = createClient({ respond: async () => response(meta({ asOf: asOf1 }), [{ opportunity_id: 'one', status: 'READY', decision }]) })
  await assert.rejects(
    () => client.api.requestAiDecision(card('one', meta())),
    (error) => error?.code === 'AI_SNAPSHOT_VERSION_MISMATCH',
  )
  assert.equal(client.requests(), 1, 'deterministic version mismatch is not retried')
}

{
  const currentMeta = meta()
  const client = createClient({
    respond: async () => ({ ...response(currentMeta, []), opportunity_id: 'single', decision }),
  })
  assert.equal((await client.api.requestAiDecision(card('single', currentMeta))).action, decision.action)
  assert.equal(client.requests(), 1)
}

{
  const oldMeta = meta()
  const bundledMeta = meta({ source: 'BUNDLED' })
  const client = createClient({
    apiMode: false,
    respond: async (body, requestNumber) => {
      const activeMeta = requestNumber === 3 ? bundledMeta : oldMeta
      if (body.cache_only) return response(activeMeta, [{ opportunity_id: 'local', status: 'MISS' }])
      return {
        ...response(activeMeta, []),
        opportunity_id: 'local',
        decision,
      }
    },
  })
  await client.api.requestAiDecision(card('local', oldMeta))
  const sameVersion = await client.api.hydrateCachedAiDecisions([card('local', oldMeta)])
  assert.equal(sameVersion[0].decision.action, decision.action)
  const differentSource = await client.api.hydrateCachedAiDecisions([card('local', bundledMeta)])
  assert.equal(differentSource[0].decision, null)
  assert.equal(client.requests(), 3)
}

{
  const client = createClient({
    apiMode: false,
    respond: async () => response(meta(), [{ opportunity_id: 'legacy', status: 'MISS' }]),
  })
  client.storage.set('medopp.grounded-ai-decisions.v2', JSON.stringify([{
    snapshot_as_of: asOf0,
    opportunity_id: 'legacy',
    context_fingerprint: '00000000',
    cached_at: asOf0,
    decision,
  }]))
  const hydrated = await client.api.hydrateCachedAiDecisions([card('legacy')])
  assert.equal(hydrated[0].decision, null)
}

console.log('AI decision provenance: PASS (batch isolation, source gate, single mismatch/no retry, card-scoped local cache, legacy cache rejection)')
