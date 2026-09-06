import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const apiConfig = readFileSync(resolve(scriptDir, '../src/services/apiConfig.ts'), 'utf8')
const guard = readFileSync(resolve(scriptDir, '../src/components/auth/RequirePilotSession.tsx'), 'utf8')
const accountApi = readFileSync(resolve(scriptDir, '../src/services/accountApi.ts'), 'utf8')

assert(apiConfig.includes("export const PILOT_SESSION_CHANGE_KEY = 'medicalchannelai.pilot.session-change.v1'"))
assert(apiConfig.includes('export function signalPilotSessionChanged(): void'))
assert.equal((apiConfig.match(/signalPilotSessionChanged\(\)/g) ?? []).length >= 4, true)
assert(apiConfig.includes('const user = parsePilotUser(root?.user)'))
assert(apiConfig.includes('const parsed = parsePilotUser'))
assert(apiConfig.includes('if (!response.ok) throw await authError(response)\n  signalPilotSessionChanged()'))

assert(guard.includes('PILOT_SESSION_CHANGE_KEY'))
assert(guard.includes("window.addEventListener('storage', handleStorage)"))
assert(guard.includes('if (event.key !== PILOT_SESSION_CHANGE_KEY) return'))
assert(guard.includes('window.location.reload()'))
assert(guard.indexOf('await activateDiscoveryWorkspaceForAccount(user.local_scope)') < guard.indexOf("setState('authorized')"))

assert(accountApi.includes("import { apiBaseUrl, signalPilotSessionChanged } from './apiConfig'"))
assert(accountApi.includes('await clearActiveDiscoveryWorkspaceAccount()'))
assert(accountApi.indexOf('await clearActiveDiscoveryWorkspaceAccount()') < accountApi.lastIndexOf('signalPilotSessionChanged()'))

console.log('Pilot cross-tab session isolation checks: PASS')
