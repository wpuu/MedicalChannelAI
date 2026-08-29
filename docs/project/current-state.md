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
- **15 份正式 JSON Schema/合同**
- **31 组 deterministic unittest 模块**
- 2 套 Agnes benchmark，共 **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 核心链路

`Source Registry → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → Institution Evidence → Product Taxonomy → Matching Profile Gate → Opportunity Match → Query Budget → Priority Score → Daily Recommendation Plan → Grounded Model Decision`

## 参数复杂度 / Query Budget

客户画像允许长期保存真实完整的区域、产品、客户类型与关系，不为了性能强迫用户缩小真实经营范围。

单次交互执行必须受预算约束：

- 公共数据采集：`SHARED_FACT_INDEX_NOT_PER_PROFILE_CRAWL`
- DB候选：500
- 确定性匹配：200
- 深度补证：30
- 模型候选：10
- 首页行动卡：5
- 交互式画像查询实时全网抓取：0
- 单商机模型 VERIFIED facts：默认最多24条
- 单商机模型事实字符预算：12000

范围宽度仅决定执行策略：

- `NORMAL`: scope cells <= 24
- `WIDE`: 25..120 → summary-then-drill-down，模型Top-N收紧到8
- `VERY_WIDE`: >120 → 深度补证收紧到15，模型Top-N收紧到5

这些阈值是 v0.1 **单次执行预算，不是客户画像硬上限**。不得把“区域数 × 产品数 × 数据源数”展开成用户点击一次就触发的实时笛卡尔爬取。

单项目深挖允许极少量受控实时请求（当前上限3）；计划采集按 Source 驱动。

## Daily Recommendation Plan

已新增 `daily_recommendations.py` 与 `medical-daily-recommendation-plan.schema.json`。

公共首页逻辑现在可以在**不重新爬网、不调用模型**的情况下执行：

`共享 VERIFIED 候选 → deterministic Match → Priority Score → bounded model candidates → Top 5 action cards`

未通过事实/画像 Gate 的项目不会进入模型候选。宽画像只会收紧模型/深挖 Top-N，不会拒绝真实客户画像。

这层是未来“今天最值得处理5件事”的确定性后端骨架。

## 模型上下文预算

Grounded Model Decision 显式记录：

- 原始可用 VERIFIED fact 数
- 实际纳入数
- 预算排除数
- 纳入字符数
- 最大 fact / 字符预算

事实选择只做确定性优先排序，不修改事实内容。**官方事实不允许截断后强塞进模型。** 如果已有 VERIFIED facts 全部无法完整放入预算，则模型调用 fail-closed。

## Institution Evidence

当前15条 VERIFIED 官方机构 Evidence，已覆盖总医院、第一中心、胸科、中医一附院、市疾控、第三中心、第五中心、南开医院、中研附院、肿瘤医院、血液病医院、天津医院，以及天津大学、天津医科大学、天津科技大学。

公共 Match Pipeline 只做精确名称/显式 alias enrichment；证据不足继续 UNKNOWN。

## Product Taxonomy / Matching

正式匹配使用稳定 `taxonomy_ids`。deterministic/human-confirmed classifier 已准入；Agnes taxonomy classifier 仍 `BENCHMARK_PENDING / can_drive_matching=false`。

Match Pipeline 要求 VERIFIED facts、证据化机构类型和受控 taxonomy。缺关键事实返回 `NEEDS_MORE_FACTS`，模型不能提前解释为好商机。

## 50条 corpus / audit

50条 VERIFIED corpus 已达到第一轮分类覆盖评估门槛。`taxonomy_corpus_audit.py` 已就绪，但 GitHub Runner 尚未执行，因此当前不宣称具体 deterministic coverage rate。

## 乙方宝对标

已建立：

- `docs/research/competitors/yifangbao-2026-08.md`
- `docs/product/competitive-roadmap-v0.1.json`

吸收其持续订阅、前期商机、关系/联系人、竞争历史、跟进管理和微信小程序等已经验证的产品工作流；不复制其泛行业信息流定位。

MedicalChannelAI 的差异化固定为：**医疗垂直 Evidence-first + 客户真实经营画像 + 医院关系资产 + 行动优先，而不是单纯“标讯更多”。**

## Agnes

Agnes 2.5 Flash 当前仍为 `GO_FOR_BENCHMARK`，不是 production validated。两套 benchmark 共28 case，均未执行；专项 taxonomy benchmark 通过并显式升级 classifier registry 前，Agnes 分类不能驱动正式匹配。

## Source / Attachment

天津政府采购 PRIMARY PARTIAL；CCGP OFFICIAL_MIRROR IMPLEMENTED；天津公共资源 OFFICIAL_MIRROR PARTIAL。Coverage 必须保持 `PARTIAL / NOT_EXHAUSTIVE`。

DOCX/XLSX parser 已实现，但真实官方附件 bytes 捕获仍为0；PDF Docling只有代码合同，没有真实字节验证。

## CI真实状态

最近已确认的 Medical Pilot CI 仍是 Job 无执行 steps 的基础设施问题；Python compile/unittest 没有开始执行。因此当前31组 tests 只能标“已写入等待真实执行证据”，不能标 PASS，也不能解释为 assertion failure。Issue #2 持续跟踪。

## 下一步

1. 将 Daily Recommendation / Query Budget 接到未来 Fact API / profile subscription 调度层。
2. Runner恢复后执行31组 tests 与 taxonomy corpus audit。
3. 获取首份真实天津医疗附件 bytes 并跑 Snapshot/SHA/parser。
4. 继续验证天津政府采购网2026原生列表/搜索/分页/生命周期。
5. 实现跟进状态 + 用户反馈回写客户画像。
6. deterministic execution 有证据后再跑 Agnes 两套 benchmark。
7. Fact/Profile/Match/Priority/QueryPlan/DailyAction API 稳定后再进入老杨 H5/Web。
