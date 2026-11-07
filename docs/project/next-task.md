# 下一轮：CCGP共用事件阶段时间预算及配对提交合同（仅离线文档）

R1区域单次调用子项已在代码4916d69完成1157/10/3离线验收；不是共享冷却或全项目F1完成。下轮以最新HEAD为准，只做文档，不再复现已修路径。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

```text
继续 MedicalChannelAI，仅离线制定CCGP event1–event6共用事件阶段的时间预算与事实/事件配对提交合同及唯一最小实现方案，只改文档和新增静态验收artifact。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、runtime-regional-access-stop-2026-11-07.md、runtime-reliability-closeout-2026-11-07.md、runtime-f2-stage-budget-contract-2026-11-07.md、publish-budget-implementation-2026-11-07.md、action-radar-acceptance-contract.md。区域R1代码4916d69及1157/10/3为已有结果，不重复CLI/区域/增量/publish修复或重跑未变测试。SDK、硬取消、原子提交及崩溃持久回执强保证保持CLOSED NO-GO。

只读审查 web/collector_runtime.py 的_run_ccgp/_run_event_batch、collector_queue.py、pipeline/scripts/sync_ccgp_query.py及直接调用的发现/详情/事件/版本/pending helper和既有测试源码。追踪一次event阶段Queue预检/owner/lease、watch分片、每项目搜索/详情/sleep/失败、CCGP staging和records/events配对提交、健康及终局推进。区分最后一片提交与中间片暂存，不能把watch非空或扫描完成当成新增事件非空。

基于实际请求/重试及保存链，形成一套有依据的阶段工作/保存/收尾预算、复用现有预算原语的传递接口、准入/返回/解析超期拒绝与恢复规则。保留最后已验证records/events对、未解决pending、已核验兄弟staging、成功时钟和独立来源执行；不能为按时而提交部分配对事实。审查共享host明确拒绝及普通单项目超时的既有处理，但本轮不实现F1共享冷却或Retry-After。不能照搬区域210秒、CLI900秒或平台maxDuration。

验收：引用最新源码行号与版本哈希，区分已实现保护、设计缺口、运行事实未核实和GO/NO-GO；给唯一最小修改文件及后续行为验收，不直接写代码。不改变Queue/lease/健康/pending/版本/CCGP配对提交协议，不用future冒称强制取消。安全方案若必须改禁止协议则明确NO-GO结束该子项，不追加模拟层或拆成多轮补证。

仅现有隔离分支文档和新增静态artifact。不改应用、测试、workflow、依赖锁、计划、变量、权限或保护，不导入执行应用/SDK/采集/模型/测试，不新增模拟器。不联网，不读凭据/实际环境值/运行日志，不访问云端、业务接口、真实缓存、数据库、函数或Queue。不新建环境/路由，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据及下一轮完整任务，报告实际完成、静态验证及未完成项。按钮不可用时明确说明并提供完整可复制提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
