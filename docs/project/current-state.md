# MedicalChannelAI 当前状态

日期：2026-08-28  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 1. 当前目标

天津 Pilot 只证明一件事：公开医疗商业信号能否持续、可追溯地进入事实层，并在**模型不得创造采购事实、客户条件不足必须继续追问、派生分类必须有准入证据**的前提下，形成渠道/厂家销售可执行的优先级与行动建议。

当前聚焦医疗器械、IVD、耗材；不是诊断或临床决策系统。

## 2. 当前真实规模

- 6 个运行时 P0 Source：4 个 IMPLEMENTED、2 个 PARTIAL_IMPLEMENTATION
- **21 条 VERIFIED 天津商机 regression fixture**
- 5 条真实官方附件声明；真实附件 binary capture 仍为 0
- 5 条天津机构官方 Evidence fixture
- **13 份正式 JSON Schema/合同**
- **28 组 deterministic unittest 模块**
- 2 套 Agnes benchmark：12 + 16 = **28 个 case**
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 3. 事实底座

已实现：

- Evidence-first SourceRegistry / Opportunity / ProcurementEvent / EvidenceFact
- Snapshot SHA-256、官方来源角色、DAY/MINUTE 时间精度
- CCGP TENDER / AMENDMENT / TERMINATION / AWARD 生命周期
- Procurement Intent 月精度与官方 `projId`
- 天津医科大学总医院、天津第一中心医院早期市场信号
- 天津政府采购原始详情页（PARTIAL）
- 天津公共资源采购结果官方镜像（PARTIAL）
- 中标供应商/金额及官方产品、品牌、型号、数量、单价
- DOCX/XLSX bounded parser
- 可选 Docling PDF backend；真实 PDF bytes 尚未验证，生产开关仍关闭

## 4. Canonical Identity / Cross-stage

身份优先级：

1. 官方 `project_number` → 可跨官方来源确定性去重。
2. 官方 native record id（如采购意向 `projId`）→ `source_id + native_record_id`。
3. 无项目编号/native id → `source_id + source_url` source-local identity。

**禁止 `buyer_name + project_name` 自动合并。**

真实回归：天津医科大学两条同单位、同名“PCR仪等设备采购项目”预算分别300万元和70万元，官方 `projId` 不同，必须保持两个 Opportunity。

Cross-stage 当前只有候选层：

- `CANDIDATE_REQUIRES_EVIDENCE`
- `auto_merge_allowed=false`
- timezone-aware chronology
- 不同显式项目编号阻止候选
- canonical bridge/merge 尚未实现

## 5. Customer / Matching Profile Gate

基础经营访谈由 `customer_profile_gate.py` 负责；正式商机匹配使用 `matching_profile_gate.py`。

除了经营区域、客户类型、合作方式、租赁能力、金额门槛、项目阶段和排除项外，**每条可执行产品能力还必须映射到受控 taxonomy ID**。

因此不会出现：

`profile_completeness=100`，但产品只有“检验/医疗器械”这种模糊文字，却仍被视为可匹配。

Taxonomy 缺失或非法时统一降级：

- `INCOMPLETE`
- `PROFILE_INTERVIEW_REQUIRED`
- `candidate_opportunity_allowed=false`

并返回下一句应询问客户的问题。

人类可读 `category/subcategory` 继续保留用于开户访谈和 UI；**正式规则只认 `taxonomy_ids`**。

## 6. Opportunity Match Pipeline

公开入口：`tools/medical_pilot/match_pipeline.py`

顺序：

1. Matching Profile Gate
2. VERIFIED / Coverage Gate
3. 明确排除规则
4. 区域/区县
5. Institution/customer type 可信来源
6. 项目阶段
7. 金额门槛
8. 受控产品 taxonomy
9. 租赁能力

缺关键事实时：

- `NEEDS_MORE_FACTS`
- `FACT_ENRICHMENT_REQUIRED`
- `model_explanation_allowed=false`

机构类型不能从名称猜；产品分类也不能从自由文本直接进入规则层。

## 7. Institution Evidence

已建立 `medical-institution-evidence.schema.json`、`institution_enrichment.py` 和首批天津官方机构 Evidence。

当前覆盖示例：

- 天津医科大学总医院
- 天津市第一中心医院
- 天津市胸科医院
- 天津中医药大学第一附属医院
- 天津市疾病预防控制中心

只有官方机构/政府证据或人工确认，才允许把 `UNKNOWN` 升级为 `TERTIARY_HOSPITAL / CDC ...`。

## 8. Product Taxonomy / Classifier Admission

已建立 `product_taxonomy.v0.1.json`，正式匹配键使用稳定 taxonomy ID，而不是“化学发光/免疫发光”等自由中文字符串。

确定性分类器只读取：

- `OFFICIAL_PUBLIC_FACT`
- `VERIFIED`
- `model_generated=false`

分类结果必须回指 supporting `fact_id`。

分类器准入注册表：`product_classifier_registry.v0.1.json`。

当前：

- deterministic classifier → VALIDATED / 可驱动匹配
- human-confirmed classifier → VALIDATED / 可驱动匹配
- Agnes 2.5 Flash taxonomy classifier → `BENCHMARK_PENDING / can_drive_matching=false`

因此单条 Agnes 结果即使自报 `VALIDATED`，也不能绕过全局准入。

## 9. Grounded Model Decision Contract

只有 Match Pipeline 得到 `MATCHED_CANDIDATE` 或 `MATCHED_PERSONALIZED` 后，模型才进入该层。

模型只能选择预设：

- action code
- reason code
- risk code
- 已存在 `fact_id`
- 已允许 customer profile path

未知 fact、非法动作、非法 reason/risk code 均拒绝。v0.1 不让模型自由生成新的采购事实；中文说明先由确定性模板渲染。

## 10. Transparent Priority Score

满分100：

- 产品执行能力 30
- 客户确认医院关系 25
- 介入阶段 25
- 项目金额 20

正式匹配和 Score 均已迁到 taxonomy ID。

固定：`BUSINESS_PRIORITY_NOT_WIN_PROBABILITY`。

85分只能表示经营优先级，不是85%中标概率；没有客户确认医院关系就记0分。

## 11. Agnes benchmark

当前仍是 `GO_FOR_BENCHMARK`，**不是 production validated**。

两套 benchmark：

1. `agnes-2.5-flash-v0.1.json`：12 case，粗分类/缺信息判断/风险枚举。
2. `agnes-2.5-flash-product-taxonomy-v0.1.json`：16 case，直接测试正式 taxonomy IDs，并包含必须主动放弃分类的安全样本。

两套 harness 默认 dry-run；只有显式 `--execute` 且环境变量存在 `AGNES_API_KEY` 才联网，仓库不保存 Key。

Agnes taxonomy classifier 在专项 benchmark 通过前，全局注册表保持 `BENCHMARK_PENDING`。

## 12. Source Topology / Coverage

政府采购：

1. `tj_government_procurement` — PRIMARY_SOURCE — PARTIAL
2. `ccgp_local_notices` — OFFICIAL_MIRROR — IMPLEMENTED
3. `tj_public_resource_exchange` — OFFICIAL_MIRROR — PARTIAL

采购意向当前由 `ccgp_procurement_intent` 提供；医院早期信号由总医院和第一中心医院官网作为 PRIMARY。

当前必须保持：

- `coverage_status=PARTIAL`
- `exhaustiveness_claim=NOT_EXHAUSTIVE`

不能宣称“天津已查全”。

## 13. Attachment / PDF

DOCX/XLSX 已有 bounded deterministic parser，并保留 paragraph / sheet+cell Evidence locator。

PDF 可选 `pdf-docling-v0.1`；只有带 page_no+bbox provenance 的 block 才能支持 Evidence。真实官方 PDF/DOCX/XLSX bytes 尚未抓到并验证，因此生产层仍不能宣称附件解析已验证。

## 14. CI真实状态

最新 Medical Pilot CI Run：`33176009681`，Job：`98864682367`。

Job 仍为 failure，且 `steps=[]`；Python compile/unittest 没有开始执行。因此当前 **28组 deterministic tests 只能标“测试代码已写入，等待真实执行证据”**，不能宣称 PASS，也不能解释成 assertion failure。

Issue #2 继续跟踪 Actions/Runner 基础设施。

## 15. 下一步

1. 把21条 VERIFIED corpus 扩到 >=50，并保持采购意向/市场调研/正式招标/更正/终止/中标多样性。
2. 获取第一份真实天津医疗 DOCX/XLSX/PDF bytes，实际验证 MIME/redirect/SHA/parser locator。
3. 验证天津政府采购网2026原生列表/搜索、分页和完整生命周期栏目。
4. 扩充 Institution Evidence，减少 `customer_type=UNKNOWN`。
5. 扩充 deterministic taxonomy 高特异词，尽量减少不必要 Agnes 调用。
6. Runner恢复后执行全部 deterministic tests，真实失败优先修复。
7. deterministic tests 有执行证据后，再运行 Agnes 两套 benchmark。
8. Fact API / Profile / Match / Priority 接口稳定后，才进入老杨 H5/Web 演示端。
