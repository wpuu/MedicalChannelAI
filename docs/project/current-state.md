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
- **30 份 Schema/合同**
- **48 组 deterministic unittest 模块**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 已确认首条天津医疗附件精确官方 URL（`TGPC-2025-A-0164` / `method=downEnId`），但尚未取得 bytes/MIME/SHA
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

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

本轮新增：

- `agnes_global_lease.py`：可持久化 sliding-window start budget + in-flight TTL lease 状态机；
- `medical-agnes-global-lease-state.schema.json`；
- `medical-agnes-lease-decision.schema.json`；
- `agnes_scheduler.py`：Provider-start 公共边界，只有 `claim_next_agnes_task()` 返回 `CLAIMED + provider_start_allowed=true + agl_* lease` 才允许调用 Agnes；
- SQLite CAS 参考 Store：支持同一主机多进程共享一个 DB 文件；**不是跨服务器生产全局 Store**。

关键行为：同一 task 不能同时持有两个 active lease；全局 5 秒 spacing、12 starts/60s、2 in-flight 都在共享状态上判断；Worker 崩溃由 TTL 回收 in-flight，但已经预占的 start 仍在60秒窗口内保留，避免重启 burst。跨多 VPS 部署必须使用真正共享的原子 Store（Postgres/Redis/D1 等同等 CAS/事务语义），不能使用每台机器自己的 SQLite 或 worker-local sleep。

## 天津政府采购 / Attachment / 原生发现

天津财政首条医疗精确附件：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

状态必须区分：**精确官方 URL 已确认；真实 bytes 仍为0。** 当前执行容器对 `www.ccgp-tianjin.gov.cn / ccgp-tianjin.gov.cn / tjgpc.zwfwb.tj.gov.cn` 均 DNS resolution failure，不能据此判定官方站故障。

采购中心原生发现研究新增：

- `web_index1.do`：公开首页入口有外部研究持续佐证；
- `/webInfo/getWebInfoListForwebInfoClass.do?fkWebInfoclassId=W008`：2022–2026 多份官方采购文件持续明确称其为**网上应答帮助链接**，不是采购公告发现列表；
- 因此 W008 被显式禁止作为 `PUBLIC_TENDER_LIST / PROCUREMENT_RESULT_LIST / DISCOVERY_FEED`；真正采购公告 classId / pagination 仍待证，不猜 W00x。

Source Topology 已修正旧状态：天津财政 `direct_attachment_href_confirmed=true`，同时保持 `crawler_runtime_attachment_bytes_confirmed=false`。

## CI

GitHub Actions Runner 基础设施问题仍在；没有真实 Python step 执行证据时，48组 tests 只能标“已写入”，不能标 PASS，也不能解释为 assertion failure。

## 下一步

1. 为跨服务器 Agnes Scheduler 选择/实现共享原子 Store adapter；核心 Lease 算法不再改。
2. 继续用已确认 `downEnId` 医疗附件 URL 攻真实 bytes；不再猜下载地址。
3. 继续验证 `tjgpc` 真正采购公告 list classId / pagination 与天津财政 native discovery；W008 不再重复研究。
4. 用 Latency Ledger + Agnes queue wait 实测调优 discovery cadence 与12 RPM初始值。
5. Runner恢复后执行48组 tests/taxonomy audit；优先修真实失败。
6. deterministic execution 有证据后跑 Agnes benchmark。
7. Backend API稳定后再做H5/微信小程序。
