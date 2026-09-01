import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const read = (path) => readFileSync(resolve(root, path), 'utf8')

const layout = read('src/components/layout/AppLayout.tsx')
assert.match(layout, /fixed inset-x-0 bottom-0/)
assert.match(layout, /sm:hidden/)
assert.match(layout, /hidden shrink-0 items-center gap-1 sm:flex/)
assert.match(layout, /lg:inline-flex/)
assert.match(layout, /sm:block/)

const stages = read('src/components/shared/StageBadge.tsx')
assert.match(stages, /BIDDING: '招标中'/)
assert.match(stages, /return '项目进行中'/)
assert.doesNotMatch(stages, />\s*\{stage\}\s*</)

const decision = read('src/components/today/DecisionBlock.tsx')
assert.match(decision, /useSyncExternalStore/)
assert.match(decision, /subscribeAiRequestBusy/)
assert.match(decision, /已有AI任务处理中/)

const aiApi = read('src/services/aiDecisionApi.ts')
assert.match(aiApi, /AI_CLIENT_BUSY/)
assert.match(aiApi, /beginAiRequest/)
assert.match(aiApi, /finally \{\s*endAiRequest\(\)/s)

const metrics = read('src/components/today/MetricCards.tsx')
assert.doesNotMatch(metrics, /AI任务队列/)
assert.match(metrics, /重点已分析/)

const today = read('src/pages/TodayPage.tsx')
assert.doesNotMatch(today, /天津公开商机试用/)
assert.match(today, /数据范围：天津公开采购/)
assert.match(today, /天津公开采购/)

const card = read('src/components/today/ActionCard.tsx')
assert.doesNotMatch(card, /TOP \{card\.rank\}/)
assert.match(card, /重点 \{card\.rank\}/)
assert.match(card, /hasUserCustomerContext/)
assert.match(card, /publicOnly=\{publicOnlyPriority\}/)

const staticService = read('src/services/StaticSnapshotTodayActionsService.ts')
assert.match(staticService, /const INTERVENTION_MAX_POINTS = 25/)
assert.match(staticService, /const LATE_WINDOW_POINTS = 8/)
assert.doesNotMatch(staticService, /LATE_WINDOW_PERCENT = 38/)
assert.doesNotMatch(staticService, /\* 40\)\)/)
assert.match(staticService, /return '各位老师好：'/)
assert.match(staticService, /return `\$\{names\[0\]\}老师，您好：`/)
assert.match(staticService, /关注到「\$\{project\}」的公开/)
assert.doesNotMatch(staticService, /关注到\$\{buyer\}公开发布了/)
for (const code of [
  'EXECUTION_FLEXIBILITY',
  'DEADLINE_URGENCY',
  'PRODUCT_SPECIFICITY',
  'PUBLICATION_FRESHNESS',
]) {
  assert.match(staticService, new RegExp(`componentPercent\\(card, '${code}'\\)`))
}

const apiService = read('src/services/ApiTodayActionsService.ts')
assert.match(apiService, /generated_at: data\.snapshot_as_of/)
assert.match(apiService, /refreshed_at: data\.snapshot_as_of/)
for (const code of [
  'EXECUTION_FLEXIBILITY',
  'DEADLINE_URGENCY',
  'PRODUCT_SPECIFICITY',
  'PUBLICATION_FRESHNESS',
]) {
  assert.match(apiService, new RegExp(`componentPercent\\(card, '${code}'\\)`))
}

const outreach = read('src/components/followup/OutreachDrawer.tsx')
assert.match(outreach, /if \(names\.length >= 2\) return '各位老师好：'/)
assert.match(outreach, /return `\$\{names\[0\]\}老师，您好：`/)
assert.match(outreach, /formatChineseDateTimeText/)
assert.match(outreach, /normalizePublicationAttribution/)
assert.match(outreach, /normalizeFormalProcurementWording/)
assert.match(outreach, /公开答疑或公告允许的资料对接窗口/)

const priorityBadge = read('src/components/shared/PriorityBadge.tsx')
assert.match(priorityBadge, /公开信号强/)
assert.match(priorityBadge, /\/ 60 公开分/)

const priorityCard = read('src/components/opportunity/PriorityCard.tsx')
assert.match(priorityCard, /\{value\}%/)
assert.match(priorityCard, /分项为各维度得分占比/)

console.log('Mobile-first UI checks: PASS')
