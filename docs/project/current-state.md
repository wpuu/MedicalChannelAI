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
- **50 条 VERIFIED 天津商机 regression fixture**
  - 8 primary
  - 1 attachment-backed
  - 2 procurement-intent identity
  - 10 expanded v0.1
  - 16 expanded v0.2
  - 13 expanded v0.3
- 5 条真实官方附件声明；真实附件 binary capture 仍为 0
- 5 条天津机构官方 Evidence fixture
- **13 份正式 JSON Schema/合同**
- **28 组 deterministic unittest 模块**
- 2 套 Agnes benchmark：12 + 16 = **28 个 case**
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

50条 corpus 已达到第一轮模型/分类评估所需的样本规模门槛，但**不等于覆盖天津全部商机**。

## 3. 事实底座

已实现 Evidence-first SourceRegistry / Opportunity / ProcurementEvent / EvidenceFact、Snapshot SHA-256、官方来源角色、DAY/MINUTE 时间精度、CCGP 生命周期、采购意向 `projId`、医院官网早期信号、政府采购原始详情 PARTIAL、公共资源结果镜像 PARTIAL、中标产品/品牌/型号/数量/单价，以及 bounded DOCX/XLSX parser。

PDF Docling backend 代码存在，但真实官方 PDF bytes 尚未验证，生产开关仍关闭。

## 4. Canonical Identity / Cross-stage

身份优先级：官方 `project_number` → source native id → source+URL。禁止 `buyer_name + project_name` 自动合并。

Cross-stage 当前只有 `CANDIDATE_REQUIRES_EVIDENCE`，`auto_merge_allowed=false`；真正 canonical bridge/merge 尚未实现。

## 5. Customer / Matching Profile Gate

基础经营访谈由 `customer_profile_gate.py` 负责；正式商机匹配使用 `matching_profile_gate.py`。

正式匹配要求客户产品能力映射到受控 `taxonomy_ids`。人类可读 category/subcategory 仅用于开户访谈和 UI；规则层只认 taxonomy ID。缺失/非法 taxonomy 会重新降为 `INCOMPLETE / PROFILE_INTERVIEW_REQUIRED` 并生成下一句问题。

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

模型只能选择预设 action/reason/risk code，并引用已有 VERIFIED fact_id / 已确认 profile path；v0.1 不允许模型自由创造采购事实。

Priority Score = 产品能力30 + 客户确认关系25 + 阶段25 + 金额20，固定 `BUSINESS_PRIORITY_NOT_WIN_PROBABILITY`。

## 10. 50条 corpus 的新增覆盖

本轮新增后，样本进一步覆盖：

- 血培养仪、流式细胞仪/分选仪
- MRI、CT、DR、乳腺X线、口腔CT
- 内窥镜、电子输尿管肾盂镜、内窥镜AI辅助诊断
- 急救生命支持/呼吸机/血液净化
- 消毒灭菌、超分辨显微镜、细胞荧光处理
- 眼科检测试纸、内窥镜清洗液
- 医院设备维保/维修及明确装机品牌、型号、购置时间
- 多设备早期市场调研

多子项市场调研页面仍**按一个 source-record Opportunity 计数**，不拆子项虚增数量。

如果官方结果索引能证明项目已成交、但正文当前不可抓取，则只锁 `AWARDED`/项目身份；金额、供应商等保持未知，不从早期招标公告补值。

## 11. Agnes benchmark

当前仍是 `GO_FOR_BENCHMARK`，不是 production validated。

两套 benchmark：12 case 粗分类/风险 + 16 case 正式 taxonomy/安全放弃分类。均默认 dry-run；只有 `--execute` + 环境变量 `AGNES_API_KEY` 才联网。

## 12. Source Topology / Coverage

政府采购：天津政府采购 PRIMARY PARTIAL；CCGP OFFICIAL_MIRROR IMPLEMENTED；天津公共资源 OFFICIAL_MIRROR PARTIAL。医院官网早期信号由总医院和第一中心医院作为 PRIMARY。

Coverage 必须继续 `PARTIAL / NOT_EXHAUSTIVE`，不能宣称“天津已查全”。

## 13. Attachment / PDF

DOCX/XLSX parser 已实现，真实官方附件 bytes 捕获仍为0。PDF Docling仅有代码合同，没有真实字节验证，因此不能宣称附件解析生产可用。

## 14. CI真实状态

最后确认的 Medical Pilot CI Run `33176009681` / Job `98864682367` 为 failure 且 `steps=[]`；Python compile/unittest 未开始执行。因此28组 tests 仍只能标“已写入等待执行证据”，不能标 PASS，也不能解释为 assertion failure。

Issue #2 继续跟踪 Runner/Actions 基础设施。

## 15. 下一步

1. 对50条 corpus 做 deterministic taxonomy coverage audit，量化本地规则覆盖率与需要 Agnes/人工的比例。
2. 获取第一份真实天津医疗 DOCX/XLSX/PDF bytes，验证 MIME/redirect/SHA/parser locator。
3. 验证天津政府采购网2026原生列表/搜索、分页和完整生命周期栏目。
4. 扩充 Institution Evidence 与 deterministic taxonomy 高特异规则。
5. Runner恢复后执行全部 deterministic tests；真实失败优先修。
6. deterministic execution 有证据后，运行 Agnes 两套 benchmark。
7. Fact/Profile/Match/Priority API 稳定后，再进入老杨 H5/Web 演示端。
