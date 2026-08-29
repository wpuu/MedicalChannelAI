# MedicalChannelAI — READ FIRST

Repo `wpuu/MedicalChannelAI`; dev `dev/tianjin-pilot-v0.1`; Draft PR #1; `production_ready=false`; `merge_approved=false`.

先读 `current-state.md`、`checkpoint.json`、Schemas、Source Registry/Topology/Coverage、Identity Policy、Product Taxonomy/Classifier Registry、`discovery_cadence.tianjin.v0.1.json`、`agnes_dispatch.v0.1.json`、`tjgpc_native_discovery_research.v0.1.json`。以 GitHub 实际状态为准。

## 硬规则

- 模型不得创造采购事实；公开事实必须可回官方 Evidence。
- 缺字段/冲突/抓取失败必须降级；DAY 精度不得伪造分钟时间。
- 客户画像可宽，限制单次执行；Subscription Prefilter 不替代完整 Match。
- 探索频率、用户推送时间、Agnes API 调用时间三层分离；Source 使用稳定 minute offset + jitter，禁止整点集体启动。
- Agnes 所有生产任务必须走统一 Dispatch；禁止业务代码自行 `for candidate: call Agnes()`。
- Agnes provider start 必须先经过 `claim_next_agnes_task()`；只有 `CLAIMED + provider_start_allowed=true + agl_* lease` 才能发请求。
- Pilot Agnes 全局预算：<=12 starts/60s、start spacing>=5s、max in-flight=2；状态由持久化 global lease store 统一裁决。
- SQLite Lease Store 仅是**同一主机多进程参考实现**；跨服务器必须使用共享原子 Store，不能每台 VPS 各用 SQLite。
- Agnes Dispatch/Lease 只管时序和容量，**不得绕过模型/分类器 admission gate**；benchmark/bulk 优先级最低。
- 工作日默认 08:10 晨报；08:30–18:30 高优先级 VERIFIED 可即时；13:15 一次上午增量；18:30 后普通项目进次日晨报。
- 晚间例外只用于可行动紧迫事件：`DEADLINE_CHANGED`、生命周期变 `TERMINATED/SUSPENDED`、或行动截止 <=16h。`AWARD_PUBLISHED` 晚间默认不打扰。
- Timing=SCHEDULED 不得提前创建 Provider QUEUED；到时后必须重验事件/画像/跟进状态。
- 天津财政首条医疗附件精确 URL 已确认：`TGPC-2025-A-0164 / method=downEnId`；**URL confirmed != bytes confirmed**，当前 bytes=0。
- `tjgpc /webInfo/getWebInfoListForwebInfoClass.do?fkWebInfoclassId=W008` 已确认是**网上应答帮助**，不得当作采购公告/结果 discovery list。
- `tjgpc web_index1.do` 只记录为首页入口研究线索；真正采购公告 list classId/pagination 仍未验证，不猜 W00x。
- 附件 discovery != download authorization；必须 MIME + magic fail-closed。
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`；Agnes=`GO_FOR_BENCHMARK`；无 Runner/Python step 时不得说 tests PASS。
- 不自行 merge PR #1。

## 当前规模

- 7 P0 Source：4 IMPLEMENTED + 3 PARTIAL
- 50 VERIFIED 天津商机 corpus
- 15 Institution Evidence
- **30 Schema**
- **48 deterministic test modules（未执行）**
- Agnes benchmark 28 case（未执行）
- real official attachment bytes=0；real medical attachment bytes=0

## Agnes 全局调度边界

`Daily/DeepDive/Taxonomy task → Agnes Dispatch Plan → claim_next_agnes_task → persistent global lease → provider API → release lease`。

Lease 获取即预占一次 provider start；同 task 不能重复 active lease；崩溃由 TTL 回收 in-flight，但 start history 保留60秒。SQLite CAS 可用于 Pilot 单机/多进程；跨节点生产 Store 仍待选择/实现。

## PARTIAL 数据源

- `tj_government_procurement`: 官方 alias detail + 精确医疗 `downEnId` URL 已确认；原生 list/search/pagination、真实附件 bytes仍待验证。
- `tj_government_procurement_center`: UUID detail parser + `downloadFile.do` discovery-only；`W008`明确不是采购列表，真正 list classId/pagination 待证。
- `tj_public_resource_exchange`: 当前仅采购结果页。

## CI

GitHub Actions Runner 基础设施问题持续；48组 tests 尚无真实 Python step 执行证据，不能标 PASS。

## 下一步

1. 跨服务器部署前，为 Agnes Lease Store 实现共享原子 adapter；Pilot 可先单 dispatcher + SQLite。
2. 用已确认 `downEnId` 医疗附件 URL 捕获真实 bytes，不再猜下载地址。
3. 继续找 `tjgpc` 真正 procurement list classId/pagination；W008 不再重复研究。
4. Runner恢复后执行48组 tests/taxonomy audit。
5. 用 Latency Ledger/Agnes queue wait 调优 cadence 与12RPM初始值。
6. deterministic execution 有证据后跑 Agnes。
7. Backend API稳定后做H5/微信小程序。
