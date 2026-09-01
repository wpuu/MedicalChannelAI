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

console.log('Mobile-first UI checks: PASS')
