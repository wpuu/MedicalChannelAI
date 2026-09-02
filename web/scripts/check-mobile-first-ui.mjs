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
for (const [path, label] of [
  ['/radar', '雷达'],
  ['/today', '今日'],
  ['/targets', '目标'],
  ['/followed', '跟进'],
  ['/resources', '资源'],
]) {
  assert.match(layout, new RegExp(`to="${path.replace('/', '\\/')}"`))
  assert.match(layout, new RegExp(`<span>${label}<\\/span>`))
}
assert.match(layout, /showTargets = isApiMode \|\| isVerifiedPublicDemo/)
assert.match(layout, /showResources = isApiMode \|\| isVerifiedPublicDemo/)

const app = read('src/App.tsx')
assert.match(app, /<Route element=\{<RequirePilotSession \/>\}>/)
assert.match(app, /path="\/radar"/)
assert.match(app, /path="\/today"/)
assert.match(app, /path="\/targets"/)
assert.match(app, /path="\/followed"/)
assert.match(app, /path="\/resources"/)

const sessionGuard = read('src/components/auth/RequirePilotSession.tsx')
assert.match(sessionGuard, /isAuthRequiredError/)
assert.match(sessionGuard, /<Navigate to="\/login" replace \/>/)
assert.match(sessionGuard, /系统不会降级为匿名模式/)
assert.match(
  sessionGuard,
  /setState\(isAuthRequiredError\(error\)[\s\S]*\? 'unauthorized'[\s\S]*: 'error'\)/,
)

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
assert.match(today, /<DueRemindersPanel/)
assert.match(today, /navigate\(`\/followed\?focus=\$\{encodeURIComponent\(opportunityId\)\}`\)/)
assert.match(today, /acknowledgeDueReminder/)

const reminders = read('src/components/today/DueRemindersPanel.tsx')
assert.match(reminders, /到期跟进提醒/)
assert.match(reminders, /站内提醒/)
assert.match(reminders, /onOpenFollowed\(item\.opportunity_id\)/)
assert.match(reminders, /当前不在今日 Top5 · 已保留在我的跟进/)
assert.match(reminders, /flex flex-wrap justify-end gap-2/)

const followed = read('src/pages/FollowedPage.tsx')
assert.match(followed, /useSearchParams/)
assert.match(followed, /const focusedId = searchParams\.get\('focus'\)/)
assert.match(followed, /return \[focused, \.\.\.items\.filter/)
assert.match(followed, /来自到期提醒/)
assert.match(followed, /item\.remind_at/)

const targets = read('src/pages/TargetHospitalsPage.tsx')
assert.match(targets, /目标医院经营视图/)
assert.match(targets, /目标医院本身不会增加医院关系分/)
assert.match(targets, /目标医院名称不会自动推导官网地址/)
assert.match(targets, /to="\/resources"/)
assert.match(targets, /to="\/radar"/)
assert.match(targets, /grid grid-cols-2 gap-2 sm:grid-cols-4/)

const pilotResources = read('src/pages/PilotResourcesPage.tsx')
assert.match(pilotResources, /目标医院 \/ 重点关注/)
assert.match(pilotResources, /医院关系/)
assert.match(pilotResources, /产品 \/ 服务能力/)
assert.match(pilotResources, /目标医院不会自动算成“有关系”/)
assert.match(pilotResources, /saveCustomerProfile\(profile\)/)
assert.match(pilotResources, /账号私有数据库/)

const card = read('src/components/today/ActionCard.tsx')
assert.doesNotMatch(card, /TOP \{card\.rank\}/)
assert.match(card, /重点 \{card\.rank\}/)
assert.match(card, /scoreScope=\{card\.priority\.score_scope\}/)
assert.doesNotMatch(card, /hasUserCustomerContext/)
assert.doesNotMatch(card, /score\s*<=\s*60/)

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
assert.match(outreach, /recipientSelection === GROUP_RECIPIENT\) return '各位老师好：'/)
assert.match(outreach, /availableRecipients\.length >= 2\) return '您好：'/)
assert.match(outreach, /return personGreeting\(availableRecipients\[0\]\)/)
assert.match(outreach, /\(老师\|先生\|女士\)\$/)
assert.match(outreach, /公告列出多位联系人，不代表本次需要群发；默认不指定收件人/)
assert.match(outreach, /formatChineseDateTimeText/)
assert.match(outreach, /normalizePublicationAttribution/)
assert.match(outreach, /normalizeFormalProcurementWording/)
assert.match(outreach, /公开答疑或公告允许的资料对接窗口/)

const priorityBadge = read('src/components/shared/PriorityBadge.tsx')
assert.match(priorityBadge, /scoreScope\?: PriorityScoreScope/)
assert.match(priorityBadge, /scoreScope !== 'PERSONALIZED'/)
assert.match(priorityBadge, /公开信号强/)
assert.match(priorityBadge, /\/ 60 公开分/)
assert.match(priorityBadge, /\/ 100 个性化分/)
assert.doesNotMatch(priorityBadge, /score\s*<=\s*60/)

const priorityCard = read('src/components/opportunity/PriorityCard.tsx')
assert.match(priorityCard, /priority\.score_scope !== 'PERSONALIZED'/)
assert.match(priorityCard, /\{value\}%/)
assert.match(priorityCard, /分项为各维度得分占比/)
assert.doesNotMatch(priorityCard, /priority\.score\s*<=\s*60/)

console.log('Mobile-first UI checks: PASS')
