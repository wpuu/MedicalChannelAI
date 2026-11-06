# 下一轮：runtime F2阶段预算合同与唯一最小方案（仅文档）

不重复CLI/CI修复，不执行workflow、runtime或SDK。推荐GPT-6.1 Sol xhigh（超高），涉及阶段租约、pending及重试边界；实际运行设置未核实。

```text
继续MedicalChannelAI，仅离线制定runtime F2阶段预算合同与唯一最小实现方案，只改文档和新增验收artifact。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动和在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、regional-ci-cli-gate-2026-11-07.md、regional-cli-f2-implementation-2026-11-07.md、regional-cli-f2-budget-contract-2026-11-07.md、shared-entry-budget-review-2026-11-07.md、action-radar-acceptance-contract.md。CI提交6d4eb1b的8模块94项本地通过，CLI代码58e7e6b的1079/10/3是已有结果，以最新HEAD为准，不重复施工或重跑；SDK保持CLOSED NO-GO。

只读审查web/collector_runtime.py、collector_incremental_runtime.py、collector_queue.py、vercel.json及直接调用的请求/重试helper和既有相关测试。追踪一个真实阶段的入口、monotonic剩余预算、sleep/请求/重试、pending/barrier保存、健康与终态更新及Queue交付边界。区分阶段预算、平台maxDuration和CLI900秒预算，不直接照搬CLI数值。

产出一套有依据的阶段工作/收尾预算、传递接口、超期结果拒绝及恢复规则，引用当前精确行号；明确有实现证据、设计缺口、运行事实未核实和NO-GO项。列唯一最小修改文件及后续离线行为验收，保留已验证canonical、未解决pending和独立来源执行，不把普通超时当全host永久故障。不能用future停止等待冒称取消，不能借预算改Queue配置/租约/健康合同或重开SDK路线。无法形成安全最小方案就给证据明确NO-GO，不拆成多轮模拟。

仅文档，不改应用、测试、workflow、依赖锁、计划、变量或权限，不新建模拟器，不导入/执行应用、真实SDK、采集、模型或测试。不联网，不读凭据/环境值/运行日志，不查云端或调用业务接口/缓存/数据库/函数/Queue。不新建环境/路由，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、静态验证及未完成项。按钮不可用时如实说明并提供完整提示词；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
```
