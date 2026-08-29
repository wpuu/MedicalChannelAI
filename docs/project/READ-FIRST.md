# MedicalChannelAI — READ FIRST

Repository `wpuu/MedicalChannelAI`; dev branch `dev/tianjin-pilot-v0.1`; Draft PR #1; `production_ready=false`; `merge_approved=false`.

开始工作前读取 `docs/project/current-state.md`、`docs/project/checkpoint.json`、`docs/research/schemas/`、Source Registry/Topology/Coverage、Identity Policy、Product Taxonomy/Classifier Registry。以 GitHub 实际状态为准，不依赖聊天记录。

## 硬规则

1. 模型不得创造采购事实；公开事实必须可回官方 Evidence。
2. 抓取失败/缺字段/冲突必须降级；Lifecycle 不得让未验证事件覆盖已验证状态。
3. DAY 精度不得伪造成分钟级时间或 latency。
4. 客户画像可宽，限制单次执行；不做 region×product×source 实时笛卡尔爬取。
5. 正式 Match 使用受控 taxonomy IDs；机构属性必须有官方/客户确认 provenance。
6. Subscription Prefilter 只是性能优化；公共订阅必须使用 VERIFIED Material Event，最终仍跑完整 Match。
7. 通知幂等、重试有界、terminal follow-up 防骚扰。
8. `tjgp.cz.tj.gov.cn` 与 `ccgp-tianjin.gov.cn`（含 www）属于同一 `tj_government_procurement` PRIMARY Source identity。
9. `tj_government_procurement_center` (`tjgpc.zwfwb.tj.gov.cn`) 是集采 PRIMARY 补充源，不替代全市财政源；同项目按 project_number 聚合。
10. **附件发现 != 下载授权。** `download_authorized=false` 时 Fetcher 网络前拒绝。
11. `tjgpc downloadFile.do` nested `fileUrl` 永远不直接请求；未知 origin/port/path 或编码 traversal 拒绝。
12. 附件同时校验 MIME + magic：PDF `%PDF-`、DOCX/XLSX ZIP、DOC/XLS OLE。
13. 搜索索引读取附件正文不等于本系统捕获 bytes。当前官方附件 bytes=0、医疗附件 bytes=0。
14. Coverage=`PARTIAL / NOT_EXHAUSTIVE`；Agnes=`GO_FOR_BENCHMARK` / taxonomy classifier=`BENCHMARK_PENDING`。
15. GitHub Runner 无 Python step 证据时不得说 tests PASS。
16. 不自行 merge PR #1。

## 当前规模

- **7 P0 Source：4 IMPLEMENTED + 3 PARTIAL**
- 50 VERIFIED 天津商机 corpus
- 15 Institution Evidence
- 23 Schema/合同
- **40 deterministic test modules，尚未执行**
- Agnes benchmark 28 case，未执行

## PARTIAL Sources

- `tj_government_procurement`：财政官方 host/alias detail parsing；原生 list/search/pagination/附件待验证。
- `tj_government_procurement_center`：官方 UUID detail parser + `downloadFile.do` wrapper discovery-only。医疗样本 `TGPC-2025-A-0164` 已确认设备正文及 DOCX 文件名，但医疗 wrapper/bytes 未找到。
- `tj_public_resource_exchange`：当前仅政府采购结果页。

## 验证

```bash
python -m compileall -q tools/medical_pilot
python -m unittest discover -s tools/medical_pilot -p "test_*.py" -v
```

最新已确认 CI：Run `33230101416` / Job `99041292283`，`runner_id=0 / runner_name="" / steps=[]`。不得写 PASS。

## 下一步

1. 找医疗 `downloadFile.do` wrapper，不猜 fileUrl。
2. 捕获真实附件 bytes；官方通用附件与医疗附件分开计数。
3. 验证 `tjgpc` 原生 list class id/pagination + 天津财政原生发现。
4. Runner恢复后执行40组 tests/taxonomy audit。
5. deterministic evidence 后再跑 Agnes。
6. Backend API 稳定后再做 H5/微信小程序；未来通过 Skill/Fact API/MCP 接 Hermes。
