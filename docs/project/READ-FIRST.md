# MedicalChannelAI — READ FIRST

Repo `wpuu/MedicalChannelAI`; dev `dev/tianjin-pilot-v0.1`; Draft PR #1; `production_ready=false`; `merge_approved=false`.

先读 `current-state.md`、`checkpoint.json`、Schemas、Source Registry/Topology/Coverage、Identity Policy、Product Taxonomy/Classifier Registry、`discovery_cadence.tianjin.v0.1.json`。以 GitHub 实际状态为准。

## 硬规则

- 模型不得创造采购事实；公开事实必须可回官方 Evidence。
- 缺字段/冲突/抓取失败必须降级；DAY 精度不得伪造分钟时间。
- 客户画像可宽，限制单次执行；Subscription Prefilter 不替代完整 Match。
- **探索频率与用户推送频率分离。夜间普通消息静默，但后台 discovery/verification/ranking 继续。**
- 工作日默认 08:10 晨报；08:30–18:30 高优先级 VERIFIED 可即时；13:15 一次普通上午增量；18:30 后普通项目进次日晨报。
- 晚间例外只用于可行动紧迫事件：`DEADLINE_CHANGED`、生命周期变 `TERMINATED/SUSPENDED`、或行动截止 <=16h。`AWARD_PUBLISHED` 晚间默认不打扰。
- **Timing=SCHEDULED 不得提前创建 Provider QUEUED 记录。** 只有 `SEND_NOW` 可直接进入 Provider；Scheduled 到时后必须重新校验事件/画像/跟进状态。
- 法定节假日/调休不得硬编码猜测；Timing API 接受 official calendar override。
- `tjgp.cz.tj.gov.cn` + `ccgp-tianjin.gov.cn`(含www) = 同一个天津财政 PRIMARY Source identity。
- `tjgpc.zwfwb.tj.gov.cn` = 集采 PRIMARY 补充源，不替代全市财政源。
- 天津财政已确认医疗附件路由 `method=downEnId`；首条精确医疗附件 URL 属于 `TGPC-2025-A-0164`，但 bytes 仍未取得。
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
- **26 Schema**
- **43 deterministic test modules（未执行）**
- Agnes benchmark 28 case（未执行）

## Discovery Cadence v0.1

- FAST_PROCUREMENT：工作日白天10m、晚间15m、深夜60m；
- EARLY_SIGNAL：15m / 30m / 120m；
- SLOW_SIGNAL：30m / 60m / 120m；
- 周末降频不停；失败指数退避，最大240m；调度加约±10% jitter；07:35、12:50 强制刷新。

这些是 Pilot 初始值，未来必须用 Latency Ledger 和来源压力证据调优，不能把10分钟当永久常量。

## Delivery Plan

`Subscription Evaluation → Follow-up Route → Notification Timing → Subscription Delivery Plan → 到时后 Notification Delivery`。

`provider_queue_allowed=true` 仅限 `SEND_NOW`；`SCHEDULED` 只保存 `scheduled_for`，不得提前进入微信/Push Provider。

## PARTIAL

- `tj_government_procurement`: 官方 alias detail + 精确医疗 `downEnId` URL 已确认；原生 list/search/pagination、真实附件 bytes仍待验证。
- `tj_government_procurement_center`: UUID detail parser + `downloadFile.do` discovery-only；医疗样本 `TGPC-2025-A-0164` 已确认正文与DOCX文件名。
- `tj_public_resource_exchange`: 当前仅采购结果页。

## CI

GitHub Actions Runner 基础设施问题持续；43组 tests 无真实执行证据，不能标 PASS。

## 下一步

1. 用已确认 `downEnId` 医疗附件 URL 捕获真实 bytes，不再猜下载地址。
2. 验证 `tjgpc` native list/pagination + 天津财政 native discovery。
3. 将 discovery cadence + scheduled delivery execution 接入持久化 scheduler，并用 Latency Ledger 反推最佳频率。
4. Runner恢复后执行43组 tests/taxonomy audit。
5. deterministic evidence 后跑 Agnes。
6. Backend API稳定后做H5/微信小程序。
