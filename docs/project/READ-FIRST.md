# MedicalChannelAI — READ FIRST

Repo `wpuu/MedicalChannelAI`; dev `dev/tianjin-pilot-v0.1`; Draft PR #1; `production_ready=false`; `merge_approved=false`.

先读 `current-state.md`、`checkpoint.json`、Schemas、Source Registry/Topology/Coverage、Identity Policy、Product Taxonomy/Classifier Registry、`discovery_cadence.tianjin.v0.1.json`、`agnes_dispatch.v0.1.json`、`today-actions-ui-v0.1.md`。以 GitHub 实际远端状态为准。

## 硬规则

- 模型不得创造采购事实；公开事实必须可回官方 Evidence。
- 缺字段/冲突/抓取失败必须降级；DAY 精度不得伪造分钟时间。
- 客户画像可宽，限制单次执行；Subscription Prefilter 不替代完整 Match。
- Today Actions 最多5张最终卡；只有最终卡且已通过 deterministic/model admission 才能进入 Agnes。
- **浏览器只能消费 `medical-today-actions-public.schema.json`**；内部 `model_requests/model_input`、task、lease、Provider、API Key 不得下发。
- Today Actions task identity 必须绑定 `model_input_sha256`；相同 immutable input 只允许一个 terminal 模型结果；新 VERIFIED Evidence/确认画像变化产生新 hash/new task。
- `READY` 与 `MODEL_OUTPUT_REJECTED` 是 terminal result；Provider/network error 不写 terminal，可按退避重试。
- Agnes 所有生产任务必须走统一 Dispatch；禁止业务代码自行批量调用 API。
- Agnes provider start 必须先经过 `claim_next_agnes_task()`；只有 `CLAIMED + provider_start_allowed=true + agl_* lease` 才允许请求。
- Pilot 全局 Agnes 预算：<=12 starts/60s、start spacing>=5s、max in-flight=2；Source/Agnes 均使用稳定错峰 + jitter，禁止整点集体启动。
- SQLite Lease/TaskResult Store 仅是**同一主机多进程参考实现**；跨服务器必须使用共享原子 Store。
- Agnes Dispatch/Lease 只管时序和容量，**不得绕过模型/分类器 admission gate**；benchmark/bulk 优先级最低。
- Agnes HTTP route 必须显式选择官方 endpoint；不因 400/401/403/422/429 自动轮换区域/Key。
- 工作日默认 08:10 晨报；08:30–18:30 高优先级 VERIFIED 可即时；13:15上午增量；18:30后普通项目进次日晨报。
- 晚间例外只用于可行动紧迫事件；`AWARD_PUBLISHED` 晚间默认不打扰。
- Timing=SCHEDULED 不得提前创建 Provider QUEUED；到时后必须重验事件/画像/跟进状态。
- 天津财政首条医疗附件精确 URL 已确认：`TGPC-2025-A-0164 / method=downEnId`；**URL confirmed != bytes confirmed**，当前 bytes=0。
- `tjgpc ...fkWebInfoclassId=W008` 已确认是**网上应答帮助**，不得当采购公告/结果 discovery list。
- 真正 `tjgpc` procurement list classId/pagination 仍未验证，不猜 W00x。
- 附件 discovery != download authorization；必须 MIME + magic fail-closed。
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`；Agnes=`GO_FOR_BENCHMARK`；无 Runner/Python step 时不得说 tests PASS。
- 不自行 merge PR #1。

## 当前规模

- 7 P0 Source：4 IMPLEMENTED + 3 PARTIAL
- 50 VERIFIED 天津商机 corpus
- 15 Institution Evidence
- **35 Schema**
- **54 deterministic test modules（未执行）**
- Agnes benchmark 28 case（未执行）
- real official attachment bytes=0；real medical attachment bytes=0

## Today Actions 后端链

`Fact/Match/Score → Today Actions internal → model_input_sha256 → terminal result lookup → pending Agnes Dispatch → global lease → Today Actions Worker → strict Agnes client → grounded output validation → terminal result → Today Actions Public View`

关键模块：

- `today_actions.py`
- `today_actions_dispatch.py`
- `today_actions_worker.py`
- `today_actions_service.py`
- `agnes_client.py`
- `agnes_task_result.py`
- `agnes_global_lease.py`
- `agnes_scheduler.py`

旧 dispatch 重放若已有 terminal result，会在 claim lease **之前**过滤，因此不会重复调用 Agnes，也不消耗新的 provider-start slot。新 Evidence/确认画像改变 input hash 后允许生成新 task。

## H5

`docs/product/today-actions-ui-v0.1.md` 已冻结，可并行生成第一版 mock H5。首版只做 `/today` 和 `/opportunity/:id`；浏览器只使用 Public View，不复制评分、匹配、模型判断等后端逻辑。H5验证后再决定微信原生小程序。

## PARTIAL 数据源

- `tj_government_procurement`: 官方 alias detail + 精确医疗 `downEnId` URL 已确认；原生 list/search/pagination、真实附件 bytes仍待验证。
- `tj_government_procurement_center`: UUID detail parser + `downloadFile.do` discovery-only；`W008`明确不是采购列表，真正 list classId/pagination 待证。
- `tj_public_resource_exchange`: 当前仅采购结果页。

## CI

最新代码检查点 `411b7936accbb6b14333f036b3f743a4b15eb9e8` 对应 Run `33276045434` / Job `99162844003` 仍为 `runner_id=0 / steps=[]`。54组 tests 没有真实执行证据，不能标 PASS。

## 下一步

1. 可并行让 Grok 生成首版 H5 mock，严格按冻结 Public View/UI 文档。
2. 增加薄 HTTP/Serverless API adapter；内部 dispatch/worker 不暴露给浏览器。
3. Runner恢复后执行54组 tests/taxonomy audit，先修真实失败。
4. 捕获已知 `downEnId` 医疗附件真实 bytes。
5. 继续找 `tjgpc` 真正 procurement list classId/pagination；W008不再重复研究。
6. deterministic execution 有证据后跑 Agnes benchmark；再用 Latency Ledger/queue wait 调优 cadence/RPM。
7. 横向多服务器前实现共享原子 Lease/TaskResult Store；天津 Pilot 单 dispatcher + SQLite 不被该项阻塞。
