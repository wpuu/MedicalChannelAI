# MedicalChannelAI｜行动雷达 V0 真实差距审计

- 日期：2026-10-07
- 状态：P0_GAP_AUDIT
- 前置文档：
  - docs/strategy/ACTION_RADAR_V0_VALIDATION_2026-10-07.md
  - docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md
- 本轮边界：只读核验 + 文档，不修改 Collector/AI/Production，不部署。

## 结论

行动雷达 V0 不需要从零开发。现有 MedicalChannelAI 已有：
- verified canonical facts；
- 官方证据 URL；
- 天津/区域采集器；
- procurement intent / market research / bidding 等生命周期；
- 客户私有产品能力/医院关系；
- Agnes 3.0 Flash action selector；
- Today / Opportunity Pool / Followup；
- verified snapshot 发布机制。

但进入 7 天真实付费试验前有 3 个 P0/P1：

1. P0 数据新鲜度没有达到试验要求。
2. P1 AI 目前是“动作选择器”，没有独立 PASS/不推送相关性门。
3. P1 新发现项目与已跟进项目没有在 late-window 展示策略上彻底分离。

因此下一步不是继续做前端，也不是扩全国源，而是把这三项做到可验收。

## 1. 真实数据基线

2026-10-07 读取 main 当前已保存天津 live records：

- 总记录：75
- CCGP：56
- 天津一中心：2
- 天津医科大学总医院：3
- 天津中医药大学第二附属医院 market research：4
- 天津中医药大学第二附属医院 procurement intent：4
- 泰达医院：6
- 中心妇产：0
- tjnothop：0

按 2026-10-07 15:19 +08:00 做简单终止判断：
- 49 条已过 registration/bid 最终时间；
- 26 条尚未按当前简单逻辑最终关闭。

但这 26 条里，多数正式招标的“获取招标文件/报名时间”已在 9 月中下旬结束，只是 10 月上旬开标时间未到。
对第一次看到项目的新客户，这类项目通常不应继续占据“今天必须行动”；对已经跟进的客户，它们仍应该保留在 Followup / 投标执行阶段。

因此：
- discovery feed 和 followup feed 必须有不同 late-window 语义；
- 不能仅依据 bid deadline 尚未到，就继续把项目当成新商机推给陌生客户。

## 2. P0：天津自动数据已经落后于官方公开页面

当前仓库内天津各 sync report：
- tianjin_sync_report: observed_at = 2026-09-27T05:22:04Z
- tjmugh/tjnothop/tjzxfc/tjzyefy/tjzyefy_intent/teda/tjfch 等报告也全部停在同一时点 2026-09-27。
- regional_sync_report 更新到 2026-10-02，但它不能证明天津医院早期信号源持续工作。

与此同时，2026-10-07 实时公开网页可验证到仓库当前天津数据没有覆盖的新事件：

### 天津中医药大学第二附属医院
2026-09-28：
院内调研公告（2026年23号）-肢体康复训练等医疗设备采购项目。
报名：2026-09-28 至 2026-10-09 16:00。
包括肢体康复训练、熏蒸、生物反馈、多关节主被动训练、骨创伤、红外、经颅磁、吞咽神经肌肉电刺激等。

官方：
https://www.tjzyefy.com/system/2026/09/28/030199113.shtml

### 天津中医药大学第二附属医院
2026-09-30：
数据安全服务项目调研公告。
方案报送截止：2026-10-11 17:00。

官方：
https://www.tjzyefy.com/system/2026/09/30/030199248.shtml

后者是很好的 hard negative：
医院官方 + 当前仍开放，不代表医疗器械渠道客户需要收到。

因此：

**在恢复天津源真实刷新之前，不能对外宣称“每日行动雷达”，也不能用当前 snapshot 做 7 天客户试验。**

### 2.1 2026-10-07 线上只读诊断：不是 Collector 全停，而是 Runtime Source Parity 缺失

后续读取生产公开只读端点：

- `https://medicalchannelai.vercel.app/api/collector-status`
- `https://medicalchannelai.vercel.app/api/public-snapshot`

得到更精确的根因，因此修正“自动刷新整体失效”的过度概括：

1. Vercel incremental collector 在 2026-10-07 当天仍正常运行。
2. collector status 在约 15:30（Asia/Shanghai）仍显示 15 分钟 tick 链，状态为 `NO_SOURCE_DUE`，且 `tjmugh`、`tjnothop`、`tjfch`、`tjfch_test`、`teda` 均有当日 runtime ledger/scan 状态。
3. 但生产 incremental source 列表**从代码层就没有**：
   - `tjzyefy`（天津中医药大学第二附属医院调研）；
   - `tjzyefy_intent`（同院采购意向）；
   - `tjzxfc`（天津市中心妇产科医院早期信号）。
4. 对应代码证据：
   - `web/collector_incremental.py::SOURCE_POLICIES` 没有以上三源；
   - `web/collector_incremental_runtime.py::SUPPORTED_INCREMENTAL_SOURCES` 没有以上三源；
   - `web/collector_incremental_scheduler.py::SCHEDULED_INCREMENTAL_SOURCES` 没有以上三源；
   - `web/collector_runtime.py` 的 RuntimeCache canonical keys / deep STAGE_ORDER / publish merge 同样没有以上三源。
5. GitHub self-hosted deep workflow 虽然支持 `tjzyefy/tjzyefy_intent/tjzxfc`，但其持久化报告停在 2026-09-27。因此这三个源没有 Vercel 增量链兜底，造成 9/28、9/30 官方新公告真实漏失。
6. 现有解析器并非缺失：
   - `tjzyefy_discovery.py` / `tjzyefy_market_research.py`；
   - `tjzyefy_intent_discovery.py` / `tjzyefy_procurement_intent.py`；
   - `tjzxfc_discovery.py` / `tjzxfc_market_research.py`
   已存在，并包含官方域名、标题/日期、医疗范围、截止时间和非医疗 unsupported 等验证逻辑。

所以 P0 根因现在明确为：

> **Runtime source parity 缺失：已有可靠 deep adapters 没有进入 Vercel-native incremental execution plane。**

这比“定时任务坏了”更准确，也决定了最小修复范围：**复用已有 adapter 接入 RuntimeCache + incremental scheduler + publish merge；禁止重写爬虫。**

### 2.2 当前 public snapshot 不是空，而是“太宽”

同一只读检查中，公开 snapshot 返回：

- `input_candidate_count = 903`
- `opportunity_pool_count = 437`
- `model_request_count = 0`

这说明当前系统的另一个问题不是“没有项目”，而是：

> **广域 verified pool 已经足够大；用户价值取决于从 437 条压缩成与其产品真正相关的极少行动项。**

因此 P0 修复源覆盖之后，下一阶段优先级仍然是 relevance suppression，而不是继续扩更多省份/更多通用公告。

## 3. 第五中心医院 9/24 线索仍只能作为 discovery clue

第三方聚合当前公开：
天津市第五中心医院医疗设备购置论证及分散采购报名公告。
发布时间 2026-09-24，截止 2026-10-07 17:30；
包含病理、耳鼻喉、骨科、普外、康复、ICU、泌尿等多类设备，包括：
- 全自动包埋盒打号机；
- 切片（载玻片）打号机；
- 全自动冰冻免疫组化染色机；
- 电动骨动力系统；
- 微波消融系统；
- 钬激光治疗机；
- 无创血流动力学监测仪等。

本轮仍未取得该院官方原始页面，因此：
- 可以用于 source discovery；
- 不得以 VERIFIED 官方事实推给客户；
- 不得因为“今天截止”而放松 Evidence First。

这恰好证明行动雷达需要两层：
第三方发现可能漏掉的机会 → 官方源核验成功后才进入用户提醒。

## 4. P1：现有 Agnes 不能说 PASS

当前 web/api/ai/_decisionContract.js 的模型角色是：
“医疗渠道行动优先级选择器”。

模型只能从服务端提供的 allowed action codes 中选择 1–3 个动作。

当前合约：
- 不允许模型生成事实，安全边界正确；
- 但 action_codes 至少 1 个；
- 没有 NOT_RELEVANT / PASS；
- 所以只要一条项目进入 AI decision 阶段，它就必须选一个“去核实/去准备/去联系”等动作。

这与行动雷达的核心产品价值冲突：

**行动雷达最重要的能力不是给每条项目写建议，而是让与客户无关的信息完全不出现。**

因此不应该直接扩展现有 action selector 去“顺便判断相关性”。
应增加独立 relevance gate，先 PASS，再 action。

## 5. 推荐的安全两级 AI 合约

### Gate 1：Relevance Gate

输入：
- 已核验公开 facts；
- 客户明确填写的 product profile；
- 服务端生成的 profile item IDs；
- 当前 lifecycle/time state。

Agnes 只允许返回枚举，例如：

- DIRECT_MATCH
- POSSIBLE_MATCH_NEEDS_CONFIRMATION
- NOT_MATCH

以及：
- matched_profile_item_ids: 只能从输入 ID 中选；
- question_codes: 只能从服务端给出的确认问题枚举中选。

不得输出：
- 新产品名；
- 新资质；
- 新日期；
- 新预算；
- 胜率；
- 自由文本事实。

服务端策略：
- NOT_MATCH → PASS，不进入行动建议；
- POSSIBLE → WATCH / 提一个确认问题；
- DIRECT_MATCH → 进入 Gate 2。

### Gate 2：Action Selector

继续复用当前安全的 action-code 选择器。
只对已经通过 Gate 1 的项目调用。

这样：
- 事实仍由确定性服务端掌控；
- Agnes 用于语义匹配；
- AI 不会因为“必须回答”而强行给垃圾项目一个动作；
- 可以显著减少模型调用量。

## 6. 关键词基线为什么不够

对当前 75 条记录做一个故意简单的 broad-keyword baseline：

- 病理 Persona A：0 条命中；
- 手术/消毒 Persona B：7 条命中；
- 检验/试剂 Persona C：9 条命中。

这个 baseline 不是当前产品算法，只用于说明单纯宽关键词的边界。

明显误匹配例子：
- 天津市海河医院战略型复合人才培养项目，因为“培养”会误命中检验 Persona；
- 天津市第三中心医院胃肠动力学检查系统采购项目，宽泛“动力”规则会错误拉入手术动力设备。

另一方面，Persona A 在当前数据完全 0 命中，但 9/24 第五中心第三方线索里恰好出现很强的病理设备项目。
这同时说明：
- 只做关键词会产生误报；
- 源覆盖不足会产生漏报；
- Agnes 不能弥补“源根本没抓到”的问题。

## 7. P1：late-window 必须按用户状态分流

当前 pool 逻辑允许：
registration/file-acquisition 结束，但 bid deadline 未到 → LATE_WINDOW。

这对已参与项目的用户有意义。

但对于首次看到项目的新用户：
- 招标文件获取已结束；
- 可能已经没有正常进入路径；
- “开标还没到”不等于“现在还是新商机”。

V0 建议：

### New Discovery
- registration/file-acquisition 已关闭：
  - 默认不进入“今天必须处理”；
  - 如有明确官方 late-entry 路径才例外；
  - 可进入 COMPETITOR_WATCH / LATE_DISCOVERY，但不占主行动位。

### Existing Followup
- 用户在窗口关闭前已经 FOLLOWED/CONTACTED/PREPARED：
  - 一直保留到 bid/award/terminal；
  - 继续提醒提交、澄清、开标、结果等。

这比用一个统一 late-window 分数更符合销售现实。

## 8. P0/P1 执行顺序

### P0-1｜补齐 Vercel incremental runtime source parity
只接入已有 verified adapters，不重写 parser。

最小范围：
- tjzyefy market research；
- tjzyefy procurement intent；
- tjzxfc early-signal market research。

验收：
- 三源进入 SOURCE_POLICIES / SUPPORTED_INCREMENTAL_SOURCES / SCHEDULED_INCREMENTAL_SOURCES；
- 三源有独立 RuntimeCache canonical state 与 bootstrap；
- incremental scan 可以复用既有 discovery/detail parser；
- 9/28 tjzyefy 康复设备调研能被真实 incremental scan 发现并验证；
- 9/30 数据安全调研不得进入 public medical opportunity；保持既有 adapter 的 fail-closed 语义，允许在 discovery scope gate 直接过滤，或在 detail scope gate 作为 unsupported/non-fact 拒绝；
- publish merge 包含新增三源的 verified canonical records；
- snapshot durable readback 一致；
- 不依赖 self-hosted runner；
- 不靠人工写入数据；
- 不修改 Production，先在隔离分支和测试中验收。

### P0-2｜检查 source freshness health
每个 source 必须有：
- last_success_at
- last_attempt_at
- latest_seen_published_at
- failure_reason
- stale_after
- status = HEALTHY / STALE / FAILING

如果 source 已 STALE：
- 用户界面不能继续显示“实时/今日”却不提示；
- AI 不得掩盖采集层失效。

### P1-1｜增加 Relevance Gate 合约
先只写合同和测试，不碰 UI。
用已有 15 gold cases × 3 personas = 45 判断验收。

### P1-2｜New Discovery / Followup late-window 分流
先写业务合同和测试。

### P1-3｜再决定是否补第五中心官方 source
必须先找到稳定官方 index/detail contract。
第三方只做 discovery clue，不能直接升格。

## 9. 工程授权建议

这次和“先开发 SaaS”不同。
P0 是修复现有 MedicalChannelAI 已承诺的数据新鲜度，属于验证基础设施修复，不是新增产品。

因此可以把 P0-1/P0-2 交给 Codex 做“只修复、只测试、禁止 Production 变更”的隔离任务。

P1 relevance gate 先不要写生产代码。
先把 gold set 用真实 Agnes 跑通，再决定是否实现。

## 10. 当前状态

- V0 产品定义：完成。
- Gold set：完成。
- 自动新鲜数据：PARTIAL FAIL。Vercel incremental 对已接入源当天仍运行；tjzyefy/tjzyefy_intent/tjzxfc 因 runtime source parity 缺失而无法获得同等新鲜度，故整体仍未满足试验条件。
- Agnes relevance benchmark：未执行，不能声称 PASS。
- 真实客户付费验证：未开始。
- Production：不改。
- 独立仓库：不建。
- 下一步：先完成 P0 runtime source parity 隔离修复与测试；再跑 Agnes 45-case relevance benchmark。
