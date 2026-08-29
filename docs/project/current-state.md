# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- **7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION**
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- 23 份 Schema/合同
- **40 组 deterministic unittest 模块**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## 本阶段重点

新增 `tj_government_procurement_center`（`tjgpc.zwfwb.tj.gov.cn`）作为 `PRIMARY_SOURCE / PARTIAL_IMPLEMENTATION` 集采补充源。已实现 UUID detail route 解析；医疗样本 `TGPC-2025-A-0164` 官方详情明确吊塔、呼吸机、中央监护、支气管镜、除颤仪等及 DOCX 文件名。

官方 `downloadFile.do?fileName=...&fileUrl=...` wrapper 已被搜索索引解析为真实文档内容，但当前系统实际 bytes 捕获仍为0。因此 wrapper 只 discovery，`download_authorized=false`；nested `fileUrl` 永远不直接请求，仅对已观察 origin/path 做安全校验，其他结构/编码 traversal fail-closed。

通用 Attachment Fetcher 已将 discovery 与 download authorization 分离，并增加 magic：PDF `%PDF-`、DOCX/XLSX ZIP、DOC/XLS OLE。MIME通过但 magic不符也拒绝。

天津财政 `tj_government_procurement` 的 Registry/Adapter 已统一支持 `tjgp.cz.tj.gov.cn`、`ccgp-tianjin.gov.cn`、`www.ccgp-tianjin.gov.cn` 同一 PRIMARY Source alias，修复了此前 Registry允许而Adapter拒绝的二次校验不一致。

既有 Query Budget / Match / Daily Top5 / VERIFIED Material Event / Continuous Subscription / Notification Delivery / Latency Ledger 保持不变。

## CI

最新确认 Run `33230101416` / Job `99041292283`：`runner_id=0`、`runner_name=""`、`steps=[]`、failure。Python没有执行，因此40组tests不能标PASS，也不是 assertion failure。

## 下一步

1. 找 `TGPC-2025-A-0164` 等医疗项目精确 `downloadFile.do` wrapper，不猜 fileUrl。
2. 捕获第一份真实官方附件 bytes；通用官方附件/医疗附件分开计数。
3. 验证 `tjgpc` 原生 list class id/pagination + 天津财政原生发现。
4. Runner恢复后执行40组 tests 与 taxonomy audit。
5. deterministic evidence 后再跑 Agnes。
6. Backend API 稳定后再做 H5/微信小程序。
