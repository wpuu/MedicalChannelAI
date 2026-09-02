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
assert.match(today, /onAcknowledge=/)

const reminders = read('src/components/today/DueRemindersPanel.tsx')
assert.match(reminders, /我的跟进/)
assert.match(reminders, /onAcknowledge\(item\.reminder_id\)/)

const followed = read('src/pages/FollowedPage.tsx')
assert.match(followed, /我的跟进/)
assert.match(followed, /getFollowedOpportunityPage/)
assert.match(followed, /getFollowedStatusIndex/)
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
