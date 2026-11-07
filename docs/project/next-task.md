# 下一轮：区域 runtime 详情明确拒绝止损（仅两文件离线复现/修复）

依据本轮起点05cbcab、代码a352b7a的收口审查。当前轮只做文档，尚未执行此任务；下轮以真实最新HEAD和未提交改动为准。唯一优先项R1，不重复CLI F1/F2/F3，不机械扩预算。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

```text
继续 MedicalChannelAI。我明确授权仅在现有隔离分支，离线复现并最小修复区域 runtime 详情阶段单次调用的明确拒绝止损R1。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、runtime-reliability-closeout-2026-11-07.md、regional-cli-f1-stop-2026-11-07.md、runtime-f2-implementation-2026-11-07.md、publish-budget-implementation-2026-11-07.md、action-radar-acceptance-contract.md。收口起点05cbcab，代码a352b7a及1145/10/3为已有结果，以最新HEAD为准。SDK、硬取消/严格时限、原子提交及崩溃后持久回执强保证分支保持CLOSED NO-GO。

只改 web/collector_runtime.py 与 web/pipeline/tests/test_runtime_source_parity_behavior.py，另更新文档及新增artifact。先用既有runtime入口、本地MemoryCache/transport桩、冻结样本、假时钟和临时目录复现至少两个同host详情的拒绝后继续请求；阻断外网和真实SDK。若已修或不能复现，给证据关闭，不凑修复。

复用 sync_regional_ccgp.py 现有access_block_reason、RATE_LIMIT_MARKERS及RegionalCcgpSearchSession已有on_access_blocked回调，不修改共享helper、CLI或分类协议。单次区域stage调用按实际URL hostname登记明确限流、HTTP401/403/429及包装cause；warmup www拒绝反馈给详情准入，限流HTML在adapter前识别。同host后续业务请求0，未执行详情明确不完整；search.ccgp.gov.cn、www.ccgp.gov.cn及裸ccgp.gov.cn不可按父域合并，其他实际合法host独立。普通超时、网络错误、503或解析失败不得误判为全host拒绝。保持原发现阶段已有止损，不重复修复。

保留原区域270/210/60协作式预算、首次重试/最终失败降级、owner/lease、pending、成功时钟和独立来源执行。不完整阶段仍fail-closed保留旧canonical；不将跳过记录视为合法空或已核验。诊断只用既有固定原因/阶段计数/有界哈希，不泄漏URL或异常正文。不新增共享冷却/Retry-After、其他来源预算、模拟引擎或新协议。

验收：主/备用路径；401/403/429、包装异常、限流HTML、warmup反馈；明确拒绝后同host后续请求0；搜索与详情/其他host独立；普通超时/503/解析错误不误封；完整成功和合法空仍通过。验证旧canonical/pending/成功时钟及原F2超期/提交边界、首次和最终失败、foreign/owner拒绝不退化。代码实际变化后运行必要离线回归及10/3并记录实际新增数量，不将mock通过称为来源恢复、真实部署或持久化。

仅现有隔离分支两文件离线代码/必要测试、文档和新增artifact。不联网、不安装执行真实SDK，不读凭据/实际环境值/运行日志，不访问云端、业务接口、真实缓存、数据库、函数、Queue或模型。不新建环境/路由，不改其他应用文件、依赖锁、workflow、计划、变量、权限或保护，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。需扩文件或改禁止协议则给证据NO-GO，不自行扩大。

结束时更新状态、证据及下一轮完整任务，报告复现、修改、实际验证和未完成项。当前界面无法生成该按钮时明确说明并提供完整可复制提示词；推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
