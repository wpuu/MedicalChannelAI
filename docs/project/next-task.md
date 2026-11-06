# 下一轮：Queue区域runtime F2协作式预算（需明确6文件本地代码授权）

本轮仅合同，不是实现。以下提示词含下一轮局部代码授权；不授权真实接入、硬取消、Queue/租约/健康协议变化或增量预算。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

```text
继续MedicalChannelAI。我明确授权仅在现有隔离分支，本地离线实现runtime F2的Queue区域主/备用阶段协作式预算子项，不要求或宣称硬取消/严格时限/原子提交保证。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动及在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、runtime-f2-stage-budget-contract-2026-11-07.md、regional-ci-cli-gate-2026-11-07.md、regional-cli-f2-implementation-2026-11-07.md、action-radar-acceptance-contract.md。合同起点62c039e，CI6d4eb1b和CLI58e7e6b的既有94及1079/10/3不冒充新结果；以最新HEAD为准。SDK保持CLOSED NO-GO。

完整执行最新runtime合同的唯一最小方案：只改web/pipeline/scripts/sync_regional_ccgp.py、web/collector_queue.py、web/collector_runtime.py，以及既有test_regional_cli_completeness.py、test_runtime_source_parity_behavior.py、test_collector_orchestration_behavior.py，另更新文档/新增artifact，不新建预算或模拟引擎。

复用并参数化既有CliBudget，CLI默认900/840/60不变。仅Queue注册区域主/备用阶段用270秒逻辑总预算、210秒工作、60秒收尾；本地monotonic原点包括Queue预检，不从payload接deadline，不在run_stage重置。预算传到session、详情timeout、sleep与解析，耗尽后无后续业务请求，超期新事实不得进入canonical。普通网络错误不是host永久故障。

写前预算耗尽复用CollectorStageBlocked retryable=True和既有FAILED/503；保留首次重试、普通第二次失败立即降级推进及显式旧恢复例外。提交后迟到/缓存结果未知不能声称旧值未变或自动回滚，不改健康终态/时钟合同、Queue配置、租约或pending协议。保留旧canonical、未解决pending及独立来源执行。不接入增量/事件/publish预算，不改其源码，不把区域子项称为全runtime完成。

验收仅既有本地cache/transport桩、冻结证据、假时钟和临时目录，阻断外部网络与真实SDK。覆盖预检消耗不重置、准入/返回/解析/睡眠超期、primary/fallback/完整空、提交前后边界、首次与最终失败、foreign/owner拒绝、其他stage不受影响、CLI默认及既有pending/硬停回归。实现后运行必要回归及10/3，记录真实新增数量；不以mock通过宣称来源恢复/真实持久化/取消或密集fallback按时完成。

仅现有隔离分支离线工作。不联网、不安装执行真实SDK、不读凭据/环境值/运行日志，不查云端或调用业务接口/缓存/数据库/真实函数/Queue/模型。不新建环境/路由，不改其他应用文件、依赖锁、workflow、计划、变量或权限，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。若必须改上述禁止协议或扩大文件范围才能安全满足合同，给证据明确NO-GO，不偷改合同、不追加模拟层。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证及未完成项。按钮不可用时如实说明并给完整提示词；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
```
