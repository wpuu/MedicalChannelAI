# MedicalChannelAI — READ FIRST

## 仓库身份

- Repository: `wpuu/MedicalChannelAI`
- 主分支: `main`
- 当前开发分支: `dev/tianjin-pilot-v0.1`
- 当前阶段: `M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`
- Draft PR: `#1`
- `production_ready=false`
- `merge_approved=false`

开始工作前读取 `docs/project/current-state.md`、`docs/project/checkpoint.json`、`docs/research/schemas/`、Source Registry/Topology/Coverage、Identity Policy、Product Taxonomy/Classifier Registry。不要依赖聊天记录判断完成状态。

## 不可违反的规则

1. 模型不得创造采购事实；官方事实必须可回原始公开来源和 Evidence locator/hash。
2. 抓取失败、字段缺失、官方冲突必须降级，不得模型补全。
3. 生命周期按 VERIFIED evidence 聚合；DAY 精度不得伪造分钟级时间/latency。
4. 客户画像可以很宽，限制单次执行预算；不做 `区域 × 产品 × 数据源` 实时笛卡尔爬取。
5. 正式 Match 使用稳定 taxonomy IDs；机构类型/等级必须有官方或客户确认 provenance。
6. Subscription Prefilter 只优化性能，最终必须完整 Match；公共事件必须使用 VERIFIED Material Event Envelope。
7. Notification Delivery 必须稳定幂等；terminal follow-up 防重复骚扰；重试有上限。
8. 天津财政采购 `tjgp.cz.tj.gov.cn` 与 `ccgp-tianjin.gov.cn`（含 www）属于同一 PRIMARY Source host/alias，不重复计商机。
9. `tj_government_procurement_center` / `tjgpc.zwfwb.tj.gov.cn` 是集采 PRIMARY 补充源，不替代全市财政源；同项目按 project_number 聚合。
10. **附件发现 != 下载授权。** `download_authorized=false` 时网络前拒绝；`tjgpc downloadFile.do` nested `fileUrl` 永远不直接请求，未知 origin/port/path 拒绝。
11. 附件同时校验 MIME + magic：PDF `%PDF-`、DOCX/XLSX ZIP、DOC/XLS OLE。
12. 搜索索引读取到附件正文不等于本系统捕获 bytes。当前真实官方附件 bytes=0、医疗附件 bytes=0。
13. Coverage=`PARTIAL / NOT_EXHAUSTIVE`；Agnes=`GO_FOR_BENCHMARK`，taxonomy classifier=`BENCHMARK_PENDING`。
14. GitHub Runner 没有 Python steps 时不得写 tests PASS。
15. 不自行 merge PR #1。

## 当前真实规模

- **7个 P0 Runtime Source：4 IMPLEMENTED + 3 PARTIAL**
- 50条 VERIFIED 天津商机 corpus
- 15条 Institution Evidence
- 23份 Schema/合同
- **40组 deterministic unittest 模块，尚无执行证据**
- Agnes 两套 benchmark 共28 case，未执行

## 当前 PARTIAL Source

- `tj_government_procurement`：财政官方 host/alias 的 detail parsing；原生 list/search/pagination/附件仍待验证。
- `tj_government_procurement_center`：官方 `getWebInfoByPkWebInfoId1.do?pkWebInfoId=<UUID>` 详情 + `downloadFile.do` wrapper discovery-only。医疗样本 `TGPC-2025-A-0164` 已确认正文和 DOCX 文件名，但精确医疗 wrapper / bytes 尚未找到。
- `tj_public_resource_exchange`：当前仅政府采购结果页。

## 验证

```bash
python -m compileall -q tools/medical_pilot
python -m unittest discover -s tools/medical_pilot -p "test_*.py" -v
```

最新证据：Run `33230101416` / Job `99041292283`，`runner_id=0 / runner_name="" / steps=[]`。不得写 `PASS`。

## 下一步

1. 反查 `TGPC-2025-A-0164` 等医疗项目的精确 `downloadFile.do` wrapper URL；不得猜 fileUrl。
2. 捕获第一份真实官方附件 bytes，并将任意官方附件与医疗附件分开计数。
3. 验证 `tjgpc` 原生 list class id/pagination，同时继续天津财政 PRIMARY 原生发现研究。
4. Runner恢复后执行40组 deterministic tests 与 taxonomy corpus audit。
5. deterministic execution 有证据后运行 Agnes benchmark。
6. 后端 API 稳定后再进入 H5/微信小程序；未来通过 Skill/Fact API/MCP 接入 Hermes。
