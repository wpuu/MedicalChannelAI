# 下一轮：Queue ccgp发现/事实预算与双键准备（须明确来源范围授权）

当前五文件方案完成；代码仍5d2fe85，1181/10/3为已有结果。本轮只文档，上一轮用户明确禁止其他阶段预算，自动继续不新增ccgp代码授权。推荐GPT-6.1 Sol xhigh，实际设置未核实。

```text
继续 MedicalChannelAI。我明确授权仅在现有隔离分支，离线实现Queue ccgp发现/事实阶段协作式预算与staging/watch准备回执；不要求硬取消、严格时限、跨键原子性、在途零写、自动回滚或崩溃持久回执保证。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、ccgp-discovery-stage-budget-contract-2026-11-07.md、ccgp-event-stage-budget-implementation-2026-11-07.md、action-radar-acceptance-contract.md，完整执行最新发现阶段合同。代码5d2fe85及1181/10/3为已有结果，不重复事件/区域/CLI/增量/publish修复；SDK及强保证分支保持CLOSED NO-GO。

只修改以下五个既有文件，另更新文档及新增artifact：
web/collector_queue.py
web/collector_runtime.py
web/pipeline/scripts/sync_ccgp_query.py
web/pipeline/tests/test_runtime_source_parity_behavior.py
web/pipeline/tests/test_collector_orchestration_behavior.py

仅stage==ccgp的Queue路径复用CliBudget，总270秒、工作150秒、共同双键准备与读回60秒、尾部60秒。原点包含预检和stage准入，不接payload deadline、不重置。准备截止min(prepare_started+60,t0+210)。搜索/详情保留cap30，timeout按工作余量减1收紧；原sleep不足就拒绝，不压短、不新增HTTP重试。

discover_candidates仅增加可选budget和函数内延迟取得既有预算异常；scan_events、CliBudget、HTTP helper不改。请求、异常、None、解析、去重/排序、详情append、merge/watch/digest超期不得成为新事实。generic catch不能吞预算。新Queue路径发现数超max_candidates时详情前整批拒绝，watch超min(计划上限,六片容量)时准备前拒绝；不能裁剪范围后称完整。无budget/CLI保持原默认路径。

保留_cached_list原seed行为及committed优先基线，调用前后记录可能的旧seed写入；超期后不能声称全系统零写。不修改_cache_set、_cached_list、pending/健康/版本或配对helper，不提前写COMMITTED_STATE_KEY，不刷新源成功时钟、不调用publish。

候选保持原staging字典与watch list格式，复用_digest。准备顺序为STAGING写→读回匹配→WATCH写→读回匹配，每步及摘要校验前后检查共同截止。两键按时匹配才PREPARED_LOCAL_READBACK；缺失/None、旧watch、错cycle/摘要或迟到均为准备INCOMPLETE/未知、FAILED/503，不推进event1。

逐键记录write_attempted、write_call_returned、mutation_possible及readback状态。首键已写/第二键未知、两写返回但读回未确认均如实保留，不改称零写或自动回滚，不盲补后键；旧committed和未解决pending、兄弟staging及独立来源保持。receipt只在workflow结果/诊断，不改staging/watch/公开snapshot结构。两键已按时匹配后的状态、健康或Queue尾部错误单独标未知；保留原重试/最终降级/owner/独立调度/释放，不因预算跳过收尾。

仅用既有MemoryCache/transport桩、冻结搜索/详情、假时钟和临时目录，阻断外网与真实SDK。覆盖预检/seed原点、timeout/sleep及正常/异常/None/解析/merge/digest超期；完整空、12/13候选、watch超量；warm/cold初始化副作用；两键各写/读回的前后异常与迟到、错cycle/旧watch/None/不匹配；旧committed/pending/兄弟staging/成功时钟；准备后尾部未知、首次/最终失败、重复投递、foreign/owner和其他阶段/CLI兼容。实际代码变化后运行必要Python回归及10/3，记录实际新增数量，不把mock通过当来源恢复、真实持久化或完整召回。

不实现其他来源预算、共享冷却或Retry-After，不新增模拟引擎。不联网、不安装执行真实SDK，不读凭据/实际环境值/运行日志，不访问云端、业务接口、真实缓存、数据库、函数、Queue或模型。不新建环境/路由，不改其他应用文件、依赖锁、workflow、计划、变量、权限或保护，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。必须扩大文件或改变禁止协议则给证据NO-GO，不追加模拟轮。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证及未完成项。按钮不可用时明确说明并提供完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
