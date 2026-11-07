# 下一轮：Queue CCGP事件阶段协作式预算（须明确六文件代码授权）

当前合同完成，应用仍4916d69，1157/10/3为已有结果。自动持续推进不扩展上一轮R1两文件权限；本轮只文档，六文件实现未获授权。唯一下一项为下述离线实现，不再追加模拟/审计轮。推荐GPT-6.1 Sol xhigh，实际设置未核实。

```text
继续 MedicalChannelAI。我明确授权仅在现有隔离分支，离线实现Queue CCGP event1–event6共用阶段的协作式时间预算及配对数据写入回执，不要求硬取消、严格时限、在途零写、原子提交或崩溃后持久回执保证。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、ccgp-event-stage-budget-contract-2026-11-07.md、runtime-regional-access-stop-2026-11-07.md、publish-budget-implementation-2026-11-07.md、action-radar-acceptance-contract.md，完整执行最新事件合同。代码4916d69及1157/10/3是已有结果，不重复CLI/区域/增量/publish修复；SDK与硬取消/原子提交/崩溃持久回执强保证CLOSED NO-GO。

只修改以下六个既有文件，另更新文档及新增artifact：
web/collector_queue.py
web/collector_runtime.py
web/pipeline/scripts/sync_ccgp_query.py
web/pipeline/tests/test_runtime_source_parity_behavior.py
web/pipeline/tests/test_collector_orchestration_behavior.py
web/pipeline/tests/test_ccgp_events.py

仅Queue注册的event1–event6复用CliBudget：总270秒、工作180秒、一次批次数据保存最多30秒、尾部60秒。原点含Queue预检/_prepare_stage，不接受payload deadline，不在runner重置。保存局部截止min(save_started+30,t0+210)；请求保留原30秒cap，timeout按工作余量减1取小；原间隔不足则拒绝，不压短，不新增HTTP重试。

scan_events只增加可选budget，无budget时保留CLI原行为。预算异常类型仅有budget时在函数内延迟从现有区域脚本取得，避免其顶层导入query造成循环；不改CliBudget或HTTP helper。请求/read/decode/解析/None/异常返回、event追加和merge须检查工作截止，generic catch不能吞预算或产生迟到discovery-only fallback。

全部项目/查询/详情完整、failures为空且merge按时完成后才保存完整片，不新增每项目checkpoint。保留前序兄弟staging，候选不原地修改读回对象。watch超过6*EVENT_BATCH_SIZE时在请求前拒绝，不能裁剪范围后称完整。event1–5仅写staging；event6先确认原CCGP_RECORDS_KEY为list（合法空允许），缺失/损坏保守拒绝，不能借原helper的初次seed豁免绕过pending；保持所有前序COMPLETED、原pending检查及单键records/events配对提交，不拆写、清屏障或修改_cache_set。

区分写前拒绝、写已发出未知、调用返回但未核实持久化、写后迟到和stage/健康/Queue尾部未知；记录目标STAGING/COMMITTED_PAIR及mutation_possible。完整数据写正常返回后迟到沿原完成/收尾并附overrun，不改称零写/回滚；异常按原失败/重试处理。receipt只在workflow结果/异常诊断，不改公开snapshot或健康/版本/Queue/lease/pending/配对协议。不因预算跳过原owner、推进、独立调度或释放。

验收只用既有MemoryCache/transport桩、事件样本、假时钟和临时目录，阻断外网与真实SDK。覆盖预检原点、零请求、timeout/sleep、正常/异常/None和解析后超期、导入顺序及无budget兼容；五项目快成功/慢拒绝、31项目拒绝、合法空watch/无新事件、event1–5不动committed及event6单键配对；前序失败/旧pending/原records缺失损坏、写前/写后迟到和抛错、状态/健康/Queue尾部未知、首次/最终失败、重复投递、foreign/owner及其他来源不受影响。运行必要离线Python回归和10/3，记录实际新增数量，不将mock通过当来源恢复或真实持久化。

不实现ccgp发现阶段预算、共享冷却/Retry-After、其他来源预算或新模拟引擎。不联网、不安装执行真实SDK，不读凭据/实际环境值/运行日志，不访问云端、业务接口、真实缓存、数据库、函数、Queue或模型。不新建环境/路由，不改其余应用文件、依赖锁、workflow、计划、变量、权限或保护，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。必须扩大文件或修改禁止协议则给证据NO-GO，不偷改合同或追加模拟轮。

结束时更新状态、证据及下一轮完整任务，报告实际完成、验证及未完成项。按钮不可用时明确说明并提供完整提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
