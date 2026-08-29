# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- 6 个运行时 P0 Source：4 IMPLEMENTED、2 PARTIAL_IMPLEMENTATION
- **50 条 VERIFIED 天津商机 regression fixture**
- 5 条真实官方附件声明；真实附件 binary capture = 0
- **15 条天津机构官方 Evidence fixture**
- **21 份正式 JSON Schema/合同**
- **37 组 deterministic unittest 模块**
- 2 套 Agnes benchmark，共 **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 核心链路

`Source Registry → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → Institution Evidence → Product Taxonomy → Matching Profile Gate → Opportunity Match → Query Budget → Priority Score → Daily Recommendation → Subscription Prefilter → Subscription Event Batch → Subscription Evaluation → Notification Route → Latency Ledger → Follow-up Feedback → Grounded Model Decision`

## Query Budget / 参数复杂度

客户画像可以长期保存真实完整的区域、产品、客户类型与关系；限制的是**单次执行复杂度**，不是客户经营范围。

交互默认：DB候选500、deterministic match 200、deep enrichment 30、model candidates 10、final action cards 5、interactive live crawl 0、单商机模型最多24条 VERIFIED facts / 12000字符事实预算。

`NORMAL <=24 cells`；`WIDE 25..120`；`VERY_WIDE >120`。范围越宽，越收紧深挖和模型 Top-N，不拒绝真实画像，也不得做 `区域 × 产品 × 数据源` 的实时笛卡尔爬取。

## Daily Recommendation

`daily_recommendations.py`：

`共享 VERIFIED 候选 → deterministic Match → Priority Score → bounded model candidates → Top 5 action cards`

未通过事实/画像 Gate 的项目不进入模型候选；首页不现场重爬全网。

## Continuous Subscription

已实现：

- `subscription_prefilter.py`
- `subscription_batch.py`
- `subscription_engine.py`
- `subscription_notification.py`
- `medical-subscription-prefilter.schema.json`
- `medical-subscription-event-batch.schema.json`
- `medical-profile-subscription-evaluation.schema.json`
- `medical-subscription-notification-route.schema.json`

原则：**订阅由客户真实画像驱动，不要求客户维护大量关键词。**

新物质性事件进入 VERIFIED 后：

1. 按 `地区 + taxonomy + customer type` 反向预筛可能相关画像；
2. 预筛只为性能，最终仍必须跑完整 Match Gate；
3. 缺关键 taxonomy/机构事实 → `ENRICHMENT_ONLY`，不通知客户；
4. 普通匹配 → `DAILY_DIGEST`；
5. fully-confirmed profile + 高优先级 → 才允许 `IMMEDIATE_HIGH_PRIORITY`；
6. 同 profile/opportunity/material-event 使用稳定 dedupe key，防重复推送；
7. 大量候选客户按固定批次处理，`batch_limit<=1000`，通过 `next_offset` 续跑，不一次展开全部画像。

预筛在区县未知时保守保留候选，防止性能优化产生 false negative。非法 event type/material event id 在预筛前就拒绝，不能被“缺事实”状态掩盖。

## Follow-up / 防骚扰路由

- `WON / LOST / NOT_FIT / ARCHIVED`：同一 opportunity 后续通知默认抑制；
- `REVIEWING / CONTACTED / RELATIONSHIP_VERIFIED / PREPARING / BID_SUBMITTED / MONITOR`：新物质变化仍可提醒；
- 已有 owner：优先路由给负责人；无 owner：团队 inbox/digest；
- 关键事实不足：只进入补证队列。

新的真正不同项目必须拥有新的 opportunity identity，不能被旧项目终态误杀。

## Latency Ledger

`latency_ledger.py` + `medical-opportunity-latency-ledger.schema.json` 记录：

`official published → discovered → fetched → verified → matched → notification queued → delivered`

可信边界：

- 官方只有 `DAY` 精度时禁止计算“发布后几分钟发现”；
- `MINUTE/SECOND` 才允许 publication-to-discovery，并保留精度；
- 运行阶段必须 timezone-aware 且单调；
- verified 必须在 fetched 后，matched 必须在 verified 后，delivery 必须有 queue；
- 发现时间早于官方报告发布时间时记录 warning，不制造负延迟。

## Institution / Taxonomy / Match

当前15条 VERIFIED 官方 Institution Evidence；只做精确名称/显式 alias enrichment，证据不足继续 UNKNOWN。

正式匹配使用稳定 `taxonomy_ids`。deterministic/human-confirmed classifier 已准入；Agnes taxonomy classifier 仍 `BENCHMARK_PENDING / can_drive_matching=false`。

## Source / Attachment

天津政府采购 PRIMARY 继续 `PARTIAL_IMPLEMENTATION`。2026 当前采购公告仍明确引用 `tjgp.cz.tj.gov.cn`；原始详情 `documentView.do?method=view&id=<digits>&ver=2` 路由有官方 2025 页面持续佐证，但 **2026 原生列表/搜索/分页、直接 primary detail fetch、附件 href 仍未验证**。

CCGP OFFICIAL_MIRROR IMPLEMENTED；天津公共资源 OFFICIAL_MIRROR PARTIAL。Coverage 保持 `PARTIAL / NOT_EXHAUSTIVE`。

DOCX/XLSX parser 已实现，但真实官方附件 bytes 捕获仍为0；PDF Docling只有代码合同，没有真实字节验证。

## Corpus / Agnes

50条 VERIFIED corpus 已达到第一轮分类覆盖评估门槛。`taxonomy_corpus_audit.py` 已就绪，但 Runner 尚未执行，因此不宣称具体 deterministic coverage rate。

Agnes 2.5 Flash 仍为 `GO_FOR_BENCHMARK`，不是 production validated。两套 benchmark 共28 case，均未执行。

## CI真实状态

最近确认的 Medical Pilot CI 仍为 GitHub Runner 基础设施问题：`runner_id=0 / runner_name="" / steps=[]`，Python compile/unittest 未开始执行。因此当前37组 tests 只能标“已写入等待真实执行证据”，不能标 PASS，也不能解释为 assertion failure。Issue #2 持续跟踪。

## 下一步

1. 将 Daily/Subscription/Latency 合同接入未来 Fact API 与后台事件调度/持久化层。
2. 继续攻克天津政府采购 PRIMARY 原生列表/搜索/分页与附件 href，拿到第一份真实 DOCX/PDF bytes。
3. Runner恢复后执行37组 tests 与 taxonomy corpus audit，优先修真实失败。
4. 根据 audit unresolved 扩 deterministic taxonomy，再决定 Agnes 实际承担比例。
5. deterministic execution 有证据后再跑 Agnes 两套 benchmark。
6. 后端核心 API 稳定后再进入 H5/微信小程序端。
