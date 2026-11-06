# 下一轮：F2区域CLI预算合同与最小实现方案（仅文档）

F1区域CLI单次调用子项已完成，不冒称完整F1完成；F3已关闭。仅文档推进，不扩大到代码或云端。推荐GPT-6.1 Sol高（high），实际设置未核实。

```text
继续MedicalChannelAI，仅离线形成F2区域CLI时间预算合同与唯一最小实现方案，只改文档和新增验收artifact。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动及在途工作。读取用户最新指令和docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、regional-cli-f1-stop-2026-11-07.md、regional-cli-f3-fix-2026-11-07.md、shared-entry-budget-review-2026-11-07.md、action-radar-acceptance-contract.md。F1实现01ccaa9、最终测试b97bc09及1059/10/3已完成；以最新HEAD为准，不重复修复或验收。F3已关闭，SDK工作流保持CLOSED NO-GO。

仅审查sync_regional_ccgp.py实际调用者、regional-medical-refresh.yml、现有session/详情HTTP helper及相关测试。区分CLI总预算和runtime阶段预算，不把平台maxDuration或20分钟前台预算直接当CLI合同。给出一套有依据的总/读阶段/失败收尾预算、monotonic传递接口、warmup/request/sleep/分页/详情准入与超期结果拒绝规则、F1/F3兼容边界，引用当前准确源码行号并列最小改动文件及行为验收标准。若正常配置无法在建议预算内完整扫描，要明确NO-GO或有界降级，不靠放宽完整性凑成功。不能用future停止等待冒称强制取消同步urllib请求。

只形成具体可评审方案，不修改应用/测试/依赖/计划，不新增模拟器、不执行CLI采集或项目模型、不重新跑条件未变的1059/10/3。不得实现跨进程共享冷却、Retry-After调度或重开SDK分支。

不联网、不安装执行真实SDK、不读凭据/环境值/日志，不查云端或调用业务接口/缓存/数据库/函数/Queue/模型。不新建环境/路由，不改计划、变量、权限，不部署、不推送，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证及未完成项。按钮接口不可用时如实说明并给完整可复制提示词；推荐GPT-6.1 Sol高（high），实际设置未核实。
```
