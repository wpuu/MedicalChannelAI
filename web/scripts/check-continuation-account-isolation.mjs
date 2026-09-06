import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const ledger = readFileSync(resolve(scriptDir, '../src/services/discoveryContinuationLedger.ts'), 'utf8')
const accountApi = readFileSync(resolve(scriptDir, '../src/services/accountApi.ts'), 'utf8')

assert(ledger.includes("import {\n  discoveryWorkspaceDbKey,\n  discoveryWorkspaceIsAccountScoped,"))
assert(ledger.includes('function continuationRecordKey(sourceId: string): string'))
assert(ledger.includes("? `${discoveryWorkspaceDbKey()}::${sourceId}`"))
assert(ledger.includes(': sourceId'))
assert(ledger.includes('const recordKey = continuationRecordKey(source.id)'))
assert(ledger.includes('const recordKey = continuationRecordKey(ledger.source_id)'))
assert(ledger.indexOf('const recordKey = continuationRecordKey(ledger.source_id)') < ledger.indexOf('await writeLedger(next, recordKey)'))
assert(ledger.includes('export async function clearActiveContinuationLedgersForAccount()'))
assert(ledger.includes('cursor.key.startsWith(prefix)'))
assert(!ledger.includes('.put(ledger, ledger.source_id)'))
assert(!ledger.includes('.get(sourceId)'))

assert(accountApi.includes("import { clearActiveContinuationLedgersForAccount } from './discoveryContinuationLedger'"))
assert(accountApi.includes('await clearActiveContinuationLedgersForAccount()'))
assert(accountApi.indexOf('await clearActiveContinuationLedgersForAccount()') < accountApi.indexOf('await clearActiveDiscoveryWorkspaceAccount()'))

console.log('Continuation account isolation checks: PASS')
