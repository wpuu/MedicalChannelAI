# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- **7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION**
- **50 条 VERIFIED 天津商机 regression fixture**
- 5 条真实官方附件声明；**真实官方附件 binary capture = 0；医疗附件 bytes = 0**
- **15 条天津机构官方 Evidence fixture**
- **23 份正式 JSON Schema/合同**
- **40 组 deterministic unittest 模块**
- 2 套 Agnes benchmark，共 **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 核心链路

`Source → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → VERIFIED Material Event → Institution/Taxonomy → Profile Gate → Match → Query Budget → Priority → Daily Recommendation → Subscription Prefilter/Batch → Notification Route → Delivery State → Latency Ledger → Follow-up → Grounded Model Decision`

## Query / Subscription / Notification

客户画像允许完整保存真实区域和产品；限制单次执行复杂度：DB候选500 → deterministic match200 → deep enrichment30 → model candidates10 → final Top5；interactive live crawl=0；单商机模型最多24条 VERIFIED facts / 12000字符。

订阅由 VERIFIED Material Event 驱动；反向预筛只优化性能，候选仍跑完整 Match；`batch_limit<=1000 + next_offset` 分批；普通匹配进入 digest，fully-confirmed + 高优先级才即时提醒；terminal follow-up 抑制同 opportunity 重复提醒。

Notification Delivery 使用稳定 identity，状态 `QUEUED → SENT → DELIVERED` 或受控 FAILED 重试；SUPPRESSED=`audience=NONE`。Latency Ledger 不允许 DAY 精度伪造成分钟级同步速度。

## 天津政府采购来源

### `tj_government_procurement` — PARTIAL PRIMARY

同一 Source identity 认可 `tjgp.cz.tj.gov.cn`、`ccgp-tianjin.gov.cn`、`www.ccgp-tianjin.gov.cn`。Registry 与 Adapter 已统一支持 exact `/portal/documentView.do` + `method=view` + numeric `id` + `ver=2`，参数顺序可变但多余/重复参数拒绝。

仍未验证原生列表/搜索/分页、crawler runtime 直接详情抓取、source-native attachment href。

### `tj_government_procurement_center` — 新增 PARTIAL PRIMARY 补充源

Host：`tjgpc.zwfwb.tj.gov.cn`。该源是**集采项目/电子投标入口子集，不替代全市财政采购源**。

已实现/确认：

- detail route：`/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=<UUID>`；
- 公开招标项目名/编号、采购人、信息日期、预算、截止时间确定性解析；
- 医疗样本 `TGPC-2025-A-0164`（天津医科大学第二医院重症病房医疗设备），官方详情明确多功能吊塔、有创/转运呼吸机、中央监护、支气管镜、除颤仪等，且显示 DOCX 招标文件名；
- 官方附件 wrapper `/webInfo/downloadFile.do?fileName=...&fileUrl=...` 已被搜索索引解析为真实文档内容。

安全边界：wrapper 目前只允许 discovery，`download_authorized=false`；nested `fileUrl` 永远不直接请求。v0.1 仅认可已观察的 `218.67.246.33:7001/ZTBS/fileupload/gw/...` 结构用于安全校验；其他 origin/port/path fail-closed，并对编码路径做有界重复解码后再检查 traversal。

尚未确认：医疗项目精确 wrapper URL、crawler runtime bytes/MIME/magic/SHA、原生列表 class id / pagination、全部采购方式。

### 其他 P0

IMPLEMENTED：`ccgp_local_notices`、`ccgp_procurement_intent`、`tjmugh_procurement`、`tj_first_central_hospital_procurement`。PARTIAL：`tj_public_resource_exchange`。

多个 PRIMARY/MIRROR 出现同一项目时仍按官方 project_number 聚合一个 canonical opportunity，不重复计商机。

## Attachment 安全链

附件发现和下载授权已分离。通用 Fetcher 新增 magic 校验：PDF=`%PDF-`；DOCX/XLSX=ZIP；DOC/XLS=OLE。即使 MIME 合法，magic 不符仍 fail-closed。

当前搜索索引可读取 `tjgpc downloadFile.do` 的 PDF 文本，但 web/container 直接抓字节仍失败。因此准确状态仍是：**官方 wrapper 机制已确认；MedicalChannelAI 实际官方附件 bytes=0；医疗附件 bytes=0。**

## Institution / Taxonomy / Agnes

15条 VERIFIED Institution Evidence；正式匹配使用稳定 taxonomy IDs。Agnes taxonomy classifier 仍 `BENCHMARK_PENDING / can_drive_matching=false`；两套 benchmark 共28 case 均未执行。50条 taxonomy corpus audit harness 已就绪，但没有 Runner 执行证据。

## CI真实状态

最新检查：Run `33230101416` / Job `99041292283`，`runner_id=0`、`runner_name=""`、`steps=[]`、conclusion=failure。Python compile/unittest 没有执行。

因此当前40组 tests 只能标“已写入等待执行证据”，不能标 PASS，也不能解释为 assertion failure。Issue #2 持续跟踪。

## 下一步

1. 继续反查 `TGPC-2025-A-0164` 等医疗项目的精确 `downloadFile.do` wrapper URL，不猜 fileUrl。
2. 捕获第一份真实官方附件 bytes，并把任意官方采购附件 / 医疗附件分开计数。
3. 验证 `tjgpc` 原生列表 class id / pagination，并继续天津财政 PRIMARY 原生列表/搜索/分页。
4. Runner恢复后执行40组 tests 与 taxonomy corpus audit。
5. deterministic execution 有证据后再跑 Agnes benchmark。
6. 后端 API 稳定后再进入 H5/微信小程序端。
