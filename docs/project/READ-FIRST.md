# MedicalChannelAI — READ FIRST

Repo `wpuu/MedicalChannelAI`; dev `dev/tianjin-pilot-v0.1`; Draft PR #1; `production_ready=false`; `merge_approved=false`.

先读 `current-state.md`、`checkpoint.json`、Schemas、Source Registry/Topology/Coverage、Identity Policy、Product Taxonomy/Classifier Registry、`discovery_cadence.tianjin.v0.1.json`、`agnes_dispatch.v0.1.json`。以 GitHub 实际状态为准。

## 硬规则

- 模型不得创造采购事实；公开事实必须可回官方 Evidence。
- 缺字段/冲突/抓取失败必须降级；DAY 精度不得伪造分钟时间。
- 客户画像可宽，限制单次执行；Subscription Prefilter 不替代完整 Match。
- 探索频率、用户推送时间、Agnes API 调用时间三层分离。
- Source 不得都在整点/整10分钟同时启动；按 `source_minute_offsets` 使用稳定相位，并在刷新窗口内分散执行。
- Agnes 所有生产任务必须走统一 Dispatch；禁止业务代码直接批量循环调用 API。
- Pilot Agnes 启动预算：<=12 starts/min、start spacing>=5s、max in-flight=2、稳定0–2s jitter；多 Worker 必须通过持久化 global lease/token bucket。
- Agnes Dispatch 只管时序和容量，**不得绕过模型/分类器 admission gate**；benchmark/bulk 优先级最低。
- 工作日默认 08:10 晨报；08:30–18:30 高优先级 VERIFIED 可即时；13:15 一次普通上午增量；18:30 后普通项目进次日晨报。
- 晚间例外只用于可行动紧迫事件：`DEADLINE_CHANGED`、生命周期变 `TERMINATED/SUSPENDED`、或行动截止 <=16h。`AWARD_PUBLISHED` 晚间默认不打扰。
- Timing=SCHEDULED 不得提前创建 Provider QUEUED；到时后必须重新校验事件/画像/跟进状态。
- 天津财政已确认医疗附件路由 `method=downEnId`；首条精确医疗附件 URL 属于 `TGPC-2025-A-0164`，但 bytes 仍未取得。
- 附件 discovery != download authorization；必须 MIME + magic fail-closed。
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`；Agnes=`GO_FOR_BENCHMARK`；无 Runner/Python step 时不得说 tests PASS。
- 不自行 merge PR #1。

## 当前规模

- 7 P0 Source：4 IMPLEMENTED + 3 PARTIAL
- 50 VERIFIED 天津商机 corpus
- 15 Institution Evidence
- **28 Schema**
- **45 deterministic test modules（未执行）**
- Agnes benchmark 28 case（未执行）

## Discovery Cadence v0.1

FAST / EARLY / SLOW 工作日白天基线 10m / 15m / 30m。FAST source 当前稳定相位：天津财政`:01`、天津采购中心`:04`、CCGP`:07`。医院/慢源也有独立 offset。晨报/午后刷新使用 `07:31-07:43`、`12:46-12:58` 窗口，不使用一个共享整点。周末降频不停；失败指数退避最大240m；仍加约±10% jitter。

## Agnes Dispatch v0.1

`Daily Recommendation → model-authorized candidates → Daily Model Dispatch → generic Agnes Dispatch Plan → persistent lease/token bucket（待接）→ API`。

默认优先级：交互式深挖 > 紧急行动解释 > Daily Top5 > taxonomy > bulk > benchmark。两套 benchmark 默认 RPM 已降为12，且不允许参数超过12。

## PARTIAL

- `tj_government_procurement`: 官方 alias detail + 精确医疗 `downEnId` URL 已确认；原生 list/search/pagination、真实附件 bytes仍待验证。
- `tj_government_procurement_center`: UUID detail parser + `downloadFile.do` discovery-only。
- `tj_public_resource_exchange`: 当前仅采购结果页。

## CI

GitHub Actions Runner 基础设施问题持续；45组 tests 无真实执行证据，不能标 PASS。

## 下一步

1. 持久化 Agnes global lease/token bucket 接入 scheduler。
2. 用已确认 `downEnId` 医疗附件 URL 捕获真实 bytes。
3. 验证 `tjgpc` native list/pagination + 天津财政 native discovery。
4. Runner恢复后执行45组 tests/taxonomy audit。
5. 用 Latency Ledger/queue wait 调优 cadence 与 Agnes 12RPM 初始值。
6. deterministic evidence 后跑 Agnes。
7. Backend API稳定后做H5/微信小程序。
