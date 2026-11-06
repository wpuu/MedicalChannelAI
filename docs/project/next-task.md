# 下一轮：tjzyefy增量协作式预算（需明确六文件本地代码授权）

本轮合同已完成，增量代码尚未实现。以下完整提示词仅授权列明六文件的本地离线实现；不授权云端、部署、硬取消或协议变更。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

```text
继续MedicalChannelAI。我明确授权仅在现有隔离分支，本地离线实现tjzyefy增量协作式时间预算及pending恢复子项，不要求或宣称硬取消、严格时限、在途写零变化或原子提交保证。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动和在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、tjzyefy-incremental-budget-contract-2026-11-07.md、runtime-f2-implementation-2026-11-07.md、action-radar-acceptance-contract.md。本合同起点d6a9cee，区域代码bba3716及1098/10/3是已有结果，不重复CLI/CI/区域修复；以最新HEAD为准，SDK保持CLOSED NO-GO。

只修改web/collector_queue.py、web/collector_incremental_runtime.py、web/pipeline/scripts/sync_tjzyefy_market_research.py、web/pipeline/tests/test_collector_deferred_budget.py、web/pipeline/tests/test_collector_orchestration_behavior.py、web/pipeline/tests/test_tjzyefy_sync.py，另更新文档和新增artifact。不修改CliBudget、planner、bootstrap、scheduler、runtime._cache_set或publish内部。

完整执行最新合同：仅Queue mode=incremental且source_id=tjzyefy复用CliBudget，逻辑总270秒、工作180秒、在途URL保存尾部30秒、最终化预留60秒。monotonic原点包括所有预检/lease，不从payload读取deadline或在runner重置。HTTP保持cap30/最多2次和原3秒间隔；timeout=min(30,工作余量-1)，sleep不足或醒来超期即拒绝，预算异常不得当普通网络错误重试。请求/解码/解析及非事实None迟到不得作为新核验证据。

URL保存局部截止min(save_started+30,t0+210)，每步调用前后检查，保持staging→本URL barrier→ledger及finally原序。超期不再准入下一成功变更；当前及未执行selected复用既有失败/延后和pending保存，不更新为新VERIFIED、不删除兄弟staging。已发出写迟到须标mutation_possible/结果未知；现有失败恢复正常确认前不得声称屏障已恢复、零写或回滚，不保证物理阻止在途写。

时间中断503、不开bucket、不canonical提交或publish；原数量deferred/旧pending分支保持原语义，不能把bucket COMPLETED且snapshot_refreshed=false当源完整成功。最终化210前准入，canonical调用270前准入，发布至少余31秒才准入；提交后迟到、写入/健康/发布/bucket/lease未知须准确区分，不用时间错误覆盖已知提交。保留旧canonical、未解决pending、及时核验兄弟staging、最后成功时钟和独立来源执行。增量不套用区域deep两次attempt降级，不改Queue/lease/健康/pending协议；其他来源、区域、deep及CLI行为保持。

验收仅既有MemoryCache/transport桩、冻结证据、假时钟和临时目录，阻断外部网络与真实SDK。覆盖预检原点、准入/返回/解析/None/sleep超期、timeout与重试、保存每步前后迟到/失败、finally/硬停、剩余周期重验carryover、12/13/合法空/旧pending、canonical与发布前后及bucket/lease未知、foreign/owner/其他源不受影响。实现后运行必要回归和10/3，记录实际新增数量；mock通过不等于来源恢复、真实持久化或取消保证。若必须扩文件或改禁止协议才能满足，给证据NO-GO，不偷改合同、不追加模拟层。

仅现有隔离分支离线工作。不联网、不安装执行真实SDK、不读凭据/环境值/运行日志，不查云端或调用业务接口/真实缓存/数据库/函数/Queue/模型。不新建环境/路由，不改其他应用文件、依赖锁、workflow、计划、变量或权限，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证及未完成项。按钮不可用时明确说明并给完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
