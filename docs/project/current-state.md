# MedicalChannelAI 当前状态

日期：2026-08-28  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 1. 当前目标

首个天津 Pilot 证明：公开医疗商业信号能否被持续、可追溯地采集和验证，并在**模型不得创造采购事实、客户条件不足必须继续追问**的前提下，形成可执行的渠道/厂家销售优先级与行动建议。

当前聚焦医疗器械、IVD、耗材；不是医疗诊断或临床决策系统。

## 2. 当前规模

- 6 个运行时 P0 Source：4 个完整实现、2 个 PARTIAL
- **21 条 VERIFIED 天津商机 regression fixture**
- 5 条真实官方附件声明；真实附件 binary capture 仍为 0
- **11 份 JSON Schema/合同**
- **23 组 deterministic unittest 模块**
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- Agnes 2.5 Flash：`GO_FOR_BENCHMARK`，未执行生产准确率验收
- GitHub CI：`BLOCKED_RUNNER_NOT_ASSIGNED`

## 3. 事实底座

已实现：

- Evidence-first SourceRegistry / Opportunity / ProcurementEvent / EvidenceFact
- Snapshot SHA-256、官方来源角色、DAY/MINUTE 时间精度
- CCGP TENDER / AMENDMENT / TERMINATION / AWARD 生命周期
- Procurement Intent 月精度与官方 `projId`
- 天津医科大学总医院、天津第一中心医院早期信号
- 天津政府采购原始详情（PARTIAL）
- 天津公共资源采购结果镜像（PARTIAL）
- 中标供应商/金额及官方产品、品牌、型号、数量、单价
- DOCX/XLSX bounded parser
- 可选 Docling PDF backend，要求 page+bbox provenance；真实 PDF bytes 尚未验证，生产开关仍关闭

## 4. Canonical Identity / 防误合并

身份优先级：

1. 官方 `project_number`：允许跨官方来源确定性去重。
2. 官方 native record id（例如采购意向 `projId`）：`source_id + native_record_id`。
3. 没有项目编号/native id：`source_id + source_url` source-local identity。

**禁止 `buyer_name + project_name` 自动合并。**

真实回归：天津医科大学存在两条同单位、同名“PCR仪等设备采购项目”、同发布时间与预计采购月，但官方 `projId` 不同，预算分别300万元和70万元；必须保持两个独立 Opportunity。

Cross-stage 当前仅实现候选层：

- `status = CANDIDATE_REQUIRES_EVIDENCE`
- `auto_merge_allowed = false`
- timezone-aware chronology
- 不同显式项目编号直接阻止候选
- 真正 canonical bridge/merge 尚未实现

## 5. Customer Profile Gate

`tools/medical_pilot/customer_profile_gate.py`

核心原则：**字段非空不等于客户条件已经确认。**

后端会重新计算：

- `INCOMPLETE / PROFILE_INTERVIEW_REQUIRED`
- `SUFFICIENT_FOR_CANDIDATES / CANDIDATE_ONLY`
- `SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION / PERSONALIZED_RECOMMENDATION`

强制确认内容包括：

- 经营角色
- 城市全覆盖还是指定区县
- 客户类型
- 具体产品/细分类别与参与能力
- 是否能临时找厂家/联合渠道/做租赁
- 最低项目金额与偏好阶段
- 明确排除项；即使“没有排除项”也必须确认

前端自报 `profile_completeness=100` 不能绕过后端 Gate。

## 6. Opportunity Match Pipeline

公开入口：`tools/medical_pilot/match_pipeline.py`

顺序：

1. Customer Profile Gate
2. 商机必须 `VERIFIED`
3. Coverage 不能为 DEGRADED/UNKNOWN
4. 明确排除规则先执行
5. 区域/区县
6. 客户类型（不能从医院名字猜三甲/二级）
7. 项目阶段
8. 金额门槛
9. 产品能力
10. 租赁能力

缺关键事实时返回：

- `NEEDS_MORE_FACTS`
- `FACT_ENRICHMENT_REQUIRED`
- `model_explanation_allowed=false`

产品分类必须带：

- `product_label_provenance`
- `product_label_validation_status`

当前只有 `VALIDATED` 分类可以驱动匹配。Agnes 仍是 benchmark pending，因此它当前产生的 `CONTROLLED_MODEL_CLASSIFICATION + BENCHMARK_PENDING` **不能直接触发正式匹配**。

## 7. Grounded Model Decision Contract

`tools/medical_pilot/model_decision_contract.py`

只有 Match Pipeline 已得到 `MATCHED_CANDIDATE` 或 `MATCHED_PERSONALIZED`，模型才可进入该层。

模型输入只允许：

- VERIFIED、`model_generated=false` 的官方 Fact
- 已确认客户画像字段
- 当前 Match Gate 允许的动作/理由/风险枚举

v0.1 模型输出**没有自由采购事实文本**，只能选择：

- action code
- reason codes
- risk codes
- 已存在 `fact_id`
- 已允许的 profile paths

未知 `fact_id`、非法动作、非法 reason/risk code 直接拒绝。前端中文说明先由确定性模板渲染。

## 8. Transparent Priority Score v0.1

`tools/medical_pilot/priority_score.py`

满分100：

- 产品执行能力：30
- 客户确认医院关系：25
- 介入阶段：25
- 项目金额：20

明确固定：

`interpretation = BUSINESS_PRIORITY_NOT_WIN_PROBABILITY`

因此85分只能表示“经营优先级较高”，绝不能展示成“85%中标概率”。

没有客户确认的医院关系就记0分，不允许模型补关系分。

## 9. Source Topology / Coverage

政府采购：

1. `tj_government_procurement` — PRIMARY_SOURCE — PARTIAL
2. `ccgp_local_notices` — OFFICIAL_MIRROR — IMPLEMENTED
3. `tj_public_resource_exchange` — OFFICIAL_MIRROR — PARTIAL

采购意向当前由 `ccgp_procurement_intent` 提供；医院早期信号由 `tjmugh_procurement`、`tj_first_central_hospital_procurement` 作为 PRIMARY。

当前必须保持：

- `coverage_status = PARTIAL`
- `exhaustiveness_claim = NOT_EXHAUSTIVE`

不能宣称“天津已查全”。

## 10. Attachment / PDF

DOCX/XLSX 已有 bounded deterministic parser，并保留 paragraph / sheet+cell Evidence locator。

PDF 可选 `pdf-docling-v0.1`，只接受 SHA 已验证本地 PDF bytes；只有带 page_no+bbox provenance 的 block 才允许进入 Evidence。真实官方 PDF bytes 尚未跑通，因此 `.pdf parser_eligible=false` 仍保持关闭。

真实附件 fixture 仍强制：

- `binary_capture_status = PENDING_DIRECT_ATTACHMENT_BYTES`
- `sha256 = null`
- `parser_validation_status = NOT_RUN_ON_REAL_BYTES`

## 11. Agnes 2.5 Flash

当前：`GO_FOR_BENCHMARK`，**不是 production validated**。

已有：

- `docs/research/benchmarks/agnes-2.5-flash-v0.1.json`
- `tools/medical_pilot/benchmark_agnes.py`
- 12 case benchmark
- 默认 dry-run
- 只有显式 `--execute` + 环境变量 `AGNES_API_KEY` 才联网
- 仓库不保存 API Key

第一轮不让模型创造采购事实，主要验证分类、缺失信息判断与风险枚举。

## 12. CI真实状态

仍为 `BLOCKED_RUNNER_NOT_ASSIGNED`，Issue #2 跟踪。

最新检查仍为 GitHub Job：`runner_id=0 / runner_name="" / steps=[]`。因此目前23组 deterministic tests 都只能标“已写入等待执行证据”，不能宣称 PASS，也不能解释成 assertion failure。

## 13. 下一步

1. 把21条 VERIFIED corpus 扩到 >=50，并保持场景/生命周期多样性。
2. 获取第一份真实天津医疗 DOCX/XLSX/PDF bytes，实际验证 parser、MIME、redirect、SHA和 Evidence locator。
3. 验证天津政府采购网2026原生列表/搜索、分页和完整生命周期栏目。
4. 给 Match Pipeline 增加 institution/customer-type 可信 enrichment，不从名称猜医院等级。
5. 建立稳定的产品 taxonomy/分类合同，再用 Agnes benchmark 验证受控分类能力。
6. Runner 恢复后执行23组 deterministic tests，真实失败优先修。
7. 确定性执行有证据后运行 Agnes benchmark。
8. Fact API / Profile / Match / Priority 接口稳定后，再进入老杨 H5/Web 演示端。
