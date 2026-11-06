# 下一轮：仅离线实现F2区域CLI协作式预算（需本地代码授权）

本轮只完成合同，不是F2实现。以下提示词包含下一轮明确的代码授权；当前不实施。推荐GPT-6.1 Sol高（high），实际运行设置未核实。硬退出/任意I/O取消与完整默认计划按时完成均不放行。

```text
继续MedicalChannelAI。我明确授权仅在现有隔离分支，本地离线实现F2区域CLI协作式预算子项，不要求也不得宣称硬时限/强制取消保证。

先核对/workspace/MedicalChannelAI-p0最新HEAD、未提交改动与在途工作。读取用户最新指令及docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、regional-cli-f2-budget-contract-2026-11-07.md、regional-cli-f1-stop-2026-11-07.md、regional-cli-f3-fix-2026-11-07.md、action-radar-acceptance-contract.md。F1实现01ccaa9、测试b97bc09及1059/10/3是已有结果，不重复施工；F2合同起点98f5503，以最新HEAD/文件为准。SDK保持CLOSED NO-GO。

完整执行最新F2合同的唯一方案，只修改sync_regional_ccgp.py和既有test_regional_cli_completeness.py，另更新文档/新增artifact。逻辑总900秒、工作840秒、收尾60秒；注入monotonic/sleep，保持HTTP原上限30/90/30，按剩余预算减1秒取timeout。睡眠预算不足则拒绝，不缩短原间隔；warmup预算异常不得被吞；请求、解码/解析返回超期不得成为可提交新事实，未完成整批沿F3拒绝。

CLI内用同文件系统临时候选准备输出，提交前检查时间与完整性，避免超期序列化先截断原records；保留report别名保护。区分提交前拒绝与提交后迟到/报告失败/结果未知，后者不能声称原文件未变或已回滚。不是跨文件事务或原子时钟CAS，不用future冒称取消。runtime不传预算保持默认行为；不实现跨进程冷却/Retry-After或扩至runtime F2。

验收使用现有unittest/冻结HTML和临时目录，阻断网络/真实客户端，注入假时钟覆盖零请求拒绝、warmup耗尽、sleep准入、timeout参数、请求/解析后超期、部分/空状态、收尾过期和文件准备/提交/报告失败边界。原F1/F3、完整成功和合法空保持；旧数据/样本/证据字节不变。实现后运行必要回归与10/3，按实际结果记录新增数量，不把假时钟通过称为真实取消或正常五地区按时完成。

仅现有隔离分支离线代码、必要测试、文档和新增artifact。不联网、不安装执行真实SDK、不读凭据/环境值/运行日志，不查云端或调用业务接口/缓存/数据库/函数/Queue/模型。不新建环境/路由，不改依赖锁、workflow、计划、变量或权限，不部署、不推送，不写运行数据、原始历史数据或公开快照。apply_allowed、migration_usable始终false，前台20分钟。若无法在该最小范围满足合同，给出证据明确NO-GO，不偷改合同或再造模拟层。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证及未完成项。按钮接口不可用时如实说明并给完整可复制提示词；推荐GPT-6.1 Sol高（high），实际设置未核实。
```
