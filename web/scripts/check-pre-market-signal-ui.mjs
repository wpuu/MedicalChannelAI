import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(process.cwd())
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const notice = read('src/components/shared/PreMarketSignalNotice.tsx')
assert.match(notice, /recommendationMode === 'PRE_MARKET_SIGNAL'/)
assert.match(notice, /PROCUREMENT_INTENT/)
assert.match(notice, /EXPECTED_PROCUREMENT_MONTH_WINDOW_TEXT=/)
assert.match(notice, /官方预计采购时间/)
assert.match(notice, /提前布局信号，不是正式招标窗口/)
assert.match(notice, /不能按“已经可以报名或投标”处理/)

const pool = read('src/pages/OpportunityPoolPage.tsx')
assert.match(pool, /type WindowFilter = 'ALL' \| 'OPEN' \| 'PRE_MARKET_SIGNAL' \| 'LATE_WINDOW'/)
assert.match(pool, /const preMarket = isPreMarketSignal\(card\.facts\.lifecycle_stage, card\.recommendation_mode\)/)
assert.match(pool, /windowFilter === 'OPEN' && \(card\.recommendation_mode === 'LATE_WINDOW' \|\| preMarket\)/)
assert.match(pool, /windowFilter === 'PRE_MARKET_SIGNAL' && !preMarket/)
assert.match(pool, /\['PRE_MARKET_SIGNAL', '提前布局'\]/)
assert.match(pool, /尚未进入正式报名\/投标窗口的采购意向/)

const actionCard = read('src/components/today/ActionCard.tsx')
assert.match(actionCard, /<PreMarketSignalNotice/)
assert.match(actionCard, /recommendationMode=\{card\.recommendation_mode\}/)
assert.match(actionCard, /qualityFlags=\{card\.facts\.quality_flags\}/)

const factsCard = read('src/components/opportunity/FactsCard.tsx')
assert.match(factsCard, /expectedProcurementWindowText\(facts\.quality_flags\)/)
assert.match(factsCard, /qualityFlags=\{facts\.quality_flags\}/)
assert.match(factsCard, /formatDate\(facts\.expected_purchase_date\) \?\? expectedProcurementWindow/)

const publicTypes = read('src/types/public.ts')
assert.match(publicTypes, /quality_flags\?: string\[\]/)

const apiAdapter = read('src/services/ApiTodayActionsService.ts')
assert.match(apiAdapter, /quality_flags: card\.facts\.quality_flags \?\? \[\]/)

const staticAdapter = read('src/services/StaticSnapshotTodayActionsService.ts')
assert.match(staticAdapter, /quality_flags: card\.facts\.quality_flags \?\? \[\]/)

const stageBadge = read('src/components/shared/StageBadge.tsx')
assert.match(stageBadge, /PROCUREMENT_INTENT: '采购意向 · 提前布局'/)

console.log('Pre-market signal UI contract: PASS')
