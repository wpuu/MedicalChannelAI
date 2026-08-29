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
- **28 份 Schema/合同**
- **45 组 deterministic unittest 模块**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 已确认首条天津医疗附件精确官方 URL（`TGPC-2025-A-0164` / `method=downEnId`），但尚未取得 bytes/MIME/SHA
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## 采集、推送与 Agnes 错峰

**探索频率、用户推送时间、Agnes API 调用时间三层分离。** 夜间普通消息静默，但 discovery/verification/ranking 继续；模型任务必须进入统一 Agnes Dispatch，不允许业务接口自己批量直呼 API。

### Discovery Cadence v0.1

FAST / EARLY / SLOW 工作日白天基线仍为 10 / 15 / 30 分钟，晚间降频，深夜继续低频抓取。新增稳定 Source 相位：

- `tj_government_procurement`: `:01`
- `tj_government_procurement_center`: `:04`
- `ccgp_local_notices`: `:07`
- `tjmugh_procurement`: `:03`
- `tj_first_central_hospital_procurement`: `:11`
- `ccgp_procurement_intent`: `:05`
- `tj_public_resource_exchange`: `:19`

因此不会再让一组 Source 同时从 `:00/:10/:20` 启动。原 07:35 / 12:50 单点强制刷新已改为 `07:31–07:43`、`12:46–12:58` 刷新窗口，scheduler 必须把 Source 分散在窗口内。仍保留约 ±10% jitter、失败指数退避至最大240分钟、周末降频不停。

### Notification Timing / Delivery Plan

- 08:10 晨报；
- 08:30–18:30 fully-confirmed + high-priority VERIFIED 可即时；
- 13:15 一次普通上午增量；
- 18:30后普通项目进入次日晨报；
- 18:30–21:30 仅 DEADLINE_CHANGED、生命周期变 TERMINATED/SUSPENDED、或行动截止<=16h 允许有限晚间例外；
- `AWARD_PUBLISHED` 晚间默认不打扰。

`SCHEDULED` 不得提前进入 Provider QUEUED；只有 `SEND_NOW` 允许 `provider_queue_allowed=true`。到时后 scheduler 必须重验 Material Event / profile / follow-up。

### Agnes Dispatch v0.1

新增 `agnes_dispatch.v0.1.json`、`agnes_dispatch.py`、`medical-agnes-dispatch-plan.schema.json`、`daily_model_dispatch.py` 和 Daily wrapper Schema。

Pilot 初始模型预算：

- 最大 **12 次请求启动/分钟**；
- 请求启动至少相隔 **5秒**；
- 最多 **2个 in-flight**；
- task_id 生成稳定 0–2 秒附加 jitter；
- 每个 Provider start 在多 Worker 环境必须取得**持久化 global lease/token bucket**；worker-local sleep 不能替代全局限流；
- 429 采用较长指数退避，5xx 使用较短指数退避，二者均带稳定 jitter；
- 优先级：交互式深挖 > 紧急行动解释 > Daily Top5 > taxonomy 分类 > bulk enrichment > benchmark；
- 调度器永远不能绕过模型/分类器 admission gate。

Daily Top5 的 `model_candidate_ids` 已接入统一 Agnes Dispatch；业务层不能再 `for candidate: call Agnes()`。两套 benchmark 默认 RPM 也从18降到12，并禁止通过参数超过12 RPM。

## 天津政府采购 / Attachment

天津财政体系已确认首条医疗采购精确附件 URL：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

当前至少观察到财政 `method=downEnId` 与采购中心 `downloadFile.do?...` 两套官方附件机制。两者仍 discovery-only / bytes-unverified。Attachment Fetcher 保持 download authorization + MIME + magic fail-closed。

## CI

GitHub Actions Runner 基础设施问题仍在；没有真实 Python step 执行证据时，45组 tests 只能标“已写入”，不能标 PASS，也不能解释为 assertion failure。

## 下一步

1. 把 Agnes Dispatch 的 global lease/token bucket 接入持久化 scheduler，而不是仅有纯计划器。
2. 继续用已确认 `downEnId` 医疗附件 URL 攻真实 bytes。
3. 验证 `tjgpc` native list/pagination + 天津财政 native discovery。
4. 用 Latency Ledger + Agnes队列等待时间实测调优 10/15/30 分钟与 12 RPM 初始值。
5. Runner恢复后执行45组 tests/taxonomy audit。
6. deterministic evidence 后跑 Agnes benchmark。
7. Backend API稳定后再做H5/微信小程序。
