# 下一轮：publish时间预算与提交回执合同（仅文档）

增量代码b584bcf已完成离线1121/10/3验收，不重复CLI/CI/区域/增量修复，不执行应用或测试。下一轮只文档，不授权新应用修改或云端。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

```text
继续MedicalChannelAI，仅离线制定publish时间预算与提交回执合同及唯一最小实现方案，只改文档和新增验收artifact。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动及在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、tjzyefy-incremental-implementation-2026-11-07.md、tjzyefy-incremental-budget-contract-2026-11-07.md、runtime-f2-implementation-2026-11-07.md、action-radar-acceptance-contract.md。代码b584bcf的1121/10/3为已有通过结果，以最新HEAD为准，不重复CLI/CI/区域/增量修复或重跑未变测试；SDK保持CLOSED NO-GO。

只读审查web/collector_runtime.py的_run_publish/_persist_verified_snapshot_durably、collector_incremental_runtime.py、collector_queue.py、api/public-snapshot.js、api/_snapshotRevision.js及直接调用的本地发布/版本/持久化helper与既有测试源码。不得读取运行环境值、凭据或日志，不调用这些函数。

追踪深度publish与增量触发publish两个实际入口：canonical completeness/pending保护、快照构造、LATEST缓存写入与读回、权威PUT及确认、公开缓存副本、source健康、bucket/stage/lease回执。区分canonical已提交、权威公开快照已确认、副本待重试、响应/状态保存未知；不把snapshot_refreshed=false当成已证明零写入，不改变微秒版本/同版本不同内容拒绝与已有幂等规则。

验收：引用最新源码行号，给出一套有依据的工作/提交/回执预算、可复用接口和最小修改文件，以及提交前拒绝、提交后迟到、权威写入或确认未知、缓存副本/状态/bucket/lease失败的行为标准。明确既有实现、设计缺口、运行事实未核实和GO/NO-GO；保持已确认版本、旧健康/未解决pending及独立来源执行，不修改Queue/lease/健康/版本/权威提交协议，不用future冒称取消。若现有能力下无法形成安全最小方案，明确NO-GO结束该子项，不重开SDK审计、不追加模拟层或拆成多轮补证。

仅现有隔离分支文档和新增静态artifact，不改应用、测试、workflow、依赖锁、计划、变量、权限或保护，不新增模拟器，不导入执行应用/真实SDK/采集/模型/测试。不联网、不查云端或调用业务接口/真实缓存/数据库/函数/Queue，不读凭据/环境值/运行日志。不新建环境/路由，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、静态验证和未完成项。按钮不可用时明确说明并提供完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
