import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const service = readFileSync(resolve(scriptDir, '../src/services/ApiTodayActionsService.ts'), 'utf8')
const contract = readFileSync(resolve(scriptDir, '../src/services/TodayActionsService.ts'), 'utf8')
const poolPage = readFileSync(resolve(scriptDir, '../src/pages/OpportunityPoolPage.tsx'), 'utf8')
const targetPage = readFileSync(resolve(scriptDir, '../src/pages/TargetHospitalsPage.tsx'), 'utf8')
const metrics = readFileSync(resolve(scriptDir, '../src/components/today/MetricCards.tsx'), 'utf8')
const privateApi = readFileSync(resolve(scriptDir, '../api/private.js'), 'utf8')

assert(contract.includes('export interface TodayActionsLoadOptions'))
assert(contract.includes('hydrateFollowups?: boolean'))
assert(contract.includes('getTodayActions(options?: TodayActionsLoadOptions)'))

assert(!service.includes("'/followed?view=status-index'"))
assert(!service.includes('getFollowupStatusIndex'))
assert(service.includes('normalizeFollowupStatus(card.followup_status)'))

const todayStart = service.indexOf('async getTodayActions(')
const opportunityStart = service.indexOf('async getOpportunity(', todayStart)
assert(todayStart >= 0 && opportunityStart > todayStart)
const todaySource = service.slice(todayStart, opportunityStart)
assert(todaySource.includes("this.requestJson<TodayActionsPublicResponse>('/today')"))
assert(!todaySource.includes('Promise.all('))
assert(!todaySource.includes('this.enrichWithServerFollowup('))

const opportunitySource = service.slice(opportunityStart)
assert(opportunitySource.includes('this.enrichWithServerFollowup(mapPublicCard(card))'))

assert(poolPage.includes('todayActionsService.getTodayActions({ hydrateFollowups: false })'))
assert(!poolPage.includes('getFollowedStatusIndex'))
assert(targetPage.includes('.getTodayActions({ hydrateFollowups: false })'))
assert(!targetPage.includes('getFollowedStatusIndex'))

assert(privateApi.includes('recommendation_feedback_summary'))
assert(privateApi.includes('decorateCardWithFollowup'))
assert(metrics.includes('serverSummary={data.recommendation_feedback_summary}'))
assert(!metrics.includes('loadRecommendationFeedback'))
assert(!metrics.includes('subscribeRemoteRecommendationFeedback'))

console.log('API request budget checks: PASS')
