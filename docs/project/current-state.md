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
- **25 份 Schema/合同**
- **42 组 deterministic unittest 模块**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 已确认首条天津医疗附件精确官方 URL（`TGPC-2025-A-0164` / `method=downEnId`），但尚未取得 bytes/MIME/SHA
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## 采集与推送时间策略

**探索频率与用户推送频率彻底解耦。** 夜间不推普通消息，不代表夜间停止抓取、验证或排序。

新增：

- `tools/medical_pilot/discovery_cadence.tianjin.v0.1.json`
- `tools/medical_pilot/discovery_cadence.py`
- `tools/medical_pilot/notification_time_policy.py`
- `medical-discovery-cadence-decision.schema.json`
- `medical-notification-time-decision.schema.json`

### Discovery Cadence v0.1

来源分三组：

- `FAST_PROCUREMENT`：天津财政 PRIMARY、天津采购中心、CCGP 正式公告镜像；
- `EARLY_SIGNAL`：总医院、一中心医院早期信号；
- `SLOW_SIGNAL`：采购意向、公共资源结果镜像。

工作日默认：

- 00:00–06:30：60 / 120 / 120 分钟；
- 06:30–18:30：10 / 15 / 30 分钟；
- 18:30–22:30：15 / 30 / 60 分钟；
- 22:30–24:00：60 / 120 / 120 分钟。

周末降频但不停；失败使用指数退避，最大 240 分钟；成功后恢复；调度器应加约 ±10% jitter。07:35 和 12:50 设强制刷新点，为晨报和午后增量准备最新 VERIFIED 数据。

### Notification Timing v0.1

默认中国业务时区 `Asia/Shanghai`：

- 08:10：晨间主推，包含前夜和清晨已经处理完的新增/变化；
- 08:30–18:30：fully-confirmed + high-priority 的 VERIFIED 事件可即时推；
- 13:15：普通上午新增进入一次当日增量摘要，避免所有非即时项目都拖到明天；
- 18:30–21:30：普通项目静默进入次日晨报；只有 `DEADLINE_CHANGED`、生命周期变为 `TERMINATED/SUSPENDED`，或行动截止剩余 <=16 小时，才允许有限晚间例外；
- 21:30后：默认不打扰，继续后台抓取/验证/排序，次日 08:10 推；
- 周末普通高优先级默认排到下一工作日晨报；仅白天的真正紧急事件允许例外。

`AWARD_PUBLISHED` 即使分数高，晚间默认仍进入次日晨报，因为通常没有当晚必须执行的动作。

中国法定节假日不在代码里硬编码具体日期；Timing API 接受 `holiday_dates / forced_workdays`，以后由年度官方工作日历提供，避免把调休周末误判为休息日。

## 天津政府采购 / Attachment

新增 `tj_government_procurement_center`（`tjgpc.zwfwb.tj.gov.cn`）作为 `PRIMARY_SOURCE / PARTIAL_IMPLEMENTATION` 集采补充源。已实现 UUID detail route 解析。

天津财政体系已确认首条医疗采购精确附件 URL：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

因此天津附件当前至少观察到两套官方机制：

1. 财政政府采购 `method=downEnId`；
2. 采购中心 `downloadFile.do?fileName=...&fileUrl=...` wrapper。

两者都仍处于 discovery-only / bytes-unverified。当前执行环境无法直连取得真实附件 bytes，因此不能宣称真实 DOCX/PDF parser 已验证。

Attachment Fetcher 已将 discovery 与 download authorization 分离，并增加 magic 校验：PDF `%PDF-`、DOCX/XLSX ZIP、DOC/XLS OLE。MIME通过但 magic不符也拒绝。

## 既有核心链

Query Budget / Match / Daily Top5 / VERIFIED Material Event / Continuous Subscription / Notification Delivery / Latency Ledger 保持。新的 Timing Policy 位于 Subscription Notification 与 Delivery 之间：先决定是否通知，再决定现在发还是延后到固定业务窗口。

## CI

GitHub Actions Runner 基础设施问题仍在；没有真实 Python step 执行证据时，42组 tests 只能标“已写入”，不能标 PASS，也不能解释为 assertion failure。

## 下一步

1. 继续用已确认的 `method=downEnId` 医疗附件 URL 攻真实 bytes；不再猜下载地址。
2. 继续验证 `tjgpc` 原生 list class id/pagination + 天津财政原生发现。
3. 将 Discovery Cadence 与 Notification Timing 接入后续持久化 scheduler；用 Latency Ledger 真实数据调优 10/15/30 分钟初始频率。
4. Runner恢复后执行42组 tests 与 taxonomy audit。
5. deterministic evidence 后再跑 Agnes。
6. Backend API 稳定后再做 H5/微信小程序。
