# 下一轮：CCGP发现/事实阶段预算与staging/watch保存合同（仅离线文档）

事件代码5d2fe85及1181/10/3已完成本地验收。下一轮只静态审查未覆盖前置阶段，不重复事件、区域、CLI、增量或publish施工。推荐GPT-6.1 Sol xhigh，实际设置未核实。

```text
继续 MedicalChannelAI，仅离线制定ccgp发现/事实阶段时间预算与staging/watch保存合同及唯一最小实现方案，只改文档和新增静态验收artifact。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动及在途工作。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、ccgp-event-stage-budget-implementation-2026-11-07.md、ccgp-event-stage-budget-contract-2026-11-07.md、runtime-regional-access-stop-2026-11-07.md、action-radar-acceptance-contract.md。代码5d2fe85及1181/10/3为已有结果，不重复已修问题或重跑未变测试；SDK及强保证分支保持CLOSED NO-GO。

只读审查 web/collector_runtime.py 的_run_ccgp及事件/配对消费边界、collector_queue.py、pipeline/scripts/sync_ccgp_query.py、sync_tianjin_plan.py、实际搜索/详情/pending/state helper、tianjin_query_plan.json和相关既有测试源码。追踪Queue预检、五关键词/两类型发现、去重/选择12详情、sleep/错误、完整性及watch容量、cycle staging与watch两次保存、状态/健康/事件推进；区分准备完成与配对canonical及公开提交。

形成一套有依据的工作/双键准备/尾部预算、复用现有CliBudget接口、超期结果拒绝和恢复规则。保存顺序须保留既有源事务：只准备staging/watch，不提前提交records/events对；任何部分发现或详情失败不冒充完整，旧committed、未解决pending、兄弟staging、成功时钟和独立来源保留。区分写前拒绝、首键已写、第二键未知、写后迟到及stage/健康/Queue尾部未知，不称跨键原子事务、零写、自动回滚或可靠持久化。不照搬事件180/区域210/CLI900或平台maxDuration，不实现共享冷却或Retry-After。

验收：引用最新源码行号/哈希，区分已有保护、设计缺口、运行事实未核实及GO/NO-GO；给唯一最小修改文件与后续行为验收，不直接改代码。不得改变Queue/lease/健康/pending/版本/配对提交协议，不用future冒称取消。必须改变禁止协议才能安全完成时明确NO-GO结束，不追加模拟层或多轮补证。

仅现有隔离分支文档及新增静态artifact。不改应用、测试、workflow、依赖锁、计划、变量、权限或保护，不导入执行应用/SDK/采集/模型/测试，不新增模拟器。不联网，不读凭据/实际环境值/运行日志，不访问云端、业务接口、真实缓存、数据库、函数或Queue。不新建环境/路由，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据及下一轮完整任务，报告实际完成、静态验证及未完成项。按钮不可用时明确说明并提供完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
