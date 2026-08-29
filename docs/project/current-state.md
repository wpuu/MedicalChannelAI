# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY + TODAY_ACTIONS_INITIAL`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- **7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION**
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **32 份 Schema/合同**
- **50 组 deterministic unittest 模块**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 已确认首条天津医疗附件精确官方 URL（`TGPC-2025-A-0164` / `method=downEnId`），但尚未取得 bytes/MIME/SHA
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## Today Actions v0.1

首页产品目标已经从“返回标讯”推进为“返回最多5条可行动商机”。已有：

- `today_actions.py` + `medical-today-actions.schema.json`；
- `today_actions_dispatch.py` + `medical-today-actions-dispatch.schema.json`；
- `today-actions-ui-v0.1.md`，首版 H5 UI 字段已冻结，可开始 mock 前端原型。

Today Actions 把以下来源严格分层：

1. `facts`：官方/已验证公开事实；
2. `evidence_source_urls`：VERIFIED Evidence 原始来源；
3. `customer_context`：客户确认的医院关系、产品能力与合作策略，明确属于 `CUSTOMER_PRIVATE_FACTS`；
4. `priority`：确定性 Business Priority，不是中标概率；
5. `decision`：Agnes 受约束的销售动作判断。

Daily 流程先完成确定性排序并截取最终 Top5，**只有最终会显示的 Top5 才允许进入 Agnes**。Normal/Wide profile 不再为了首页向 Agnes 发送最终不会展示的第6–10名候选。`model_candidate_count` 与 `model_candidate_ids` Schema 均硬限制为最多5。

Today Actions 本身不直接调用模型。没有 VERIFIED grounded facts 时保留事实卡，但状态为 `BLOCKED_GROUNDING`，不创建 Agnes 请求；Agnes 若引用未提供的 fact_id、越权 action/reason/risk 或非法 profile path，则输出标为 `MODEL_OUTPUT_REJECTED`，不得渲染给用户。

`today_actions_dispatch.py` 只接收 Today Actions 已允许的 `model_requests`，为它们建立稳定 `DAILY_TOP5_EXPLANATION` task，并继续进入现有 Agnes Dispatch / Global Lease。已得到合法模型输出的卡不会再次创建模型任务。

新增 `test_today_actions.py` 与 `test_today_actions_dispatch.py`，覆盖 Top5 模型请求上限、缺 Evidence 阻断、未验证来源隔离、客户私有关系分区、合法/非法模型输出以及 Dispatch 身份约束。**这些测试目前仅已写入，尚无 Runner 实际执行证据。**

## 首版 H5 原型

`docs/product/today-actions-ui-v0.1.md` 已标记 `FROZEN_FOR_FIRST_FRONTEND_PROTOTYPE`。首版只做天津 Pilot 的 Today Actions 和商机详情，不做全国地图大屏、支付、复杂权限或微信原生小程序。

首版前端使用 mock service，可以现在开始生成；真实 API 后续替换 service 实现。UI 必须明显区分官方事实、客户私有关系和 AI 判断；Coverage PARTIAL 时不得宣称全量覆盖。

## 采集、推送与 Agnes 错峰

探索频率、用户推送时间、Agnes API 调用时间三层分离。Source 使用稳定 minute offset + jitter；普通夜间消息静默但后台 discovery/verification/ranking 继续；所有模型任务必须走统一 Agnes Dispatch。

### Discovery Cadence v0.1

FAST / EARLY / SLOW 工作日白天基线 10 / 15 / 30 分钟。稳定相位：天津财政`:01`、天津采购中心`:04`、CCGP`:07`、总医院`:03`、一中心`:11`、采购意向`:05`、公共资源`:19`。晨报/午后强刷改为 `07:31–07:43`、`12:46–12:58` 窗口；周末降频不停，失败退避最大240分钟。

### Notification Timing / Delivery Plan

- 08:10 晨报；08:30–18:30 fully-confirmed + high-priority VERIFIED 可即时；13:15 上午增量；
- 18:30后普通项目进入次日晨报；晚间只对截止变化、终止/暂停或行动截止<=16h做有限例外；
- `SCHEDULED` 不得提前进入 Provider QUEUED；只有 `SEND_NOW` 可直接排 provider，到时还要重验 Material Event / profile / follow-up。

## Agnes Dispatch + Global Lease

模型起始预算仍为 <=12 starts/min、start spacing>=5s、max in-flight=2、task稳定0–2s jitter；优先级为交互深挖 > 紧急行动 > Daily Top5 > taxonomy > bulk > benchmark。

已有：

- `agnes_global_lease.py`：可持久化 sliding-window start budget + in-flight TTL lease 状态机；
- `medical-agnes-global-lease-state.schema.json`；
- `medical-agnes-lease-decision.schema.json`；
- `agnes_scheduler.py`：Provider-start 公共边界，只有 `claim_next_agnes_task()` 返回 `CLAIMED + provider_start_allowed=true + agl_* lease` 才允许调用 Agnes；
- SQLite CAS 参考 Store：支持同一主机多进程共享一个 DB 文件；**不是跨服务器生产全局 Store**。

关键行为：同一 task 不能同时持有两个 active lease；全局 5 秒 spacing、12 starts/60s、2 in-flight 都在共享状态上判断；Worker 崩溃由 TTL 回收 in-flight，但已经预占的 start 仍在60秒窗口内保留，避免重启 burst。天津 Pilot 可先保持单 dispatcher + SQLite；只有未来横向多服务器模型 Worker 时才必须增加共享原子 Store（Postgres/Redis/D1 等同等 CAS/事务语义）。

## 天津政府采购 / Attachment / 原生发现

天津财政首条医疗精确附件：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

状态必须区分：**精确官方 URL 已确认；真实 bytes 仍为0。** 当前执行容器对 `www.ccgp-tianjin.gov.cn / ccgp-tianjin.gov.cn / tjgpc.zwfwb.tj.gov.cn` 存在访问/DNS约束，不能据此判定官方站故障。

采购中心原生发现研究：

- `web_index1.do`：公开首页入口有外部研究持续佐证；
- `/webInfo/getWebInfoListForwebInfoClass.do?fkWebInfoclassId=W008`：2022–2026 多份官方采购文件持续明确称其为**网上应答帮助链接**，不是采购公告发现列表；
- 因此 W008 被显式禁止作为 `PUBLIC_TENDER_LIST / PROCUREMENT_RESULT_LIST / DISCOVERY_FEED`；真正采购公告 classId / pagination 仍待证，不猜 W00x。

Source Topology 已区分天津财政 `direct_attachment_href_confirmed=true` 与 `crawler_runtime_attachment_bytes_confirmed=false`。

## CI

GitHub Actions Runner 基础设施问题仍在；没有真实 Python step 执行证据时，50组 tests 只能标“已写入”，不能标 PASS，也不能解释为 assertion failure。

## 下一步

1. 允许并行生成首版 H5 mock 前端；以后只替换 TodayActionsService，不把业务判断搬进浏览器。
2. 继续把 Today Actions 接到实际 Backend API/Agnes Worker 闭环。
3. Runner恢复后执行50组 tests/taxonomy audit；优先修真实失败。
4. 继续用已确认 `downEnId` 医疗附件 URL 捕获真实 bytes；不再猜下载地址。
5. 继续验证 `tjgpc` 真正采购公告 list classId / pagination 与天津财政 native discovery；W008 不再重复研究。
6. deterministic execution 有证据后跑 Agnes benchmark，并用 Latency Ledger + Agnes queue wait 调优 cadence。
7. H5 Pilot 验证工作流后再决定微信原生小程序，不提前重复开发两套前端。
8. 横向多服务器部署前再实现共享原子 AgnesLeaseStore adapter；天津 Pilot 单 dispatcher + SQLite 不被此项阻塞。
