# 下一轮：F1区域CLI单次调用明确限流止损

本轮只完成F3，未实施F1/F2。以下提示词含下一轮该子项的明确本地代码授权；不把当前F3授权扩大。推荐GPT-6.1 Sol高（high），实际设置未核实。

```text
继续MedicalChannelAI。我明确授权仅在现有隔离分支，本地离线修复F1的区域CLI单次调用明确限流止损子项。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动及在途工作，读取用户最新指令和docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、regional-cli-f3-fix-2026-11-07.md、shared-entry-budget-review-2026-11-07.md、action-radar-acceptance-contract.md。F3代码7b29933及1046项Python/10/3门禁已完成，以最新文件和HEAD为准，不重复修复或部署；SDK工作流保持CLOSED NO-GO。

复用既有限流/拒绝分类、unittest和冻结官方语料，阻断网络与真实客户端，仅临时目录输出，先通过sync_regional_ccgp.py真实CLI入口复现。最小修复该次调用：scoped或national fallback出现明确官方限流页、HTTP429或明确401/403拒绝后，不再向同一实际入口请求；详情入口同类反馈停止该入口后续详情，未执行部分必须判不完整。区分search.ccgp.gov.cn与www.ccgp.gov.cn，不凭共同父域扩展熔断，普通单项目超时不冒称全入口不可用。只处理区域CLI，范围无法安全最小化就给证据停止；不另建分类/模拟引擎，不扩至整个runtime。

验收：实际CLI正反例证明明确限流/拒绝后同入口后续请求0、普通网络错误不误判、完整成功/合法空仍成功；不完整批次沿用F3非零退出、明确report及records/输入字节与别名保护。运行必要回归和10/3，旧数据/样本/证据不变。不实现跨进程共享冷却、Retry-After调度或F2墙钟预算，不把单次调用止损称为完整F1解决。

仅改现有隔离分支离线代码、必要测试、文档及新增artifact。不联网、不安装执行真实SDK、不读凭据/环境值/日志，不查云端、不调用业务接口/缓存/数据库/函数/Queue/模型。不新建环境/路由，不改依赖锁/计划/变量/权限，不部署、不推送，不写运行数据/原始历史数据/公开快照。apply_allowed、migration_usable始终false，前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告复现、修改、验证及未完成项。按钮接口不可用时明确说明并给完整可复制提示词；推荐GPT-6.1 Sol高（high），实际设置未核实。
```
