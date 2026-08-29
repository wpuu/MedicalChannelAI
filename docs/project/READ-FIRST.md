# MedicalChannelAI — READ FIRST

Repo `wpuu/MedicalChannelAI`; dev `dev/tianjin-pilot-v0.1`; Draft PR #1; `production_ready=false`; `merge_approved=false`.

先读 `current-state.md`、`checkpoint.json`、Schemas、Source Registry/Topology/Coverage、Identity Policy、Product Taxonomy/Classifier Registry。以 GitHub 实际状态为准。

## 硬规则

- 模型不得创造采购事实；公开事实必须可回官方 Evidence。
- 缺字段/冲突/抓取失败必须降级；DAY 精度不得伪造分钟时间。
- 客户画像可宽，限制单次执行；Subscription Prefilter 不替代完整 Match。
- `tjgp.cz.tj.gov.cn` + `ccgp-tianjin.gov.cn`(含www) = 同一个天津财政 PRIMARY Source identity。
- `tjgpc.zwfwb.tj.gov.cn` = 集采 PRIMARY 补充源，不替代全市财政源。
- 附件 discovery != download authorization；`download_authorized=false` 时网络前拒绝。
- `tjgpc downloadFile.do` nested `fileUrl` 永远不直接请求；未知 origin/port/path/编码 traversal 拒绝。
- 附件必须校验 MIME + magic（PDF `%PDF-`; DOCX/XLSX ZIP; DOC/XLS OLE）。
- 搜索索引读到附件正文 != 本系统捕获 bytes。当前官方附件 bytes=0，医疗附件 bytes=0。
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`；Agnes=`GO_FOR_BENCHMARK`；无 Runner/Python step 时不得说 tests PASS。
- 不自行 merge PR #1。

## 当前规模

- 7 P0 Source：4 IMPLEMENTED + 3 PARTIAL
- 50 VERIFIED 天津商机 corpus
- 15 Institution Evidence
- 23 Schema
- 40 deterministic test modules（未执行）
- Agnes benchmark 28 case（未执行）

## PARTIAL

- `tj_government_procurement`: 官方 alias detail；原生 list/search/pagination/附件待验证。
- `tj_government_procurement_center`: UUID detail parser + `downloadFile.do` discovery-only；医疗样本 `TGPC-2025-A-0164` 已确认正文与DOCX文件名，wrapper/bytes未确认。
- `tj_public_resource_exchange`: 当前仅采购结果页。

## CI

最新已确认 Run `33230101416` / Job `99041292283`: `runner_id=0`, `runner_name=""`, `steps=[]`。40组 tests 不能标 PASS。

## 下一步

1. 找医疗 `downloadFile.do` wrapper，不猜 fileUrl。
2. 捕获真实附件 bytes，通用/医疗分开计数。
3. 验证 `tjgpc` native list/pagination + 天津财政 native discovery。
4. Runner恢复后执行40组 tests/taxonomy audit。
5. deterministic evidence 后跑 Agnes。
6. Backend API稳定后做H5/微信小程序。
