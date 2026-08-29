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
- **16 份正式 JSON Schema/合同**
- **32 组 deterministic unittest 模块**
- 2 套 Agnes benchmark，共 **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 核心链路

`Source Registry → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → Institution Evidence → Product Taxonomy → Matching Profile Gate → Opportunity Match → Query Budget → Priority Score → Daily Recommendation Plan → Grounded Model Decision → Follow-up Feedback`

## Query Budget / 参数复杂度

客户画像允许长期保存真实完整的区域、产品、客户类型与关系；限制的是**单次执行复杂度**，不是客户真实经营范围。

交互默认：DB候选500、deterministic match 200、deep enrichment 30、model candidates 10、final action cards 5、live profile-query crawl 0、单商机模型最多24条 VERIFIED facts / 12000字符事实预算。

`NORMAL <=24 cells`；`WIDE 25..120`；`VERY_WIDE >120`。范围越宽，越收紧深挖和模型Top-N，而不是拒绝客户画像。

## Daily Recommendation Plan

已实现 `daily_recommendations.py` + `medical-daily-recommendation-plan.schema.json`：

`共享 VERIFIED 候选 → deterministic Match → Priority Score → bounded model candidates → Top 5 action cards`

这层不现场爬网、不直接调用模型。未通过事实/画像 Gate 的项目不会进入模型候选。

## Follow-up / 画像学习

已实现 `medical-opportunity-followup.schema.json` + `followup_feedback.py`。

吸收乙方宝的项目笔记/阶段/提醒逻辑，但进一步要求：客户标记 `NOT_FIT` 后，可以生成画像复核建议，例如产品范围、合作厂家能力、最低项目金额、区域、租赁政策等。

**任何建议默认 `auto_apply_allowed=false`。** 只有客户明确确认后才允许真正修改画像；`COMPETITOR_LOCKED_CUSTOMER_JUDGMENT`、`PROJECT_TOO_LATE` 等项目特有判断禁止自动泛化成公司长期规则。

## Institution Evidence

当前15条 VERIFIED 官方机构 Evidence，公共 Match Pipeline 仅做精确名称/显式 alias enrichment；证据不足继续 UNKNOWN。

## Product Taxonomy / Matching

正式匹配使用稳定 `taxonomy_ids`。deterministic/human-confirmed classifier 已准入；Agnes taxonomy classifier 仍 `BENCHMARK_PENDING / can_drive_matching=false`。

## 50条 corpus / audit

50条 VERIFIED corpus 已达到第一轮分类覆盖评估门槛。`taxonomy_corpus_audit.py` 已就绪，但 GitHub Runner 尚未执行，因此当前不宣称具体 deterministic coverage rate。

## 乙方宝对标

已建立：

- `docs/research/competitors/yifangbao-2026-08.md`
- `docs/product/competitive-roadmap-v0.1.json`

吸收其持续订阅、前期商机、联系人/关系、竞争历史、跟进管理、微信小程序等已验证工作流；不复制泛行业信息流定位。

MedicalChannelAI 固定差异化：**医疗垂直 Evidence-first + 客户真实经营画像 + 医院关系资产 + 今日行动优先**。

## Agnes

Agnes 2.5 Flash 仍为 `GO_FOR_BENCHMARK`，不是 production validated。两套 benchmark 共28 case，均未执行。

## Source / Attachment

天津政府采购 PRIMARY PARTIAL；CCGP OFFICIAL_MIRROR IMPLEMENTED；天津公共资源 OFFICIAL_MIRROR PARTIAL。Coverage 保持 `PARTIAL / NOT_EXHAUSTIVE`。

DOCX/XLSX parser 已实现，但真实官方附件 bytes 捕获仍为0；PDF Docling只有代码合同，没有真实字节验证。

## CI真实状态

GitHub Actions 仍是 Job 无执行 steps 的基础设施问题；Python compile/unittest 没有开始执行。因此当前32组 tests 只能标“已写入等待真实执行证据”，不能标 PASS，也不能解释为 assertion failure。Issue #2 持续跟踪。

## 下一步

1. 把 Daily Recommendation / Follow-up 接到未来 Fact API 与 profile subscription 调度层。
2. Runner恢复后执行32组 tests 与 taxonomy corpus audit。
3. 获取首份真实天津医疗附件 bytes 并跑 Snapshot/SHA/parser。
4. 继续验证天津政府采购网2026原生列表/搜索/分页/生命周期。
5. 实现推送 latency ledger 与提醒/负责人状态。
6. deterministic execution 有证据后再跑 Agnes 两套 benchmark。
7. Fact/Profile/Match/Priority/QueryPlan/DailyAction/Followup API 稳定后再进入老杨 H5/Web。
