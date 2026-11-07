# 下一轮：CCGP主链收口与唯一后续优先项（仅离线文档）

发现阶段代码fea6fc7及1202/10/3已完成离线验收；上一轮CCGP/事件/区域等成果不重复施工。下一轮只静态文档，推荐GPT-6.1 Sol xhigh，实际设置未核实。

```text
继续 MedicalChannelAI，仅离线做CCGP主链F1/F2/F3工程收口审查与唯一后续优先项决策，只改文档和新增静态验收artifact。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动及在途工作。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、ccgp-discovery-stage-budget-implementation-2026-11-07.md、ccgp-event-stage-budget-implementation-2026-11-07.md、runtime-regional-access-stop-2026-11-07.md、runtime-f2-implementation-2026-11-07.md、tjzyefy-incremental-implementation-2026-11-07.md、publish-budget-implementation-2026-11-07.md、runtime-reliability-closeout-2026-11-07.md、action-radar-acceptance-contract.md。代码fea6fc7及1202/10/3为已有结果，不重复已修问题或重跑未变测试；SDK、硬取消/原子提交/崩溃持久回执强保证CLOSED NO-GO。

静态复核最新collector_runtime.py、collector_queue.py、sync_ccgp_query.py、sync_regional_ccgp.py及直接helper/既有测试源码。更新CCGP发现→staging/watch读回→event1–6→配对提交→publish与区域/增量独立路径的实际覆盖矩阵；区分已实现且本地验证、只设计、未覆盖和真实运行未核实。

重点审查明确限流/HTTP401/403/429后是否继续同host请求、普通单项目超时分类、部分准备/写后未知/重投与pending/健康/版本/独立来源边界。最多列三项仍存在且有最新源码或既有证据的问题，不凑数；未复现只标静态缺口，不把历史来源状态当当前事实。给影响、优先级、唯一最小后续文件、行为验收和所需授权，选择唯一下一项或明确暂停。

不机械给剩余7个医院deep或7个其他增量源扩预算，不重开SDK/强保证、不新增模拟层、不把本地mock、读回匹配、配对或权威ACK当真实部署/来源恢复/完整召回/客户交付。保持原验收合同，不放宽pending、健康、版本幂等、独立来源及权限边界。

仅现有隔离分支文档及新增静态artifact。不改应用、测试、workflow、依赖锁、计划、变量、权限或保护，不导入执行应用/SDK/采集/模型/测试。不联网，不读凭据/实际环境值/运行日志，不访问云端、业务接口、真实缓存、数据库、函数或Queue。不新建环境/路由，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、静态验证及未完成项。按钮不可用时明确说明并提供完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
