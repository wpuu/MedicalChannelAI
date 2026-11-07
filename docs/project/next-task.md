# 下一轮：F1/F2/F3收口审查与唯一下一优先项（仅文档）

publish调用者代码a352b7a已完成1145/10/3离线验收。下轮仅文档，不新改应用或叠加模拟；强保证和SDK分支CLOSED NO-GO。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

```text
继续MedicalChannelAI，仅离线做F1/F2/F3工程收口审查与唯一下一优先项决策，只改文档和新增静态验收artifact。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动及在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、publish-budget-implementation-2026-11-07.md、publish-budget-receipt-contract-2026-11-07.md、tjzyefy-incremental-implementation-2026-11-07.md、runtime-f2-implementation-2026-11-07.md、shared-entry-budget-review-2026-11-07.md、action-radar-acceptance-contract.md。代码a352b7a及1145/10/3为已有结果，以最新HEAD为准，不重复CLI/CI/区域/增量/publish已修问题或重跑未变测试。SDK与跨进程硬取消/持久回执强保证分支保持CLOSED NO-GO，不重开审计或追加模拟。

静态复核现有调用者和直接helper，建立实际覆盖矩阵：CLI完整性/限流止损/900预算、区域Queue270预算、tjzyefy增量270/180/30/60、publish调用者270/210/60与ACK保真；区分已实现且本地验证、只设计、未覆盖来源、运行事实未核实及关闭项。追踪剩余共享host冷却/Retry-After、医院/事件阶段、其他增量来源和真实发布验收门槛，但不直接实施或机械扩预算。

验收：引用最新源码行号与版本绑定证据，最多列三项仍然存在且有依据的缺口，不凑数；说明影响、优先级、最小后续工作、行为验收和所需授权。给唯一下一优先项或明确暂停结论，说明为何优先于其他项；不能把历史来源状态、本地mock、权威ACK或bucket完成当当前完整采集/真实部署/持久化/客户交付证据。不削弱既有pending、健康、版本幂等、独立来源或权限边界，不改协议。

仅现有隔离分支文档和新增静态artifact；不改应用、测试、workflow、依赖锁、计划、变量、权限或保护，不导入执行应用/真实SDK/采集/模型/测试，不新增模拟器。不联网、不读凭据/实际环境值/运行日志，不查云端或调用业务接口/真实缓存/数据库/函数/Queue。不新建环境/路由，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、静态验证及未完成项。按钮不可用时明确说明并提供完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
