# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY + TODAY_ACTIONS_TRUSTED_BACKEND`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- **7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION**
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **35 份 Schema/合同**
- **54 组 deterministic unittest 模块**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 首条天津医疗附件精确官方 URL 已确认：`TGPC-2025-A-0164 / method=downEnId`，但 bytes/MIME/SHA 尚未取得
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## Today Actions：已从合同推进到可信后端闭环

首版 H5 UI 仍为 `FROZEN_FOR_FIRST_FRONTEND_PROTOTYPE`，但浏览器边界已进一步收紧：

- 内部 `medical-today-actions.schema.json` 可以包含 `model_requests/model_input`；
- 浏览器只允许消费 `medical-today-actions-public.schema.json`；
- Public View 不下发 `model_requests`、model input、task id、lease id、Provider、API Key 或上游地址；
- H5 仍只展示官方事实、Evidence、客户私有上下文、Priority 与已验证 AI Decision。

新增可信后端链：

`Fact/Match/Score → Today Actions internal → model input SHA-256 → terminal result reuse → Agnes Dispatch → global lease → Worker → grounded output validation → terminal result → Today Actions Public View`

### Model input 身份与幂等

`today_actions_dispatch.py` 已将 task identity 绑定到当前 immutable model input：

`today|profile_id|local_day|opportunity_id|<model_input_sha256前24位>`

完整 `model_input_sha256` 同时保存在 task payload。行为：

- 同一客户/商机/日期 + 完全相同 facts/profile context → 同一个 task；
- 新增 VERIFIED Evidence 或已确认客户条件变化 → input hash 变化 → 新 task，可重新分析；
- payload hash 与 task id 不一致时，在申请模型前 fail-closed。

### Terminal result store

新增 `agnes_task_result.py` + `medical-agnes-task-terminal-result.schema.json`：

- 仅 `READY` 与 `MODEL_OUTPUT_REJECTED` 是 immutable terminal result；
- terminal result 必须同时绑定 `task_id + opportunity_id + model_input_sha256`；
- 同 task 使用原子 `put_if_absent`，成功后旧 dispatch 重放不会再烧 Agnes；
- Provider/network error 不写 terminal，允许按退避策略重试；
- SQLite result store 是同机多进程参考实现；跨服务器仍需共享数据库唯一约束。

### Today Actions Worker

新增 `today_actions_worker.py` + `medical-today-actions-worker-result.schema.json`：

- 先过滤已有 terminal task，**过滤发生在 global lease claim 前**，因此重复旧 dispatch 不消耗12 RPM/start slot；
- 再通过 `claim_next_agnes_task()` 获取 `agl_*` lease；
- provider 调用前再次核验 task/hash/model input；
- 模型输出必须经过现有 `validate_model_decision()`；越权 action/reason/risk、引用未提供 fact_id 等全部拒绝；
- Provider error、模型输出拒绝、正常 READY 等路径都会按规则释放 lease；
- 同一 immutable input 第二次执行返回 `ALREADY_COMPLETED`，不再次调用模型。

### Agnes HTTP adapter

新增 `agnes_client.py`：

- 默认官方国际主线路 `https://apihub.agnes-ai.com/v1`；
- 仅允许官方 `apihub.agnes-ai.com / apihub.agnes-ai.cn / api.agnes-ai.cn` 三个 HTTPS `/v1` endpoint；
- Today Actions v0.1 固定 `agnes-2.5-flash` + `POST /chat/completions`；
- API Key 仅通过部署时构造参数/环境传入，不进入 repo、返回值或 Public View；
- 不因 400/401/403/422/429 自动切换区域线路；
- JSON必须是单一精确对象，不静默去除 markdown fence；
- 429/5xx/network 等保留错误分类供后续 retry/backoff 使用。

### Backend service assembly

新增 `today_actions_service.py`：

- 首次生成 current model input fingerprint；
- 只复用**当前 hash 精确匹配**的 READY/REJECTED terminal result；
- READY 会再次通过 Today Actions 的 deterministic/grounded validation 后渲染；
- REJECTED immutable output 保持 `MODEL_OUTPUT_REJECTED`，不会每次刷新页面重新调用模型；
- 新 Evidence 导致 hash 变化时旧 terminal 自动失效，新 task 进入内部 dispatch；
- Public response 自动去掉 `model_requests`，内部 dispatch 只留服务器。

## 采集、推送与 Agnes 错峰

探索频率、用户推送时间、Agnes API 调用时间继续三层分离。

Source 稳定相位：天津财政`:01`、天津采购中心`:04`、CCGP`:07`、总医院`:03`、一中心`:11`、采购意向`:05`、公共资源`:19`。晨报/午后强刷为 `07:31–07:43`、`12:46–12:58` 窗口；仍有 jitter、失败退避、周末降频不停。

通知：08:10晨报；08:30–18:30高优先级 VERIFIED 可即时；13:15上午增量；18:30后普通项目次日晨报；晚间仅截止变化、终止/暂停或行动截止<=16h等真正紧急事件例外。

Agnes Pilot：<=12 starts/60s、start spacing>=5s、max in-flight=2、task稳定0–2s jitter；交互深挖 > 紧急行动 > Daily Top5 > taxonomy > bulk > benchmark。

`agnes_global_lease.py + agnes_scheduler.py` 已提供持久化 global lease 状态机和 Provider-start 公共边界。SQLite Lease Store 仅用于同一主机多进程参考；跨服务器必须换共享原子 Store。

## 天津政府采购 / Attachment / 原生发现

天津财政首条医疗精确附件：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

必须继续区分：**URL confirmed != bytes confirmed**。当前 real medical attachment bytes=0。

采购中心：

- `web_index1.do` 仅作为公开首页入口线索；
- `/webInfo/getWebInfoListForwebInfoClass.do?fkWebInfoclassId=W008` 已确认是**网上应答帮助**，明确禁止当采购 discovery；
- 真正 `PUBLIC_TENDER_LIST / PROCUREMENT_RESULT_LIST` classId 与 pagination 仍未可靠验证，不猜 W00x；
- 2025–2026 UUID detail 页面仍稳定可由公开索引发现。

## CI

最新代码检查点 `411b7936accbb6b14333f036b3f743a4b15eb9e8` 对应 Run `33276045434` / Job `99162844003` 仍为 `runner_id=0 / steps=[]`。因此 **54组 tests 都只能标“已写入”，不能标 PASS，也不能解释为 assertion failure。**

## 下一步

1. 允许并行生成首版 H5 mock；前端严格使用 Public View，不复制业务判断。
2. 为真实部署增加薄 HTTP/Serverless API adapter，把 `TodayActionsServiceCycle.public_response()` 暴露给 `/today`，内部 dispatch/worker 不外泄。
3. Runner恢复后立即执行54组 tests/taxonomy audit，先修真实失败。
4. 继续捕获已知 `downEnId` 医疗附件真实 bytes。
5. 继续验证 `tjgpc` 真正采购公告 list classId/pagination 与天津财政 native discovery；W008 不再研究。
6. deterministic execution 有证据后运行 Agnes benchmark；使用 Latency Ledger / queue wait 调优 cadence 与12RPM。
7. H5 Pilot 验证工作流后再决定微信原生小程序。
8. 横向多服务器部署前实现共享原子 AgnesLeaseStore / AgnesTaskResultStore adapter；天津 Pilot 单 dispatcher + SQLite 可先运行。
