import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const auth = readFileSync(resolve(scriptDir, '../api/auth.js'), 'utf8')
const apiConfig = readFileSync(resolve(scriptDir, '../src/services/apiConfig.ts'), 'utf8')
const guard = readFileSync(resolve(scriptDir, '../src/components/auth/RequirePilotSession.tsx'), 'utf8')
const isolation = readFileSync(resolve(scriptDir, '../src/services/discoveryWorkspaceAccountIsolation.js'), 'utf8')

assert(auth.includes("import {\n  authenticatedUser,"))
assert(auth.includes('sha256,'))
assert(auth.includes('function localScope(userId)'))
assert(auth.includes('sha256(`pilot-local-scope:v1:${userId}`).slice(0, 32)'))
assert.equal((auth.match(/local_scope: localScope\(user\.id\)/g) ?? []).length, 3)

const exportStart = auth.indexOf('async function exportAccount')
const deleteStart = auth.indexOf('async function deleteAccount')
assert(exportStart >= 0 && deleteStart > exportStart)
assert(!auth.slice(exportStart, deleteStart).includes('local_scope'))
assert(!auth.includes('user: { id:'))

assert(apiConfig.includes('local_scope: string'))
assert(apiConfig.includes("typeof row.local_scope !== 'string'"))
assert(apiConfig.includes('!/^[0-9a-f]{32}$/.test(row.local_scope)'))
assert(apiConfig.includes('local_scope: row.local_scope'))
assert(guard.includes('activateDiscoveryWorkspaceForAccount(user.local_scope)'))

assert(isolation.includes('export function discoveryAccountToken(accountScope)'))
assert(isolation.includes("if (!/^[0-9a-f]{32}$/.test(normalized)) throw new Error('DISCOVERY_ACCOUNT_SCOPE_INVALID')"))
assert(!isolation.includes('function hash32('))
assert(!isolation.includes("discoveryAccountToken(username)"))

console.log('Immutable account local-scope checks: PASS')
