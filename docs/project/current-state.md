# MedicalChannelAI 当前状态

日期：2026-08-28  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 1. 当前目标

天津 Pilot 验证：公开医疗商业信号能否持续、可追溯地进入事实层，并在**模型不得创造采购事实、客户条件不足必须继续追问、派生分类必须有准入证据**的前提下，形成渠道/厂家销售可执行的优先级与行动建议。

当前聚焦医疗器械、IVD、耗材；不是诊断或临床决策系统。

## 2. 当前真实规模

- 6 个运行时 P0 Source：4 IMPLEMENTED、2 PARTIAL_IMPLEMENTATION
- **50 条 VERIFIED 天津商机 regression fixture**：8 + 1 + 2 + 10 + 16 + 13
- 5 条真实官方附件声明；真实附件 binary capture = 0
- 5 条天津机构官方 Evidence fixture
- **13 份正式 JSON Schema/合同**
- **29 组 deterministic unittest 模块**
- 2 套 Agnes benchmark：12 + 16 = **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

50条 corpus 已达到第一轮分类覆盖/模型评估所需的样本规模门槛，但不等于覆盖天津全部商机。

## 3. 事实底座

已实现 Evidence-first SourceRegistry / Opportunity / ProcurementEvent / EvidenceFact、Snapshot SHA-256、官方来源角色、DAY/MINUTE 时间精度、CCGP 生命周期、采购意向 `projId`、医院官网早期信号、天津政府采购原始详情 PARTIAL、公共资源结果镜像 PARTIAL、中标产品/品牌/型号/数量/单价，以及 bounded DOCX/XLSX parser。

PDF Docling backend 代码存在，但真实官方 PDF bytes 尚未验证，生产开关仍关闭。

## 4. Canonical Identity / Cross-stage

身份优先级：官方 `project_number` → source native id → source+URL。禁止 `buyer_name + project_name` 自动合并。

Cross-stage 当前只有 `CANDIDATE_REQUIRES_EVIDENCE`，`auto_merge_allowed=false`；真正 canonical bridge/merge 尚未实现。

## 5. Customer / Matching Profile Gate

正式商机匹配使用 `matching_profile_gate.py`。客户产品能力必须映射到受控 `taxonomy_ids`；人类可读 category/subcategory 仅用于开户访谈和 UI。缺失/非法 taxonomy 会降为 `INCOMPLETE / PROFILE_INTERVIEW_REQUIRED` 并返回下一句问题。

## 6. Opportunity Match Pipeline

公开入口：`tools/medical_pilot/match_pipeline.py`。

顺序：Matching Profile Gate → VERIFIED/Coverage → 排除规则 → 区域 → Institution/customer type 证据 → 项目阶段 → 金额 → taxonomy → 租赁能力。

缺关键事实返回 `NEEDS_MORE_FACTS / FACT_ENRICHMENT_REQUIRED / model_explanation_allowed=false`。

## 7. Institution Evidence

当前5条官方机构 Evidence 覆盖总医院、第一中心医院、胸科医院、中医一附院、天津市疾控。机构等级/类型不能从名称猜。

## 8. Product Taxonomy / Classifier Admission

已建立稳定 taxonomy、确定性分类器、客户 taxonomy 验证和分类器全局准入注册表。

- deterministic classifier：VALIDATED，可驱动匹配
- human-confirmed classifier：VALIDATED，可驱动匹配
- Agnes taxonomy classifier：`BENCHMARK_PENDING / can_drive_matching=false`

单条 Agnes 结果不能自报 VALIDATED 绕过全局准入。

## 9. Grounded Model Decision / Priority

模型只能选择预设 action/reason/risk code，并引用已有 VERIFIED fact_id / 已确认 profile path；v0.1 不允许模型创造采购事实。

Priority Score = 产品能力30 + 客户确认关系25 + 阶段25 + 金额20，固定 `BUSINESS_PRIORITY_NOT_WIN_PROBABILITY`。

## 10. 50条 corpus 可信边界

新增覆盖包括流式/血培养、MRI/CT/DR、内窥镜与内窥镜AI、急救生命支持、消毒灭菌、显微成像、眼科耗材、设备维保和官方装机品牌/购置时间。

- 多子项市场调研页面按一个 source-record Opportunity 计数，不拆子项虚增数量。
- 同项目不同生命周期事件不重复计数。
- 官方结果索引能证明已成交、但正文当前不可抓取时，只锁项目身份和 `AWARDED`；金额/供应商保持未知，不从早期公告补值。
- 每条 fixture 都有 `forbidden_inference`。

## 11. Deterministic Taxonomy Corpus Audit

已新增：

- `tools/medical_pilot/taxonomy_corpus_audit.py`
- `tools/medical_pilot/test_taxonomy_corpus_audit.py`

Audit 会把50条 fixture 中的项目名称、官方 scope、官方中标产品名和官方装机设备名转换成模拟 VERIFIED Fact，调用与生产一致的确定性 taxonomy classifier，并输出：

- `deterministically_classified_count`
- `unresolved_count`
- `deterministic_coverage_rate`
- 每条 case 的 taxonomy IDs 和 supporting fact IDs

重要：`deterministic_coverage_rate` 只是**本地规则覆盖率，不是准确率，也不是 Agnes 准确率**。

由于 GitHub Runner 仍未执行测试，本轮**不宣称具体覆盖率**。泛标题如“天津市肿瘤医院设备采购项目”必须继续 unresolved，不允许为了提高覆盖率猜产品类别。

## 12. Agnes benchmark

当前仍是 `GO_FOR_BENCHMARK`，不是 production validated。

两套 benchmark：12 case 粗分类/风险 + 16 case 正式 taxonomy/安全放弃分类。均默认 dry-run；只有 `--execute` + 环境变量 `AGNES_API_KEY` 才联网。

## 13. Source Topology / Coverage

天津政府采购 PRIMARY PARTIAL；CCGP OFFICIAL_MIRROR IMPLEMENTED；天津公共资源 OFFICIAL_MIRROR PARTIAL。医院官网早期信号由总医院和第一中心医院作为 PRIMARY。

Coverage 必须继续 `PARTIAL / NOT_EXHAUSTIVE`，不能宣称“天津已查全”。

## 14. Attachment / PDF

DOCX/XLSX parser 已实现，真实官方附件 bytes 捕获仍为0。PDF Docling仅有代码合同，没有真实字节验证，因此不能宣称附件解析生产可用。

## 15. CI真实状态

最新确认：Medical Pilot CI Run `33177116131` / Job `98868503191` 为 failure，且 Job 没有任何执行 steps。Python compile/unittest 没有开始执行。

因此当前 **29组 deterministic tests 只能标“测试代码已写入，等待真实执行证据”**，不能标 PASS，也不能解释为 assertion failure。Issue #2 继续跟踪 Runner/Actions 基础设施。

## 16. 下一步

1. Runner恢复后先执行29组 deterministic tests，并生成真实 taxonomy corpus audit 覆盖率。
2. 根据 audit unresolved 清单扩充 deterministic taxonomy，剩余模糊项再进入 Agnes/人工分类。
3. 获取第一份真实天津医疗 DOCX/XLSX/PDF bytes，验证 MIME/redirect/SHA/parser locator。
4. 验证天津政府采购网2026原生列表/搜索、分页和完整生命周期栏目。
5. 扩充 Institution Evidence。
6. deterministic execution 有证据后，运行 Agnes 两套 benchmark。
7. Fact/Profile/Match/Priority API 稳定后，再进入老杨 H5/Web 演示端。
