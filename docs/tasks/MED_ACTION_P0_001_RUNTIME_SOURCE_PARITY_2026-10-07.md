# MED-ACTION-P0-001｜Vercel Incremental Runtime Source Parity

- 日期：2026-10-07
- 项目：MedicalChannelAI
- 仓库：wpuu/MedicalChannelAI
- 优先级：P0
- 类型：现有采集基础设施完整性修复，不是新产品开发
- 执行方式：Codex 隔离分支
- Production：禁止修改/禁止部署/禁止手工写入生产数据
- 前置：
  - docs/strategy/ACTION_RADAR_V0_VALIDATION_2026-10-07.md
  - docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md
  - docs/strategy/ACTION_RADAR_GAP_AUDIT_2026-10-07.md

## 1. 根因

2026-10-07 线上只读诊断确认：

- Vercel incremental collector 当天仍在运行；
- 15 分钟 tick 链正常；
- 当前 runtime 支持 tjmugh / tjnothop / teda / tjfch / tjfch_test；
- **tjzyefy / tjzyefy_intent / tjzxfc 不在 Vercel incremental source set 中**；
- 这三个源只存在于 GitHub self-hosted daily deep workflow，而对应持久化 report 停在 2026-09-27；
- 结果是官方 2026-09-28、2026-09-30 新公告没有进入生产 runtime snapshot。

已有 deep adapters 和 tests 已存在，不需要重写 parser。

## 2. 任务目标

把以下 3 个现有官方源安全接入 Vercel-native incremental execution plane：

1. `tjzyefy`
   - 天津中医药大学第二附属医院 market research
2. `tjzyefy_intent`
   - 同院 procurement intent
3. `tjzxfc`
   - 天津市中心妇产科医院 early-signal / market research

目标不是增加更多来源。
目标是让已有 verified adapters 在电脑关闭、自托管 runner 不在线时仍能获得与其他 Vercel incremental 源相同的 freshness 保证。

## 3. 必须复用的现有实现

禁止另写一套解析逻辑。

复用：

- `web/pipeline/medical_channel_pipeline/tjzyefy_discovery.py`
- `web/pipeline/medical_channel_pipeline/tjzyefy_market_research.py`
- `web/pipeline/medical_channel_pipeline/tjzyefy_intent_discovery.py`
- `web/pipeline/medical_channel_pipeline/tjzyefy_procurement_intent.py`
- `web/pipeline/medical_channel_pipeline/tjzxfc_discovery.py`
- `web/pipeline/medical_channel_pipeline/tjzxfc_market_research.py`

并保持现有：
- official host allowlist；
- index/detail identity；
- title/date consistency；
- medical-channel scope gate；
- unsupported non-medical 作为 non-fact，而不是伪造事实；
- deadline never invented；
- failed detail 不覆盖 verified canonical record；
- incremental pending barrier / fail-closed publish 规则。

## 4. 最小允许修改范围

优先只改下列 runtime/incremental 相关文件及对应 tests：

- `web/collector_runtime.py`
- `web/collector_incremental.py`
- `web/collector_incremental_runtime.py`
- `web/collector_incremental_scheduler.py`
- `web/collector_incremental_bootstrap.py`（仅在现有 generic bootstrap 无法自然支持新源时）
- `web/api/collector-status.py`（仅为 aggregate health/source 状态，不暴露详情）
- `web/pipeline/tests/test_incremental_*.py`
- 必要的新 source-parity regression tests

不要改：
- 前端 UI；
- AI prompt / decision contract；
- Customer Profile；
- ranking；
- late-window 逻辑；
- Vercel production domains；
- Secrets；
- 数据库；
- 付费/登录；
- 其他省份 collector；
- E01 或其他仓库。

如果发现必须超出以上范围，停止并报告，不自行扩大任务。

## 5. 实现要求

### 5.1 SOURCE_POLICIES

在 `web/collector_incremental.py` 为 3 个新 source_id 增加明确 policy。

建议起始值：
- tjzyefy: scan 60m / reverify 24h / max 12
- tjzyefy_intent: scan 120m / reverify 24h / max 12
- tjzxfc: scan 60m / reverify 24h / max 12

这些只是初始工程参数。
如果现有 source 页面结构/请求成本要求更保守，允许调低频率，但必须记录理由。

### 5.2 Runtime canonical state

在 `web/collector_runtime.py`：

新增独立 RuntimeCache keys 和 bootstrap：
- TJZYEFY_RECORDS_KEY
- TJZYEFY_INTENT_RECORDS_KEY
- TJZXFC_RECORDS_KEY

bootstrap 只来自 repo 已存在的：
- tianjin_live_tjzyefy_records.json
- tianjin_live_tjzyefy_intent_records.json
- tianjin_live_tjzxfc_records.json

不能把 bootstrap 文件当“当前实时事实”；只作为 runtime cache 初始 canonical base。

### 5.3 Incremental adapters

在 `web/collector_incremental_runtime.py`：

新增：
- _discover_tjzyefy
- _verify_tjzyefy
- _discover_tjzyefy_intent
- _verify_tjzyefy_intent
- _discover_tjzxfc
- _verify_tjzxfc

要求：
- discovery 使用现有官方 INDEX_URL + parser；
- bounded lookback；
- bounded max candidates；
- verification 复用现有 detail parser；
- non-medical supported exclusions 返回 None/non-fact，不能进入 canonical records；
- exception 继续走 pending barrier，不可 partial publish；
- 每个 source 用自己独立 canonical cache key，禁止把 intent/research 混成同一个 cache。

### 5.4 Scheduler parity

更新：
- `SUPPORTED_INCREMENTAL_SOURCES`
- `SCHEDULED_INCREMENTAL_SOURCES`
- `_DISCOVERY`
- `_VERIFICATION`
- `_existing_records`
- `clear_incremental_pending`

API trigger 继续继承 scheduler explicit allowlist。
禁止仅增加 policy 就自动激活 adapter。

### 5.5 Snapshot publish parity

当前 `runtime._run_publish` 只合并 ccgp/tjmugh/tjnothop/teda/tjfch/regional。

必须把：
- tjzyefy research canonical；
- tjzyefy intent canonical；
- tjzxfc canonical
加入 canonical completeness check 和 snapshot merge。

任何一个应该存在的 canonical cache 缺失时，仍 fail closed。

不能因为新增源导致：
- 未验证记录进入 snapshot；
- partial source verification 覆盖旧 verified state；
- durable readback 校验被绕过。

## 6. 必须增加的回归测试

至少覆盖：

### A. Explicit source activation
- runtime supported list 与 scheduler scheduled list 都包含 3 个新 source；
- 仍不包含未经实现的 source；
- ccgp incremental 现有边界不被意外改变。

### B. Real adapter reuse
测试必须能证明新 incremental adapter 引用了现有：
- discovery parser；
- detail parser；
- stable opportunity ID。

不要复制 parser 到 runtime。

### C. tjzyefy 9/28 正样本
使用既有 fixture，或新增最小官方 HTML fixture：

标题：
`院内调研公告（2026年23号）-肢体康复训练等医疗设备采购项目`

期望：
- discovery 识别；
- detail VERIFIED；
- registration deadline = 2026-10-09T16:00:00+08:00；
- lifecycle = MARKET_RESEARCH；
- canonical merge；
- publish snapshot 包含该机会。

### D. tjzyefy 9/30 hard negative
标题：
`天津中医药大学第二附属医院数据安全服务项目调研公告`

它是官方、有效、当前窗口开放，但不是医疗器械渠道机会。

期望：
- 不写入 canonical opportunity；
- 不进入 public snapshot；
- 保持现有 adapter 的过滤层级：若 discovery scope gate 已判定非医疗，可以直接不进入 detail；若进入 detail，则必须作为 unsupported/non-fact 拒绝；
- 不能为了满足测试而放宽现有医疗范围过滤；
- 不把正常的 non-medical 排除误算成整源 verification failure。

### E. tjzyefy procurement intent
至少一条现有 fixture：
- discovery；
- PROCUREMENT_INTENT lifecycle；
- 不发明 registration deadline；
- 独立 canonical key；
- 可进入 snapshot。

### F. tjzxfc
至少：
- 一个医疗 early-signal 正样本；
- 一个非医疗 hard negative；
- official host/title/date/deadline guard 均保持。

### G. Incremental fail-closed
新三源必须继承：
- detail failure -> staging only；
- pending barrier；
- 不 partial publish；
- retry bucket 行为；
- deep cycle lease / incremental lease 互斥。

### H. Snapshot completeness
测试确认 _run_publish：
- 缺任意新增 canonical cache -> COLLECTOR_CANONICAL_STATE_INCOMPLETE；
- 三源都存在时合并；
- duplicate identity 仍走 merge_canonical_records。

## 7. 运行时间/成本保护

不要把 3 个源塞进一个长函数连续抓几十个详情。

保留“一次 scheduler 只选一个 source”原则。

每个 source：
- discovery 一次；
- 详情只处理 planner 选中的 bounded candidates；
- 使用 existing ledger fingerprint 避免未变化详情重复抓；
- quiet scan 继续适用 backoff；
- 不能因为新增 3 个源造成 15 分钟 tick 内无限积压。

如果现有 11:30–19:00 business window 在新增 source 后无法满足“工作日每天至少扫描每源 2 次”的最低要求，先在测试/计算中报告，再提出 cadence 变更；不要直接修改 Vercel Cron。

## 8. 测试命令

先运行聚焦测试：

`cd web/pipeline && python3 -m unittest tests.test_incremental_collector_planner tests.test_incremental_collector_runtime tests.test_incremental_collector_scheduler tests.test_incremental_collector_bootstrap tests.test_incremental_bootstrap_discovery_reuse -v`

再运行现有三个 source 相关测试：
- test_tjzyefy_discovery
- test_tjzyefy_market_research
- test_tjzyefy_procurement_intent
- test_tjzyefy_intent_discovery
- test_tjzxfc_discovery
- test_tjzxfc_market_research

最后运行 pipeline 全量：
`cd web/pipeline && python3 -m unittest discover -s tests -v`

如果全量基线本来有失败：
- 先证明失败是否在修改前已存在；
- 不顺手修无关失败；
- 明确 baseline vs introduced regression。

## 9. 验收标准

只有全部满足才可报告 PASS：

1. 三源进入 Vercel incremental explicit allowlist；
2. 三源都能独立 discover/verify/cache；
3. 9/28 tjzyefy 正样本通过；
4. 9/30 数据安全 hard negative 不进入 public facts；
5. procurement intent lifecycle 不被改成 market research/bidding；
6. publish merge 包含 3 个新 canonical source；
7. fail-closed / pending barrier / lease / durable readback 语义不退化；
8. 聚焦测试通过；
9. pipeline 全量没有新增失败；
10. 没有 Production deploy；
11. 没有修改 secret / credential / domain；
12. 没有把第三方聚合数据升格成 VERIFIED。

## 10. 完成后回报格式

不要给用户看代码或大日志。

只报告：

- 任务编号：MED-ACTION-P0-001
- 分支
- 起始 commit
- 最终 commit
- 改了什么（5 行内）
- 聚焦测试：PASS/FAIL
- 全量测试：PASS/FAIL + 数量
- 9/28 正样本：PASS/FAIL
- 9/30 hard negative：PASS/FAIL
- Snapshot parity：PASS/FAIL
- 是否触碰 Production：必须 NO
- 遇到的问题
- 下一步建议

如果测试失败，停止，不部署、不合并。
