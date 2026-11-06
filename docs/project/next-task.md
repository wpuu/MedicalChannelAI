# 下一轮：区域CI补齐CLI离线测试门禁（需该workflow局部修改授权）

本轮未改workflow。以下提示词包含下一轮仅paths/测试模块清单的明确授权，不扩展定时/权限/执行/推送。推荐GPT-6.1 Sol高（high），实际设置未核实。

```text
继续MedicalChannelAI。我明确授权仅在现有隔离分支，本地补齐区域CI的CLI离线测试门禁；仅允许修改现有workflow的paths和unittest模块清单，不触发workflow。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动和在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、regional-cli-f2-implementation-2026-11-07.md、regional-cli-f2-budget-contract-2026-11-07.md、regional-cli-f1-stop-2026-11-07.md、regional-cli-f3-fix-2026-11-07.md。F2代码58e7e6b、1079/10/3已通过，以最新HEAD/文件为准，不重复修复F1/F2/F3；SDK保持CLOSED NO-GO。

核对.github/workflows/regional-medical-refresh.yml，确认现有paths未包含web/pipeline/tests/test_regional_cli_completeness.py，离线unittest列表未包含tests.test_regional_cli_completeness；若已补齐给证据关闭。若仍缺失，只新增这个路径与这个测试模块，复用现有job，不新增workflow或执行环境，不改schedule、分支条件、concurrency、permissions、timeout、发布/采集/预热步骤或任何凭据引用。

验收：差异严格限上述两项及文档/新增artifact；现有测试模块和set-e均保留。使用已有工具离线核对YAML/命令结构，在外部网络/真实SDK阻断下，仅运行修改后的离线unittest模块组合，输出只在临时目录；没有应用/fixture变化时不再重复1079/10/3全套。验证实际结果并保存非敏感证据，不声称GitHub runner执行通过或真实来源验收完成。

不联网、不安装执行真实SDK、不读凭据/环境值/运行日志，不查云端或调用业务接口/缓存/数据库/函数/Queue/模型。不新建环境/路由，不改应用、测试源码、依赖锁、定时计划、变量或权限，不部署、不推送、不触发workflow，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟；无法在该范围安全完成就给证据停止，不扩大范围。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证及未完成项。按钮接口不可用时如实说明并给完整提示词；推荐GPT-6.1 Sol高（high），实际设置未核实。
```
