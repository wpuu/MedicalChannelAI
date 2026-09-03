import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import {
  activateDiscoveryWorkspaceForAccount,
  clearActiveDiscoveryWorkspaceAccount,
  discoveryAccountToken,
} from '../src/services/discoveryWorkspaceAccountIsolation.js'

class MemoryStorage {
  constructor() { this.values = new Map() }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null }
  setItem(key, value) { this.values.set(String(key), String(value)) }
  removeItem(key) { this.values.delete(String(key)) }
}

const OWNER_KEY = 'medicalchannelai.discovery.workspace.owner.v1'
const BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.bootstrap.v4'
const ACCOUNT_BOOTSTRAP_PREFIX = 'medicalchannelai.discovery.workspace.account.v1.'
const UNOWNED_BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.unowned.v1.bootstrap'

const storage = new MemoryStorage()
globalThis.window = { localStorage: storage }

const tokenA = discoveryAccountToken('Alice')
const tokenB = discoveryAccountToken('Bob')
assert.notEqual(tokenA, tokenB)
assert.equal(tokenA, discoveryAccountToken(' alice '))
assert(!tokenA.includes('alice'))

storage.setItem(BOOTSTRAP_KEY, '{"legacy":true}')
await activateDiscoveryWorkspaceForAccount('Alice')
assert.equal(storage.getItem(OWNER_KEY), tokenA)
assert.equal(storage.getItem(BOOTSTRAP_KEY), null)
assert.equal(storage.getItem(UNOWNED_BOOTSTRAP_KEY), '{"legacy":true}')

storage.setItem(BOOTSTRAP_KEY, '{"owner":"A"}')
await activateDiscoveryWorkspaceForAccount('Bob')
assert.equal(storage.getItem(`${ACCOUNT_BOOTSTRAP_PREFIX}${tokenA}`), '{"owner":"A"}')
assert.equal(storage.getItem(BOOTSTRAP_KEY), null)
assert.equal(storage.getItem(OWNER_KEY), tokenB)

storage.setItem(BOOTSTRAP_KEY, '{"owner":"B"}')
await activateDiscoveryWorkspaceForAccount('Alice')
assert.equal(storage.getItem(`${ACCOUNT_BOOTSTRAP_PREFIX}${tokenB}`), '{"owner":"B"}')
assert.equal(storage.getItem(BOOTSTRAP_KEY), '{"owner":"A"}')
assert.equal(storage.getItem(OWNER_KEY), tokenA)

await clearActiveDiscoveryWorkspaceAccount()
assert.equal(storage.getItem(BOOTSTRAP_KEY), null)
assert.equal(storage.getItem(OWNER_KEY), null)
assert.equal(storage.getItem(`${ACCOUNT_BOOTSTRAP_PREFIX}${tokenA}`), null)
assert.equal(storage.getItem(`${ACCOUNT_BOOTSTRAP_PREFIX}${tokenB}`), '{"owner":"B"}')

delete globalThis.window

const scriptDir = dirname(fileURLToPath(import.meta.url))
const guard = readFileSync(resolve(scriptDir, '../src/components/auth/RequirePilotSession.tsx'), 'utf8')
assert(guard.includes('await activateDiscoveryWorkspaceForAccount(user.username)'))
assert(guard.indexOf('await activateDiscoveryWorkspaceForAccount(user.username)') < guard.indexOf("setState('authorized')"))

const accountApi = readFileSync(resolve(scriptDir, '../src/services/accountApi.ts'), 'utf8')
assert(accountApi.includes('await clearActiveDiscoveryWorkspaceAccount()'))

const radarStore = readFileSync(resolve(scriptDir, '../src/services/discoveryRadarStore.ts'), 'utf8')
assert(radarStore.includes("const DB_KEY = 'current'"))
assert(radarStore.includes("const STORAGE_KEY = 'medicalchannelai.discovery.workspace.bootstrap.v4'"))

console.log('Radar account isolation checks: PASS')
