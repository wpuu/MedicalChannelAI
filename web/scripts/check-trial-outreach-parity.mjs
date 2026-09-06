import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { outreachBudgetFactText } from '../src/utils/outreachBudgetFact.js'

assert.equal(outreachBudgetFactText(4588), '项目预算约4588元')
assert.equal(outreachBudgetFactText(15000), '项目预算约1.5万元')
assert.equal(outreachBudgetFactText(5730000), '项目预算约573万元')
assert.equal(outreachBudgetFactText(0), null)
assert.equal(outreachBudgetFactText(null), null)

const scriptDir = dirname(fileURLToPath(import.meta.url))
const runtimeTrial = readFileSync(resolve(scriptDir, '../src/services/RuntimeTrialTodayActionsService.ts'), 'utf8')
assert(runtimeTrial.includes('outreachBudgetFactText(card?.facts.budget)'))
assert(runtimeTrial.includes('draft.draft.replace(/项目预算约\\d+(?:\\.\\d+)?万元/, budgetFact)'))
assert(runtimeTrial.includes('normalizeTrialOutreachBudget(draft, card)'))

const server = readFileSync(resolve(scriptDir, '../api/ai/analyze.js'), 'utf8')
assert(server.includes('if (budget < 10_000) return `项目预算约${Math.round(budget)}元`'))
assert(server.includes('const decimals = wan < 10 ? 2 : wan < 100 ? 1 : 0'))

console.log('Trial outreach budget parity: PASS')
