# MedicalChannelAI 当前状态

日期：2026-08-28  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE`  
生产就绪：**false**  
Draft PR：**#1**

## 1. 当前产品目标

首个 Pilot 只证明：能否持续、可追溯地发现天津区域公开医疗商业信号，并在模型不能创造事实的前提下，结合客户真实经营条件生成可执行的销售行动建议。

产品不是医疗诊断系统；当前聚焦医疗器械、IVD、耗材的渠道经营与厂家销售场景。

## 2. 当前事实底座

- 5 个 JSON Schema：SourceRegistry / Opportunity / ProcurementEvent / EvidenceFact / CustomerProfile
- 6 个已登记运行时 P0 Source，其中 4 个完整实现、2 个部分实现
- 8 条真实天津 regression fixtures
- bounded collector + Snapshot SHA-256
- Evidence Fact 生成
- Procurement Intent 解析
- CCGP lifecycle 解析
- deterministic LifecycleLinker
- 中标供应商/金额与官方产品/品牌/型号/数量/单价解析
- 天津医科大学总医院早期市场调研解析
- 天津第一中心医院院内比选/测试企业征集解析
- 天津公共资源政府采购结果官方镜像解析（部分实现）
- 天津市政府采购网原始详情页解析（部分实现）
- PRIMARY_SOURCE / OFFICIAL_MIRROR / DISCOVERY_ONLY 来源角色，已在所有 Runtime Source 中显式配置并由 Schema 强制
- DAY / MINUTE 发布时间精度
- 同项目跨源去重与精度感知生命周期聚合
- 附件白名单、host/MIME/size/hash 安全链
- DOCX / XLSX bounded stdlib parser；输出段落或单元格 Evidence locator
- PDF / DOC / XLS 当前只允许安全下载并保留快照，`parser_eligible=false`
- XLSX 公式缓存值当前不采信、不进入确定性文本层
- SourceHealth / Coverage 聚合
- CLI 单 URL evidence-backed 输出，并暴露解析后的 `provenance_role`
- 12 组 deterministic unittest 模块

## 3. 当前真实 fixture

1. 天津市胸科医院检验科设备租赁 — 573万元 / TENDER
2. 天津医院 SPECT/CT — TERMINATED
3. 天津市泰达医院 DR — 250万元 / TENDER
4. 天津中医药大学第一附属医院光电同步脑活动检测仪 — 390万元 / PROCUREMENT_INTENT / `2026-05` 月精度
5. 天津医科大学 GMP 实验室核心设备 — 873.27万元 / AWARD / 供应商 + 东富龙品牌型号表
6. 天津市第一中心医院手术无影灯 — INTERNAL_SELECTION / 1.98万元
7. 天津市第一中心医院医疗器械精细化管理 — MARKET_RESEARCH / 测试企业征集
8. 天津市疾病预防控制中心性病艾滋病检测试剂、耗材 — AWARD / 天津公共资源官方镜像 / DAY 精度 / 供应商与官方产品品牌型号

## 4. Source Topology

政府采购主链路已经固定为：

1. `tj_government_procurement` — `PRIMARY_SOURCE`
2. `ccgp_local_notices` — `OFFICIAL_MIRROR`
3. `tj_public_resource_exchange` — `OFFICIAL_MIRROR`

采购意向当前由 `ccgp_procurement_intent` 提供，暂按 `OFFICIAL_MIRROR` 使用，直到天津原始采购意向入口完成验证。

医院官网早期信号：

- `tjmugh_procurement` — `PRIMARY_SOURCE`
- `tj_first_central_hospital_procurement` — `PRIMARY_SOURCE`

机器可读拓扑：`tools/medical_pilot/source_topology.tianjin.v0.1.json`。

### 去重规则

- 官方存在项目编号时，以 exact normalized `project_number` 形成 canonical project identity。
- 同项目出现在 PRIMARY、CCGP、公共资源时保留多个 Evidence Event，但只能形成一个 Opportunity。
- URL 不是项目身份。
- 同一生命周期、同一天且不能证明精确先后时，主证据优先 PRIMARY_SOURCE。
- 同一天出现矛盾生命周期且任一来源只有 DAY 精度时，必须 `CONFLICTED / UNKNOWN`，禁止用规范化 `00:00` 猜测先后。

### 时效差规则

只有同时满足以下条件才能计算来源间分钟级时延：

- 同一 canonical project / lifecycle event；
- 两端都是来源自身发布的时间；
- 两端都是 `MINUTE` 精度。

否则必须记 `LATENCY_UNKNOWN`。抓取时间不能伪装成发布时间。

## 5. 当前 Coverage

完整实现：

- `ccgp_local_notices`
- `ccgp_procurement_intent`
- `tjmugh_procurement`
- `tj_first_central_hospital_procurement`

部分实现：

- `tj_public_resource_exchange`：当前只验证 `/jyxxcgjg/` 政府采购结果详情页。
- `tj_government_procurement`：当前确认 2026 使用 `tjgp.cz.tj.gov.cn`，并实现 `/portal/documentView.do?method=view&id=<digits>&ver=2` 直接详情页解析；尚未验证 2026 原生列表/搜索、分页及全部生命周期栏目。

因此当前状态必须保持：

- `coverage_status = PARTIAL`
- `exhaustiveness_claim = NOT_EXHAUSTIVE`

不能宣称“天津已查全”。

## 6. Attachment Parser 状态

当前下载允许：`.pdf / .doc / .docx / .xls / .xlsx`；`.zip / .rar / .7z` 只发现，不自动下载解包。

当前真正可确定性解析：

- `.docx`：读取 `word/document.xml`，输出 `DOCX_PARAGRAPH` + paragraph locator。
- `.xlsx`：读取 workbook / relationships / shared strings / worksheet XML，输出 `XLSX_RANGE` + sheet/range locator。

当前安全限制：

- Snapshot SHA-256 必须与 bytes 一致。
- OOXML 加密成员拒绝。
- 路径逃逸成员拒绝。
- 最大 ZIP member 数、总解压大小、最大文本量、最大 XLSX 单元格数受限。
- XLSX 公式单元格不计算，也不采信缓存值。
- `.pdf / .doc / .xls` 当前 `DOWNLOAD_ONLY_PARSER_PENDING`，不能标成已解析。

## 7. Agnes 2.5 Flash

状态：`GO_FOR_BENCHMARK`

尚未完成真实 API 医疗准确率生产验收。

允许承担候选任务：医疗产品分类、辅助结构化、客户能力/商机匹配、缺失条件追问、确定性评分解释、销售行动建议。

不得成为采购事实权威：采购人/医院、项目名、预算、日期/截止时间、生命周期状态、中标供应商/金额、官方产品品牌型号数量价格、来源 URL。

## 8. CI / 自动测试真实状态

GitHub Actions 仍为：`BLOCKED_RUNNER_NOT_ASSIGNED`。

已记录 Issue #2。已知证据：Job `runner_id=0`、`runner_name=""`、`steps=[]`，日志对象 `BlobNotFound`。因此 GitHub Runner 没有执行 Python；不能标 PASS，也不能把红色 CI 解释为 assertion failure。

本轮新增测试代码仍属于“已写入、等待可执行证据”，不得宣称已经跑绿。

## 9. 下一步

1. 找到并验证天津市政府采购网 2026 原生列表/搜索入口、分页与栏目路由，才能把 PRIMARY 从 PARTIAL 升到 IMPLEMENTED。
2. 增加至少一条真实 2026 天津医疗项目的原始站详情快照 fixture，与 CCGP 镜像做双源字段/发布时间对照。
3. 获取真实采购附件 fixture，先验证 DOCX/XLSX parser 对实际招标文件/设备清单的表现。
4. 为 PDF 选定可控解析方案并建立真实 PDF 页码 Evidence locator；未完成前保持 parser pending。
5. 继续验证天津公共资源招标/更正/终止栏目，决定是否值得升级完整实现，或只作为结果补证源。
6. 先扩到 >=20 VERIFIED 天津样本，再扩到 >=50。
7. GitHub Runner 恢复后第一时间执行全部 deterministic tests 并修真实失败。
8. 事实层稳定后跑 Agnes 2.5 Flash benchmark。
9. 最后再进入首批客户 H5/Web 演示端。
