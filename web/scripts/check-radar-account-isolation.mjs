import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import {
  activateDiscoveryWorkspaceForAccount,
  clearActiveDiscoveryWorkspaceAccount,
  discoveryAccountToken,
  discoveryWorkspaceDbKey,
  discoveryWorkspaceIsAccountScoped,
  discoveryWorkspaceStorageKey,
} from '../src/services/discoveryWorkspaceAccountIsolation.js'

class MemoryStorage {
  constructor() { this.values = new Map() }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null }
  setItem(key, value) { this.values.set(String(key), String(value)) }
  removeItem(key) { this.values.delete(String(key)) }
}

const LEGACY_BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.bootstrap.v4'
const UNOWNED_BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.unowned.v2.bootstrap'
const SCOPE_A = '0123456789abcdef0123456789abcdef'
const SCOPE_B = 'fedcba9876543210fedcba9876543210'

const storage = new MemoryStorage()
globalThis.window = { localStorage: storage }

const tokenA = discoveryAccountToken(SCOPE_A)
const tokenB = discoveryAccountToken(SCOPE_B)
assert.equal(tokenA, SCOPE_A)
assert.equal(tokenB, SCOPE_B)
assert.notEqual(tokenA, tokenB)
assert.equal(discoveryAccountToken(SCOPE_A.toUpperCase()), SCOPE_A)
assert.throws(() => discoveryAccountToken('Alice'), /DISCOVERY_ACCOUNT_SCOPE_INVALID/)
assert.throws(() => discoveryAccountToken('0123456789abcdef'), /DISCOVERY_ACCOUNT_SCOPE_INVALID/)
assert.equal(discoveryWorkspaceIsAccountScoped(), false)
assert.equal(discoveryWorkspaceStorageKey(), LEGACY_BOOTSTRAP_KEY)
assert.equal(discoveryWorkspaceDbKey(), 'current')

storage.setItem(LEGACY_BOOTSTRAP_KEY, '{"legacy":true}')
await activateDiscoveryWorkspaceForAccount(SCOPE_A)
const storageKeyA = discoveryWorkspaceStorageKey()
const dbKeyA = discoveryWorkspaceDbKey()
assert.equal(discoveryWorkspaceIsAccountScoped(), true)
assert(storageKeyA.includes(tokenA))
assert(dbKeyA.includes(tokenA))
assert.equal(storage.getItem(LEGACY_BOOTSTRAP_KEY), null)
assert.equal(storage.getItem(UNOWNED_BOOTSTRAP_KEY), '{"legacy":true}')

storage.setItem(storageKeyA, '{"owner":"A"}')
await activateDiscoveryWorkspaceForAccount(SCOPE_B)
const storageKeyB = discoveryWorkspaceStorageKey()
const dbKeyB = discoveryWorkspaceDbKey()
assert.notEqual(storageKeyA, storageKeyB)
assert.notEqual(dbKeyA, dbKeyB)
assert.equal(storage.getItem(storageKeyA), '{"owner":"A"}')
assert.equal(storage.getItem(storageKeyB), null)

storage.setItem(storageKeyB, '{"owner":"B"}')
await activateDiscoveryWorkspaceForAccount(SCOPE_A)
assert.equal(discoveryWorkspaceStorageKey(), storageKeyA)
assert.equal(discoveryWorkspaceDbKey(), dbKeyA)
assert.equal(storage.getItem(storageKeyA), '{"owner":"A"}')
assert.equal(storage.getItem(storageKeyB), '{"owner":"B"}')

await clearActiveDiscoveryWorkspaceAccount()
assert.equal(discoveryWorkspaceIsAccountScoped(), false)
assert.equal(storage.getItem(storageKeyA), null)
assert.equal(storage.getItem(storageKeyB), '{"owner":"B"}')

delete globalThis.window

const scriptDir = dirname(fileURLToPath(import.meta.url))
const guard = readFileSync(resolve(scriptDir, '../src/components/auth/RequirePilotSession.tsx'), 'utf8')
assert(guard.includes('await activateDiscoveryWorkspaceForAccount(user.local_scope)'))
assert(guard.indexOf('await activateDiscoveryWorkspaceForAccount(user.local_scope)') < guard.indexOf("setState('authorized')"))

const accountApi = readFileSync(resolve(scriptDir, '../src/services/accountApi.ts'), 'utf8')
assert(accountApi.includes('await clearActiveDiscoveryWorkspaceAccount()'))

const radarStore = readFileSync(resolve(scriptDir, '../src/services/discoveryRadarStore.ts'), 'utf8')
assert(radarStore.includes('const storageKey = discoveryWorkspaceStorageKey()'))
assert(radarStore.includes('const dbKey = discoveryWorkspaceDbKey()'))
assert(radarStore.includes('discoveryWorkspaceIsAccountScoped()'))
assert(radarStore.includes('writeIndexedWorkspace(workspace, dbKey)'))
assert(radarStore.includes('writeBootstrap(workspace, false, storageKey)'))
assert(radarStore.includes("An older account's"))
assert(!radarStore.includes("const DB_KEY = 'current'"))

console.log('Radar account isolation checks: PASS')
