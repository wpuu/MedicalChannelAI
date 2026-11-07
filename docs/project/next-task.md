# 下一轮：Queue CCGP单次stage明确拒绝止损R1（待明确四文件授权）

收口文档6aaaa66已完成，本轮重复指令仅复核并确认无新变化；后续先核对真实HEAD和本次checkpoint，不重复同一审查。应用仍fea6fc7，1202/10/3为既有结果。本提示词在用户明确提交后才授权四文件代码，不由当前文档授权自动扩展。最新文档提交以HEAD/checkpoint核对。推荐GPT-6.1 Sol xhigh，实际设置未核实。

```text
继续 MedicalChannelAI。我明确授权仅在现有隔离分支，离线复现并最小修复Queue CCGP发现/事实及event1–event6共用路径的单次stage明确拒绝止损R1，并保持安全诊断；不实现跨进程冷却或Retry-After。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动及在途工作。当前应用代码fea6fc7，最新成果以真实HEAD及checkpoint为准。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、ccgp-mainline-reliability-closeout-2026-11-07.md、ccgp-discovery-stage-budget-implementation-2026-11-07.md、ccgp-event-stage-budget-implementation-2026-11-07.md、runtime-regional-access-stop-2026-11-07.md、action-radar-acceptance-contract.md。1202/10/3是已有通过结果，不重复区域/CLI/预算/回执修复；SDK及强保证保持CLOSED NO-GO。

只修改四个既有文件，另更新文档和新增artifact：
web/collector_runtime.py
web/pipeline/scripts/sync_ccgp_query.py
web/pipeline/tests/test_runtime_source_parity_behavior.py
web/pipeline/tests/test_ccgp_events.py

先用既有runtime/helper入口、MemoryCache/transport桩、冻结样本、假时钟和临时目录复现明确拒绝后继续同host请求；阻断外网和真实SDK。若已修或不能复现，给证据关闭，不凑修复。

仅Queue ccgp及event1–6显式启用单次stage的host拒绝集合，复用access_block_reason、RATE_LIMIT_MARKERS和failure_row/failure_summary；helper只增加可选参数，反向区域依赖必须函数内延迟取得，避免循环导入。发现跨关键词、事件同片跨项目共享stage内范围，不跨stage、重试、进程或部署共享。

HTTP401/403/429、限流HTML及包装cause明确拒绝后，同实际URL hostname后续业务请求0。搜索/www/裸域不合并；另一合法详情host可独立核验，但不完整stage不得提交。搜索拒绝可立即拒绝不完整stage；不影响其他独立来源。普通及时超时、网络错误、503和解析错误不得误封全host，原及时普通事件fallback保持；拒绝或跳过详情不得制造新核验/fallback。

CCGP事实失败改用固定原因、阶段计数和最多5个哈希，移除拼接原异常正文；不把URL、标题、项目号、查询或秘密写入workflow诊断。保持既有事件/区域安全诊断，不改共享分类器或HTTP helper。

保留270/150/60/60发现预算、270/180/30/60事件预算及原点、seed初始化披露、committed优先、双键准备读回/部分未知、完整片/单键配对、pending、成功时钟、首次重试与最终降级、owner/lease和独立调度。无guard/CLI默认路径保持，不调整预算、Queue或健康协议，不宣称零写、回滚、硬取消或真实持久化。

验收覆盖两个查询类型、两个关键词/同host详情、同片两个项目、event1/event6、401/403/429/cause/marker、不同host与普通错误反例、下一次stage重试、完整成功和合法空、无guard兼容、两种导入顺序及诊断无原文。保留旧canonical/pending/兄弟staging/成功时钟及写后未知回执，运行必要离线Python回归和10/3，按实际结果记录新增数量。需要扩四文件或修改禁止协议则给证据NO-GO，不另建模拟层。

仅现有隔离分支上述离线代码/测试、文档和新增artifact。不联网、不安装执行真实SDK、不读凭据/实际环境值/运行日志，不访问云端、业务接口、真实缓存、数据库、函数、Queue或模型。不新建环境/路由，不改其他应用文件、依赖锁、workflow、计划、变量、权限或保护，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告复现、修改、实际验证及未完成项。按钮不可用时明确说明并提供完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
