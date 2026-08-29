# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- **7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION**
- **50 条 VERIFIED 天津商机 regression fixture**
- **15 条天津机构官方 Evidence fixture**
- **23 份正式 JSON Schema/合同**
- **40 组 deterministic unittest 模块**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 2套 Agnes benchmark 共28 case，均未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 本阶段新增重点

### 天津市政府采购中心网

新增 P0 `tj_government_procurement_center`，`PRIMARY_SOURCE / PARTIAL_IMPLEMENTATION`。它是集采项目/电子投标入口子集，不替代全市财政采购源。

已实现官方详情：`/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=<UUID>`，确定性解析项目名/编号、采购人、信息日期、预算、投标截止时间。

医疗样本 `TGPC-2025-A-0164`（天津医科大学第二医院重症病房医疗设备）官方详情明确：多功能吊塔2台、有创呼吸机2台、转运呼吸机1台、中央监护系统1套、支气管镜系统1套、电动转运床2台、除颤仪1台、冰毯2台；预算300万元；页面显示 DOCX 招标文件名。

官方站 `downloadFile.do?fileName=...&fileUrl=...` wrapper 已由搜索索引解析出真实文档正文，但当前 web/container 直接获取 bytes 仍失败。因此只实现 **discovery-only**：`download_authorized=false`，nested `fileUrl` 永远不直接请求。

v0.1 对 nested URL 只接受已观察的 `http://218.67.246.33:7001/ZTBS/fileupload/gw/...` 结构用于安全校验；未知 host/port/path、路径逃逸、异常编码 fail-closed。

### Attachment Fetch 安全修复

附件 discovery 与 download authorization 已分离。通用 Fetcher 新增 magic 校验：PDF=`%PDF-`；DOCX/XLSX=ZIP；DOC/XLS=OLE。MIME看似合法但 magic 不符也拒绝。

### 天津财政 PRIMARY alias 一致性修复

`tj_government_procurement` 的 Registry 与 Adapter 现在统一支持 `tjgp.cz.tj.gov.cn`、`ccgp-tianjin.gov.cn`、`www.ccgp-tianjin.gov.cn` 这一个 PRIMARY Source 的官方 host/alias；此前“Registry允许 alias、Adapter二次拒绝”的不一致已修复。

## 既有核心链路

`Source → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → VERIFIED Material Event → Institution/Taxonomy → Profile Gate → Match → Query Budget → Priority → Daily Recommendation → Subscription Prefilter/Batch → Notification Route → Delivery State → Latency Ledger → Follow-up → Grounded Model Decision`

客户画像可宽，但单次执行受 Query Budget 约束；订阅反向预筛只做性能优化，最终仍跑完整 Match；通知有稳定幂等、terminal follow-up 防骚扰和 Latency Ledger。

## CI真实状态

最新确认 Run `33230101416` / Job `99041292283`：`runner_id=0`、`runner_name=""`、`steps=[]`、conclusion=failure。Python compile/unittest 没有执行，因此40组 tests 不能标 PASS，也不是 assertion failure。Issue #2 跟踪。

## 下一步

1. 继续反查 `TGPC-2025-A-0164` 等医疗项目精确 `downloadFile.do` wrapper URL，不猜 fileUrl。
2. 捕获第一份真实官方附件 bytes；任意官方采购附件与医疗附件分开计数。
3. 验证 `tjgpc` 原生 list class id / pagination，并继续天津财政 PRIMARY 原生 list/search/pagination。
4. Runner恢复后执行40组 tests 与 taxonomy corpus audit。
5. deterministic execution 有证据后再跑 Agnes benchmark。
6. 后端 API 稳定后再进入 H5/微信小程序端。
