import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

// Execute the production module bodies. Only imports of the external database
// and Runtime Cache are replaced; no validation or publishing logic is stubbed.
const directory = await mkdtemp(join(tmpdir(), 'medical-publish-preflight-'))
const registryName = '__medicalPublishPreflightTest'
const previousRegistry = globalThis[registryName]
const previousToken = process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN
const previousFetch = globalThis.fetch
const bundleUrl = new URL('../public/data/today-actions.public.json', import.meta.url)
const bundle = JSON.parse(await readFile(bundleUrl, 'utf8'))
const now = Date.now()
const candidate = () => ({ ...structuredClone(bundle), snapshot_as_of: new Date(now).toISOString() })
const changed = (snapshot) => ({ ...structuredClone(snapshot), coverage_warning: 'offline changed revision' })
function reorderKeys(value) {
  if (Array.isArray(value)) return value.map(reorderKeys)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.keys(value).reverse().map((key) => [key, reorderKeys(value[key])]))
}
const partialCandidate = () => ({
  ...candidate(),
  collection_coverage: { complete: false, last_complete_as_of: null, updated_source_ids: ['tjnothop'], failed_source_ids: ['tjmugh', 'ccgp_regional:he'] },
})
const state = {
  current: null, durableLatest: null, durableWrites: 0, cacheWrites: 0,
  cacheFailure: false, advanceDuringPersist: false, persistOptions: null,
}
const cache = {
  async get() { return structuredClone(state.current) },
  async set(_key, value) {
    if (state.cacheFailure) throw new Error('RUNTIME_CACHE_UNAVAILABLE')
    state.cacheWrites += 1
    state.current = structuredClone(value)
  },
}

function replaceImport(source, pattern, replacement) {
  assert.match(source, pattern, 'Production import changed; update offline dependency wiring')
  return source.replace(pattern, replacement)
}

try {
  globalThis.fetch = async () => { throw new Error('Real network requests forbidden in this offline check') }
  globalThis[registryName] = {
    cache,
    latestPublicVerifiedSnapshotIfChanged: async () => null,
    latestPublicVerifiedSnapshotForPublish: async () => state.durableLatest,
    persistPublicVerifiedSnapshot: async (snapshot, options) => {
      state.persistOptions = options
      state.durableWrites += 1
      if (state.advanceDuringPersist) {
        state.current = { ...candidate(), snapshot_as_of: new Date(now + 60_000).toISOString() }
      }
      return { configured: true, persisted: true, snapshot_hash: 'offline-accepted-hash' }
    },
  }
  let verifiedSource = await readFile(new URL('../api/_verifiedSnapshot.js', import.meta.url), 'utf8')
  verifiedSource = replaceImport(verifiedSource, /import \{ getCache \} from '@vercel\/functions'/,
    `const getCache = () => globalThis.${registryName}.cache`)
  verifiedSource = replaceImport(verifiedSource,
    /import \{[^}]*\} from '\.\/_publicIntelligenceDb\.js'/,
    `const { latestPublicVerifiedSnapshotIfChanged, latestPublicVerifiedSnapshotForPublish } = globalThis.${registryName}`)
  verifiedSource = replaceImport(verifiedSource,
    /from '\.\.\/public\/data\/today-actions\.public\.json'/, `from '${bundleUrl.href}'`)
  verifiedSource = replaceImport(verifiedSource,
    /from '\.\/_medicalChannelScope\.js'/,
    `from '${new URL('../api/_medicalChannelScope.js', import.meta.url).href}'`)
  const verifiedPath = join(directory, 'verified.mjs')
  await writeFile(verifiedPath, verifiedSource)

  let endpointSource = await readFile(new URL('../api/public-snapshot.js', import.meta.url), 'utf8')
  endpointSource = replaceImport(endpointSource, /from '\.\/_verifiedSnapshot\.js'/,
    `from '${pathToFileURL(verifiedPath).href}'`)
  endpointSource = replaceImport(endpointSource,
    /import \{ persistPublicVerifiedSnapshot \} from '\.\/_publicIntelligenceDb\.js'/,
    `const { persistPublicVerifiedSnapshot } = globalThis.${registryName}`)
  const endpointPath = join(directory, 'endpoint.mjs')
  await writeFile(endpointPath, endpointSource)
  const handler = (await import(pathToFileURL(endpointPath).href)).default
  process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = 'offline-publish-test-token'

  async function invoke(value, overrides = {}) {
    Object.assign(state, {
      current: null, durableLatest: null, durableWrites: 0, cacheWrites: 0,
      cacheFailure: false, advanceDuringPersist: false, persistOptions: null,
    }, overrides)
    const response = {
      statusCode: null, body: null, setHeader() {},
      status(code) { this.statusCode = code; return this },
      json(value) { this.body = value; return this },
    }
    await handler({ method: 'PUT', body: value, headers: { authorization: 'Bearer offline-publish-test-token' } }, response)
    return response
  }

  for (const [value, overrides, expected] of [
    [{ ...candidate(), snapshot_as_of: new Date(now + 86_400_000).toISOString() }, {}, 'RUNTIME_SNAPSHOT_FUTURE_REJECTED'],
    [{ ...candidate(), snapshot_as_of: 'invalid' }, {}, 'VERIFIED_SNAPSHOT_AS_OF_INVALID'],
    [{ ...candidate(), public_note: 'x'.repeat(2 * 1024 * 1024) }, {}, 'RUNTIME_SNAPSHOT_TOO_LARGE'],
    [changed(candidate()), { current: candidate() }, 'RUNTIME_SNAPSHOT_REVISION_CONFLICT'],
    [candidate(), { current: { ...candidate(), snapshot_as_of: new Date(now + 60_000).toISOString() } }, 'RUNTIME_SNAPSHOT_ROLLBACK_REJECTED'],
    [changed(candidate()), { durableLatest: { payload: candidate() } }, 'PUBLIC_SNAPSHOT_REVISION_CONFLICT'],
    [candidate(), { durableLatest: { payload: { ...candidate(), snapshot_as_of: new Date(now + 60_000).toISOString() } } }, 'PUBLIC_SNAPSHOT_ROLLBACK_REJECTED'],
  ]) {
    const response = await invoke(value, overrides)
    assert.ok(response.statusCode >= 400, expected)
    assert.equal(response.body.error, expected)
    assert.equal(state.durableWrites, 0, `${expected}: durable writes`)
    assert.equal(state.cacheWrites, 0, `${expected}: cache writes`)
  }

  let response = await invoke(candidate())
  assert.equal(response.statusCode, 200)
  assert.equal(state.durableWrites, 1)
  assert.equal(state.cacheWrites, 1)

  response = await invoke(candidate(), { current: reorderKeys(candidate()) })
  assert.equal(response.statusCode, 200)
  assert.equal(state.cacheWrites, 0)

  response = await invoke(candidate(), { cacheFailure: true, current: bundle })
  assert.equal(response.statusCode, 503)
  assert.equal(response.body.durable_accepted, true)
  assert.equal(response.body.snapshot_as_of, candidate().snapshot_as_of)
  assert.equal(response.body.snapshot_hash, 'offline-accepted-hash')
  assert.equal(state.durableWrites, 1)
  assert.equal(state.cacheWrites, 0)
  assert.deepEqual(state.current, bundle)

  response = await invoke(candidate(), { advanceDuringPersist: true })
  assert.equal(response.statusCode, 409)
  assert.equal(response.body.error, 'RUNTIME_SNAPSHOT_ROLLBACK_REJECTED')
  assert.equal(response.body.durable_accepted, true)
  assert.equal(state.cacheWrites, 0)
  assert.equal(state.current.snapshot_as_of, new Date(now + 60_000).toISOString())

  const durableBase = { ...candidate(), snapshot_as_of: new Date(now - 60_000).toISOString() }
  for (const current of [null, bundle, { invalid: true }]) {
    response = await invoke(partialCandidate(), { current, durableLatest: { payload: durableBase } })
    assert.equal(response.statusCode, 409)
    assert.equal(response.body.error, 'PUBLIC_SNAPSHOT_BASE_UNAVAILABLE')
    assert.equal(state.durableWrites, 0)
    assert.equal(state.cacheWrites, 0)
    assert.deepEqual(state.current, current)
  }
  const baseHash = 'a'.repeat(64)
  response = await invoke(partialCandidate(), { current: durableBase, durableLatest: { payload: durableBase, snapshot_hash: baseHash } })
  assert.equal(response.statusCode, 200)
  assert.equal(state.durableWrites, 1)
  assert.equal(state.persistOptions.requireBaseMatch, true)
  assert.equal(state.persistOptions.expectedBaseHash, baseHash)
  assert.equal(state.persistOptions.expectedBaseAsOf, durableBase.snapshot_as_of)

  response = await invoke({
    ...candidate(),
    collection_coverage: {
      complete: true, last_complete_as_of: candidate().snapshot_as_of,
      updated_source_ids: ['ccgp_regional:he'], failed_source_ids: [],
    },
  })
  assert.equal(response.statusCode, 200)
  assert.equal(state.durableWrites, 1)
  assert.equal(state.persistOptions.requireBaseMatch, false)
} finally {
  globalThis.fetch = previousFetch
  if (previousRegistry === undefined) delete globalThis[registryName]
  else globalThis[registryName] = previousRegistry
  if (previousToken === undefined) delete process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN
  else process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN = previousToken
  await rm(directory, { recursive: true, force: true })
}
console.log('Publish preflight: PASS (invalid writes=0; accepted durable/cache failure and concurrent advance reported accurately)')
