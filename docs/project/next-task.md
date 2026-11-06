# 下一轮：增量tjzyefy时间预算与pending恢复合同（仅文档）

不重复区域/CLI/CI修复，不执行runtime、SDK或测试。推荐GPT-6.1 Sol xhigh（超高），实际运行设置未核实。

```text
继续MedicalChannelAI，仅离线制定增量源tjzyefy的时间预算与pending恢复合同及唯一最小实现方案，只改文档和新增验收artifact。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动和在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、runtime-f2-implementation-2026-11-07.md、runtime-f2-stage-budget-contract-2026-11-07.md、action-radar-acceptance-contract.md。区域预算代码bba3716及1098/10/3已完成，以最新HEAD为准，不重复CLI/CI/区域修复或重跑；SDK保持CLOSED NO-GO。

只读审查collector_incremental_runtime.py、collector_incremental.py、collector_incremental_bootstrap.py、collector_incremental_scheduler.py、collector_queue.py、collector_runtime.py及tjzyefy请求/重试helper和既有pending/硬停测试。以一次tjzyefy增量消息为具体链，追踪入口lease、discovery、12详情数量预算、逐URL持久staging/barrier/ledger顺序、失败/延后、bucket完成、健康时钟和publish。不照搬区域210秒工作预算，不把bucket COMPLETED且snapshot_refreshed=false说成源完整成功。

给出一套有依据的工作/逐URL保存/最终化时间预算、复用现有预算原语的传递接口、超期结果拒绝与恢复规则；引用最新源码行号，明确已有保护、设计缺口、运行事实未核实及NO-GO。列唯一最小代码/测试范围和后续离线行为验收，保留旧canonical、未解决pending、已核验兄弟staging、成功时钟和独立来源执行。不得把未执行/超期URL标VERIFIED或清屏障，不改既有Queue/lease/健康协议，不用future冒称取消。不能在安全最小范围满足就给证据明确NO-GO，不追加模拟层或重开SDK工作流。

仅文档，不改应用、测试、workflow、锁、计划、变量或权限，不新增模拟器，不导入执行应用/真实SDK/采集/模型/测试。不联网、不读凭据/环境值/运行日志，不查云端或调用业务接口/真实缓存/数据库/函数/Queue。不新建环境/路由，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、静态验证及未完成项。按钮不可用时如实说明并给完整提示词；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
```
