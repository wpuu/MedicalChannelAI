# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- **7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION**
- **50 条 VERIFIED 天津商机 regression fixture**
- 5 条真实官方附件声明；**真实官方附件 binary capture = 0**
- **15 条天津机构官方 Evidence fixture**
- **23 份正式 JSON Schema/合同**
- **40 组 deterministic unittest 模块**
- 2 套 Agnes benchmark，共 **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 当前核心链路

`Source → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → VERIFIED Material Event → Institution/Taxonomy → Profile Gate → Match → Query Budget → Priority → Daily Recommendation → Subscription Prefilter/Batch → Notification Route → Delivery State → Latency Ledger → Follow-up → Grounded Model Decision`

## Query Budget / Daily / Subscription

客户画像允许保存真实完整的区域与产品范围；限制的是单次执行，不要求客户为了性能填写虚假的小范围。

交互默认：DB候选500 → deterministic match200 → deep enrichment30 → model candidates10 → final action cards5；interactive live crawl=0；单商机模型最多24条 VERIFIED facts / 12000字符。

订阅由客户画像驱动：新 VERIFIED Material Event → `region + taxonomy + customer_type` 反向预筛 → `batch_limit<=1000 + next_offset` 分批 → 每个候选仍跑完整 Match → enrichment/digest/immediate/no-notify。terminal follow-up 抑制同一 opportunity 重复提醒；有 owner 优先路由 owner。

## VERIFIED Material Event / Delivery / Latency

只有 VERIFIED opportunity + VERIFIED/non-model `OFFICIAL_PUBLIC_FACT` 才能生成 Material Event，且每个 semantic `change_fields` 必须被 supplied fact 的 field_name/value 支持。镜像补 Evidence、发现时间变化或 DAY/MINUTE 精度变化不能重复制造同一业务事件。

Notification Delivery 使用稳定 `subscription_dedupe_key + channel` 身份，状态为 `QUEUED → SENT → DELIVERED` 或受控 `FAILED` 重试；SUPPRESSED 使用真实 `audience=NONE`。默认最多3次，时间戳必须 timezone-aware 且单调。

Latency Ledger 记录 `official published → discovered → fetched → verified → matched → notification queued → delivered`；官方只有 DAY 精度时禁止计算分钟级 publication latency。

## Tianjin Government Procurement 官方来源拓扑

### 1. 天津市政府采购网 / 财政发布体系

`source_id=tj_government_procurement`，`PRIMARY_SOURCE`，当前 `PARTIAL_IMPLEMENTATION`。

同一个 Source identity 认可三个官方 host/alias：

- `tjgp.cz.tj.gov.cn`
- `ccgp-tianjin.gov.cn`
- `www.ccgp-tianjin.gov.cn`

Runtime detail validator：path 必须 `/portal/documentView.do`，query 必须恰好 `method=view + numeric id + ver=2`，参数顺序不限，多余/重复参数拒绝。Registry 与 Adapter 已统一支持全部官方 alias。

仍未验证：2026 原生列表/搜索/分页、crawler runtime 直接详情抓取、source-native attachment href、原生分钟级发布时间。当前执行容器对相关 host 的 DNS/下载探测失败，只解释为执行环境限制，不解释为网站 outage。

### 2. 天津市政府采购中心网（新增 P0 PRIMARY 补充源）

`source_id=tj_government_procurement_center`，host `tjgpc.zwfwb.tj.gov.cn`，`PRIMARY_SOURCE / PARTIAL_IMPLEMENTATION`。

已由当前官方索引验证并实现：

- detail route：`/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=<UUID>`；
- 公开招标详情的项目名/编号、采购人、信息日期、预算、截止时间确定性解析；
- 医疗详情页真实样本：天津医科大学第二医院 `TGPC-2025-A-0164`，正文明确多功能吊塔、呼吸机、中央监护、支气管镜、除颤仪等，且页面显示 `招标文件（TGPC-2025-A-0164）.docx`；
- 官方附件 wrapper 家族：`/webInfo/downloadFile.do?fileName=...&fileUrl=...` 已由搜索索引确认能承载真实文档内容。

安全策略：wrapper 目前**只发现、不授权下载**。内层 `fileUrl` 永远不直接请求；v0.1 仅接受已观察到的 `218.67.246.33:7001/ZTBS/fileupload/gw/...` 结构做安全校验，其他 host/端口/路径拒绝。`AttachmentCandidate.download_authorized=false` 会让通用 Fetcher 在网络请求前 fail-closed。

尚未完成：原生列表 class id / pagination、全部采购方式、医疗项目对应的精确 wrapper URL、crawler runtime 真实附件 bytes、MIME/magic/SHA。该 Source 是集采项目子集/投标入口，**不是全市财政采购源替代品**。

### 3. 其他

- `ccgp_local_notices`：OFFICIAL_MIRROR / IMPLEMENTED
- `ccgp_procurement_intent`：OFFICIAL_MIRROR / IMPLEMENTED
- `tj_public_resource_exchange`：OFFICIAL_MIRROR / PARTIAL（当前仅结果页）
- `tjmugh_procurement`：PRIMARY / IMPLEMENTED
- `tj_first_central_hospital_procurement`：PRIMARY / IMPLEMENTED

多个 PRIMARY/MIRROR 出现同一项目时，仍按官方 `project_number` 聚合一个 canonical opportunity；不同页面保留独立 Evidence Event，不重复计算商机。

## Attachment 安全链

DOCX/XLSX parser 已实现；PDF Docling backend 只有代码合同。通用附件下载器现增加：

- discovery 与 download authorization 分离；
- PDF 必须 `%PDF-` magic；
- DOCX/XLSX 必须 ZIP magic；
- DOC/XLS 必须 OLE magic；
- MIME允许但 magic 不符也 fail-closed。

目前搜索索引能读取官方 `tjgpc downloadFile.do` PDF正文，但 web/container 直接取 bytes 仍失败。因此准确状态仍是：**官方 wrapper 机制确认，MedicalChannelAI 实际附件 bytes 捕获=0，医疗附件 bytes=0。**

## Institution / Taxonomy / Agnes

15条 VERIFIED 官方 Institution Evidence；机构只做精确名称/显式 alias。正式匹配使用稳定 taxonomy IDs；deterministic/human-confirmed classifier 已准入，Agnes taxonomy classifier 仍 `BENCHMARK_PENDING / can_drive_matching=false`。

50条 corpus audit harness 已就绪，但 Runner 未执行，因此不宣称 deterministic coverage rate。Agnes 两套 benchmark 共28 case，均未执行。

## CI真实状态

GitHub Actions 仍为 Runner 基础设施问题；最近已确认的 job 仍无 Python steps。**当前40组 tests 只能标“已写入等待真实执行证据”，不能标 PASS，也不能解释为 assertion failure。** Issue #2 持续跟踪。

## 下一步

1. 继续从 `tjgpc` 搜索索引/官方页面反查医疗 DOCX 的精确 `downloadFile.do` wrapper URL；拿到后仍先验证，不直接跟 nested `fileUrl`。
2. 获取第一份真实官方附件 bytes；分别记录“任意官方采购附件 bytes”和“医疗附件 bytes”，避免混报。
3. 继续验证 `tjgpc` 原生列表 class id / pagination，以及天津财政 PRIMARY 的原生列表/搜索/分页。
4. Runner恢复后执行40组 tests 与 taxonomy corpus audit，优先修真实失败。
5. deterministic execution 有证据后再跑 Agnes benchmark。
6. 后端 API 稳定后再进入 H5/微信小程序端。
