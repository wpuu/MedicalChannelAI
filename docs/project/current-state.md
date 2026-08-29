# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- 6 个运行时 P0 Source：4 IMPLEMENTED、2 PARTIAL_IMPLEMENTATION
- **50 条 VERIFIED 天津商机 regression fixture**
- 5 条真实官方附件声明；真实附件 binary capture = 0
- **15 条天津机构官方 Evidence fixture**
- **14 份正式 JSON Schema/合同**
- **30 组 deterministic unittest 模块**
- 2 套 Agnes benchmark，共 **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 核心可信链

`Source Registry → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → Institution Evidence → Product Taxonomy → Matching Profile Gate → Opportunity Match → Query Budget → Priority Score → Grounded Model Decision`

模型不得创造采购事实；客户条件不足必须继续追问；派生分类必须经过来源/准入验证；Coverage 不完整时不能宣称“已查全”。

## Query Budget / 参数复杂度

客户画像可以长期保存真实完整的区域、产品、客户类型和关系范围，**不为了性能强迫客户把真实业务范围填窄**。

单次交互执行则必须受预算约束：

- `acquisition_strategy = SHARED_FACT_INDEX_NOT_PER_PROFILE_CRAWL`
- DB候选最多500
- 确定性匹配最多200
- 深度补证默认最多30
- 进入模型默认最多10
- 首页最终行动卡默认5
- 交互式画像查询实时全网抓取 = 0
- 单商机模型事实默认最多24条 / 12000字符级事实输入

范围复杂度只用于决定执行方式：

- `NORMAL`: scope cells <= 24
- `WIDE`: 25..120 → summary-then-drill-down，模型Top-N收紧到8
- `VERY_WIDE`: >120 → 深度补证收紧到15，模型Top-N收紧到5

**这些是单次执行预算，不是客户画像永久上限。** 数据采集按 Source Registry 集中运行，不能把“区域数 × 产品数 × 数据源数”变成客户点击一次就触发的实时笛卡尔爬取。

单项目深挖可允许极少量受控实时请求（当前上限3）用于缺失官方详情/附件；计划采集则按数据源驱动。

## 模型上下文预算

Grounded Model Decision 现在显式记录：原始可用 VERIFIED fact 数、实际纳入数、预算排除数、纳入字符数和最大预算。

事实选择只做确定性优先排序，不修改事实内容。**官方事实不允许为了塞进上下文而被截断。** 如果现有 VERIFIED facts 全部超出单条上下文预算，模型调用直接 fail-closed。

因此未来可以避免两种问题：

1. 把几百条候选/几十页附件一次塞进模型，造成速度下降和注意力稀释；
2. 实际只给模型部分事实，却让日志/前端误以为模型已经读过全部证据。

## Institution Evidence

当前15条 VERIFIED 官方机构 Evidence，已覆盖总医院、第一中心、胸科、中医一附院、市疾控、第三中心、第五中心、南开医院、中研附院、肿瘤医院、血液病医院、天津医院，以及天津大学、天津医科大学、天津科技大学。

公共 Match Pipeline 仅做精确名称/显式 alias enrichment；没有足够官方证据的机构保持 UNKNOWN。

## Product Taxonomy / Agnes

正式匹配使用稳定 `taxonomy_ids`，不使用自由中文字符串。deterministic/human-confirmed classifier 已准入；Agnes taxonomy classifier 仍 `BENCHMARK_PENDING / can_drive_matching=false`。

Agnes 当前仍是 `GO_FOR_BENCHMARK`，不是 production validated。两套 benchmark 共28 case，均未执行。

## 50条 corpus / taxonomy audit

50条 corpus 已达到第一轮分类覆盖评估门槛。`taxonomy_corpus_audit.py` 已能统计确定性规则覆盖和 unresolved 清单，但 GitHub Runner 尚未执行，所以当前不宣称具体 coverage rate。

## Source / Attachment

天津政府采购 PRIMARY PARTIAL；CCGP OFFICIAL_MIRROR IMPLEMENTED；天津公共资源 OFFICIAL_MIRROR PARTIAL。Coverage 必须继续 `PARTIAL / NOT_EXHAUSTIVE`。

DOCX/XLSX parser 已实现，但真实官方附件 bytes 捕获仍为0；PDF Docling只有代码合同，没有真实字节验证。

## CI真实状态

最近已确认的 Medical Pilot CI 仍是 Job 无执行 steps 的基础设施问题；Python compile/unittest 没有开始执行。因此当前30组 deterministic tests 只能标“测试代码已写入，等待真实执行证据”，不能标 PASS，也不能解释为 assertion failure。Issue #2 持续跟踪。

## 下一步

1. 将 Query Budget 接到未来 Fact API / daily recommendations 调度层，禁止调用方绕过预算。
2. Runner恢复后执行30组 tests 与 taxonomy corpus audit。
3. 获取首份真实天津医疗附件 bytes 并跑 Snapshot/SHA/parser。
4. 继续验证天津政府采购网2026原生列表/搜索/分页/生命周期。
5. deterministic execution 有证据后再跑 Agnes 两套 benchmark。
6. Fact/Profile/Match/Priority/QueryPlan API 稳定后再进入老杨 H5/Web。
