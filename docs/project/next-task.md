# 下一轮：publish调用者侧预算与回执保真（需明确七文件离线代码授权）

当前仅合同，未实现publish内部预算。唯一建议是Python调用者侧协作式准入与现有ACK保真；跨进程硬取消/持久回执子项CLOSED NO-GO，不再追加模拟/SDK补证。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

```text
继续MedicalChannelAI。我明确授权仅在现有隔离分支，本地离线实现publish调用者侧协作式预算与现有提交ACK回执保真，不要求或宣称硬取消、严格时限、在途写零变化、原子提交或崩溃后持久回执保证。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动及在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、publish-budget-receipt-contract-2026-11-07.md、tjzyefy-incremental-implementation-2026-11-07.md、runtime-f2-implementation-2026-11-07.md、action-radar-acceptance-contract.md，完整执行最新合同。合同起点82c1006，代码b584bcf的1121/10/3是已有结果，不重复CLI/CI/区域/增量已修问题；以最新HEAD为准，SDK保持CLOSED NO-GO。

只修改web/collector_runtime.py、web/collector_queue.py、web/collector_incremental_runtime.py、web/pipeline/tests/test_collector_publish_environment.py、web/pipeline/tests/test_runtime_source_parity_behavior.py、web/pipeline/tests/test_collector_orchestration_behavior.py、web/pipeline/tests/test_collector_deferred_budget.py，另更新文档和新增artifact。不改Node endpoint、SQL/版本/数据库helper、CliBudget、依赖、平台配置或协议。

deep publish复用Queue入口原点，逻辑总270秒、发布工作210秒、已确认后收尾预留60秒，PUT cap30及余量减1秒，零本地HTTP重试。tjzyefy传已有parent budget，原270/180/30/60不变；publish_work_deadline=min(parent.started+210,parent.started+parent.total_seconds-60)，不能重置原点或误用parent180工作截止代替发布210。保留原外层31准入，内部按同一clock检查canonical读取、构造/JSON/digest、LATEST与PUT准入/返回；不从payload传deadline。

复用现有Node ACK字段：HTTP200、ok严格true、durable_committed严格true、精确版本和整数pool数量全部校验通过才能CONFIRMED。PUT前NOT_ATTEMPTED，发出后未确认UNKNOWN；迟到先验ACK再判时间，正确ACK不可降为未提交。分别保留Node/Python副本回执，任一未确认保守RETRY_REQUIRED；确认后总预算不足可跳过后续可选Python副本，但不撤销权威提交。不改变Node请求/响应字段，不把本地digest当数据库hash。receipt只放workflow结果/异常诊断，不进入公开snapshot或改变其hash、source_health、snapshot_as_of；parent.work_complete不作为公开提交证明。

保留既有stage/bucket/heartbeat/pending按证据reconcile/tick/owner/lease顺序及重试限额；已确认后状态或回执失败单独标未知，不声称零写、回滚、按时或已可靠完成。不能因budget新增中途异常跳过独立调度/释放。原健康/版本微秒/同版本冲突/回退/幂等协议不变，不换时间戳绕过冲突。其他来源和stage不新增预算。

验收仅既有本地cache/HTTP桩、冻结证据、假时钟、临时目录，阻断外网和真实SDK。覆盖预检原点与parent传递、读取/构造/LATEST/PUT超期、timeout参数、坏/缺/false ACK、迟到合法ACK、两份副本状态、确认后stage/bucket/heartbeat/tick/lease失败与owner替换、合法空/缺canonical/CCGP committed对/pending/健康/其他stage保护。实现后必要Python回归和10/3，记录实际新增数量；Node及JS门禁源码未改时只静态保护，不重跑JS或安装/导入真实SDK。若必须扩大七文件范围或修改禁止协议才能安全完成，给证据NO-GO结束，不偷改合同、不追加模拟层或重开SDK审计。

不联网、不安装执行真实SDK、不读凭据/实际环境值/运行日志，不查云端或调用业务接口/真实缓存/数据库/函数/Queue/模型。不新建环境/路由，不改其他应用文件、workflow、依赖锁、计划、变量、权限或保护，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证和未完成项。按钮不可用时明确说明并给完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
