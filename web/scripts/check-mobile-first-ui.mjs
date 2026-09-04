import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(process.cwd())
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const app = read('src/App.tsx')
assert.match(app, /path="\/radar"/)
assert.match(app, /path="\/today"/)
assert.match(app, /path="\/targets"/)
assert.match(app, /path="\/followed"/)
assert.match(app, /path="\/resources"/)

const layout = read('src/components/layout/AppLayout.tsx')
assert.match(layout, /雷达/)
assert.match(layout, /今日/)
assert.match(layout, /目标/)
assert.match(layout, /跟进/)
assert.match(layout, /资源/)
assert.doesNotMatch(layout, /grid-cols-6/)

const login = read('src/pages/LoginPage.tsx')
assert.match(login, /邀请码/)
assert.match(login, /注册/)
assert.match(login, /登录/)

const requireSession = read('src/components/auth/RequirePilotSession.tsx')
assert.match(requireSession, /AUTH_REQUIRED/)
assert.doesNotMatch(requireSession, /localStorage/)

const radar = read('src/pages/DiscoveryRadarPage.tsx')
assert.match(radar, /累计发现/)
assert.match(radar, /扫描/)
assert.match(radar, /官方/)
assert.match(radar, /深分页/)

const continuation = read('src/components/discovery/DiscoveryContinuationDashboard.tsx')
assert.match(continuation, /安全续扫下一段/)
assert.match(continuation, /累计发现/)
assert.match(continuation, /续扫链/)

const today = read('src/pages/TodayPage.tsx')
assert.match(today, /今日/)
assert.match(today, /DueRemindersPanel/)
assert.match(today, /acknowledgeDueReminder/)

const reminders = read('src/components/today/DueRemindersPanel.tsx')
assert.match(reminders, /我的跟进/)
assert.match(reminders, /onAcknowledge\(item\.reminder_id\)/)

const actionCard = read('src/components/today/ActionCard.tsx')
assert.match(actionCard, /主要匹配维度（完成度）/)
assert.match(actionCard, /不是直接加分/)
assert.match(actionCard, /公告公开联系人/)
assert.match(actionCard, /PRODUCT_EXECUTION_CAPABILITY/)
assert.match(actionCard, /PreMarketSignalNotice/)
assert.match(actionCard, /recommendationMode=\{card\.recommendation_mode\}/)

const preMarketSignal = read('src/components/shared/PreMarketSignalNotice.tsx')
assert.match(preMarketSignal, /PRE_MARKET_SIGNAL/)
assert.match(preMarketSignal, /PROCUREMENT_INTENT/)
assert.match(preMarketSignal, /提前布局信号，不是正式招标窗口/)
assert.match(preMarketSignal, /不能按“已经可以报名或投标”处理/)

const stageBadge = read('src/components/shared/StageBadge.tsx')
assert.match(stageBadge, /PROCUREMENT_INTENT: '采购意向 · 提前布局'/)
assert.match(stageBadge, /border-amber-200/)

const opportunityPool = read('src/pages/OpportunityPoolPage.tsx')
assert.match(opportunityPool, /'PRE_MARKET_SIGNAL', '提前布局'/)
assert.match(opportunityPool, /windowFilter === 'OPEN' && \(card\.recommendation_mode === 'LATE_WINDOW' \|\| preMarket\)/)
assert.match(opportunityPool, /windowFilter === 'PRE_MARKET_SIGNAL' && !preMarket/)
assert.match(opportunityPool, /全部已核验机会与早期信号/)
assert.match(opportunityPool, /PreMarketSignalNotice/)

const factsCard = read('src/components/opportunity/FactsCard.tsx')
assert.match(factsCard, /PreMarketSignalNotice lifecycleStage=\{facts\.lifecycle_stage\}/)

const resourceBlock = read('src/components/today/CustomerResourceBlock.tsx')
assert.match(resourceBlock, /补充我的资源/)
assert.match(resourceBlock, /只填写已确认事实/)
assert.match(resourceBlock, /医院关系（如有）/)
assert.match(resourceBlock, /产品\/服务能力/)

const followed = read('src/pages/FollowedPage.tsx')
assert.match(followed, /我的跟进/)
assert.match(followed, /getFollowedOpportunityPage/)
assert.match(followed, /getFollowedOpportunityById/)
assert.match(followed, /加载更早跟进/)

const targetRoute = read('src/pages/TargetHospitalsPage.tsx')
assert.match(targetRoute, /目标医院经营视图/)
assert.match(targetRoute, /目标医院本身不会增加医院关系分/)
assert.match(targetRoute, /目标医院名称不会自动推导官网地址/)
assert.match(targetRoute, /to="\/resources"/)
assert.match(targetRoute, /to="\/radar"/)
assert.match(targetRoute, /grid grid-cols-2 gap-2 sm:grid-cols-4/)

const targets = targetRoute
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
assert.match(pilotResources, /saveCustomerProfile\((?:profile|nextProfile)\)/)
assert.match(pilotResources, /账号私有数据库/)

const card = read('src/components/today/ActionCard.tsx')
assert.doesNotMatch(card, /TOP \{card\.rank\}/)
assert.match(card, /重点 \{card\.rank\}/)

console.log('Mobile-first UI checks: PASS')
