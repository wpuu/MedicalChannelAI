# MedicalChannelAI 当前状态

日期：2026-08-28  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE`  
生产就绪：**false**  
Draft PR：**#1**

## 1. 当前目标

首个天津 Pilot 只证明：能否持续、可追溯地发现公开医疗商业信号，并在模型不能创造采购事实的前提下，结合客户真实经营条件形成可执行的渠道/销售建议。

当前聚焦医疗器械、IVD、耗材；不是诊断或临床决策系统。

## 2. 当前事实底座

- 5 个 JSON Schema：SourceRegistry / Opportunity / ProcurementEvent / EvidenceFact / CustomerProfile
- 6 个运行时 P0 Source：4 个完整实现、2 个部分实现
- **21 条 VERIFIED 天津商机 regression fixture**：8 主 fixture + 1 attachment-backed + 2 procurement-intent identity + 10 expanded official corpus
- 5 条真实官方附件声明 fixture；真实附件二进制捕获仍为 0
- bounded collector + Snapshot SHA-256 + Evidence Fact
- CCGP TENDER / AMENDMENT / TERMINATION / AWARD 生命周期解析
- Procurement Intent 月份精度与官方 `projId` 身份
- 天津医科大学总医院、天津第一中心医院早期信号
- 天津公共资源政府采购结果官方镜像（PARTIAL）
- 天津市政府采购网原始详情页（PARTIAL）
- `PRIMARY_SOURCE / OFFICIAL_MIRROR / DISCOVERY_ONLY`
- `DAY / MINUTE` 发布时间精度与 timezone-aware chronology
- 精度感知 LifecycleLinker
- 中标供应商、金额及官方产品/品牌/型号/数量/单价解析
- DOCX/XLSX bounded stdlib parser
- 可选 Docling PDF backend；要求页码+bbox provenance；尚未真实 PDF 验证，生产开关仍关闭
- 本地附件验证 CLI；PDF 需要显式 `--enable-docling-pdf`
- fail-closed Canonical Identity + cross-stage candidate layer
- SourceHealth / Coverage / Source Topology
- **18 组 deterministic unittest 模块**
- Agnes 2.5 Flash benchmark manifest + opt-in harness，尚未执行

## 3. Canonical Identity / 防误合并

本轮修复高风险 over-dedup：天津医科大学存在两条独立政府采购意向，采购单位和项目名称都为“天津医科大学 / PCR仪等设备采购项目”，发布时间和预计采购月也相同，但官方 `projId` 不同，预算分别 300万元与70万元。它们必须是两个独立 Opportunity。

当前身份优先级：

1. 有官方 `project_number`：按项目编号建立 canonical identity，可跨官方来源去重。
2. 有官方 native record id：按 `source_id + native_record_id` 建立独立 identity。
3. 没有项目编号/native id：按 `source_id + source_url` 保持 source-local identity。

**禁止 `buyer_name + project_name` 自动合并。**

机器规则：`tools/medical_pilot/identity_policy.tianjin.v0.1.json`。

## 4. Cross-stage Link Candidate

已实现 `tools/medical_pilot/cross_stage_link.py`，解决“过度去重修掉以后，怎样安全提示采购意向可能对应后来的正式招标”。

v0.1 只有候选层，不执行 canonical merge。候选至少要求：

- 双方都 VERIFIED；
- 阶段属于 PROCUREMENT_INTENT / MARKET_RESEARCH / INTERNAL_SELECTION → TENDER；
- 标准化采购单位完全一致；
- 标准化项目名完全一致；
- timezone-aware 发布时间顺序向前；
- 两边若都有显式项目编号，不允许编号冲突。

即使全部满足，结果仍固定：

- `status = CANDIDATE_REQUIRES_EVIDENCE`
- `auto_merge_allowed = false`
- `confidence = 0.70` 仅为 v0.1 固定启发式候选分，不是概率或生产置信度。

LLM 可以以后帮助扩大候选召回，但不能执行 merge。真正 canonical bridge 仍需 deterministic public evidence。

## 5. Source Topology / Coverage

政府采购：

1. `tj_government_procurement` — PRIMARY_SOURCE — PARTIAL
2. `ccgp_local_notices` — OFFICIAL_MIRROR — IMPLEMENTED
3. `tj_public_resource_exchange` — OFFICIAL_MIRROR — PARTIAL

采购意向当前由 `ccgp_procurement_intent` 提供；医院早期信号由 `tjmugh_procurement`、`tj_first_central_hospital_procurement` 作为 PRIMARY。

当前 Coverage 必须保持：

- `coverage_status = PARTIAL`
- `exhaustiveness_claim = NOT_EXHAUSTIVE`

不能宣称“天津已查全”。

## 6. Attachment / PDF 状态

### 已实现

- DOCX：`DOCX_PARAGRAPH` + paragraph locator
- XLSX：`XLSX_RANGE` + sheet/range locator
- Snapshot SHA-256 校验
- ZIP成员数/解压大小/路径逃逸/加密OOXML/最大文本量/最大单元格边界
- XLSX公式缓存值不采信

### PDF

可选 `pdf-docling-v0.1`：只接受 SHA 已验证的本地 PDF bytes；最大 32MB / 200页 / 50,000 grounded blocks；`enable_remote_services=false`；只有带 Docling `page_no + bbox` provenance 的文本/表格才输出 Evidence block。

真实官方 PDF bytes 尚未跑通，因此基础下载层仍保持 `.pdf parser_eligible=false`，不能宣称 PDF 已生产可用。

真实附件 fixture 统一保持：

- `binary_capture_status = PENDING_DIRECT_ATTACHMENT_BYTES`
- `sha256 = null`
- `parser_validation_status = NOT_RUN_ON_REAL_BYTES`

## 7. VERIFIED 样本进度

当前总数：**21**。

新增 corpus 覆盖同名不同 `projId` PCR意向、流式/qPCR研究设备、流式细胞仪、县域DR/CT设备更新、血液病医院试剂耗材、疾控病原微生物设备、荧光显微成像/GMP质量检测设备等。正式招标和中标是生命周期事件时不重复计算为两个 Opportunity。

所有 fixture 均要求：官方正文没写的品牌、产品、供应商、科室、关系等不得补全。

## 8. Agnes 2.5 Flash

当前：`GO_FOR_BENCHMARK`，**不是 production validated**。

已建立：

- `docs/research/benchmarks/agnes-2.5-flash-v0.1.json`
- `tools/medical_pilot/benchmark_agnes.py`
- 12 个首轮 benchmark case
- 默认 dry-run；只有显式 `--execute` 且环境存在 `AGNES_API_KEY` 才调用
- 仓库不保存 API Key
- 第一轮只测：渠道粗分类、附件是否不足、是否需要更多来源、风险枚举；不允许自由文本或生成采购事实

首轮 Gate：segment ≥90%；item detail / missing-source ≥95%；required risk recall ≥95%；invalid enum=0；API/JSON failure ≤2%。

## 9. CI 真实状态

仍为：`BLOCKED_RUNNER_NOT_ASSIGNED`，Issue #2 跟踪。

最新检查仍出现 GitHub Job `runner_id=0 / runner_name="" / steps=[]`，Python compile/unittest 没有执行，所以不能标 PASS，也不能解释为 assertion failure。

当前 18 组测试均属于“测试代码已写入，等待真实执行证据”。

## 10. 下一步

1. 扩到 >=50 VERIFIED 天津商机，保持类型/生命周期多样性。
2. 获取第一份真实天津医疗采购 DOCX/XLSX/PDF bytes，记录 redirect/MIME/size/SHA 并实际跑 parser。
3. 验证天津政府采购网 2026 原生列表/搜索、分页和全生命周期栏目。
4. 在 link candidate 之上实现真正 evidence-backed canonical bridge；在此之前始终 `auto_merge=false`。
5. Runner 恢复后执行全部 deterministic tests，真实失败优先修复。
6. 确定性测试有执行证据后，再用环境变量运行 Agnes 2.5 Flash benchmark。
7. Fact API / Customer Profile 稳定后才进入老杨 H5/Web 演示端。
