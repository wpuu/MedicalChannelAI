# F3：区域CLI完整性门禁离线复现与修复

2026-11-07（Asia/Shanghai）。起点2911c92，分支codex/p0-reliability-contracts、工作树干净，仅根代理运行，没有相关在途任务。按最新明确授权只处理F3；SDK工作流保持CLOSED NO-GO。首次可恢复核实时钟2026-11-06T17:26:30Z，保守收尾截止17:44:00Z，实际时间见completion.json。

代码提交：`7b2993308c41316c0b3620a80e8dd038a189f3fd`。仅本地CLI修改，没有部署或推送，不代表云端已具有该门禁。

## 复现与结果

复用既有unittest、真实argparse/main、原官方详情解析器及冻结河北/黑龙江HTML。只替换搜索/详情I/O边界，阻断socket、create_connection、真实search opener；运行输入/records/report均只写TemporaryDirectory。不是实际来源访问或线上故障复现。

| 场景 | 2911c92复现 | 修复后 |
|---|---|---|
| 全部成功 | exit 0，写入2条新核验事实 | exit 0，正常输出并保留旧事实 |
| 部分scoped查询失败 | exit 0，records被改写 | exit 2，保留原字节 |
| 部分详情失败 | exit 0，仍写入成功兄弟事实 | exit 2，保留原字节 |
| 单条搜索明确限流 | exit 0，仍写入records | exit 2，保留原字节 |
| fallback局部失败 | exit 0，仍写入records | exit 2，保留原字节 |
| 详情限流/详情全部失败/发现全部失败 | 未新增修复前行为结论 | exit 2，report明确阻断，records原字节保留 |
| 全部查询完成且无候选 | 未新增修复前行为结论 | exit 0，保留旧事实；原输入为空时输出[]，不回填 |
| scoped完整空、fallback完整成功 | 未新增修复前行为结论 | exit 0，按原规则核验输出 |

[修复前证据](validation/regional-cli-f3-2026-11-07/before.json)、[修复后逐场景退出码/哈希](validation/regional-cli-f3-2026-11-07/after.json)、[失败report](validation/regional-cli-f3-2026-11-07/blocked-detail-report.json)。修复前证据来自修改应用前、加入离线测试后；不补写未复现结论。

## 最小变更与语义

- [路径检查:208](../../web/pipeline/scripts/sync_regional_ccgp.py#L208)：resolve/samefile拒绝report与plan、每份existing-records-input、records-output的同路径/符号链接/硬链接冲突，建立session/采集请求之前退出2；危险目标不写report。records-output也不得覆盖plan。完整成功仍允许原地更新records，兼容既有CLI工作流。
- [完整性判定:451](../../web/pipeline/scripts/sync_regional_ccgp.py#L451)：任一市场失败（scoped、详情、最终地区守卫）或fallback失败阻断整批；全部发现失败也能写安全诊断report。
- [输出门禁:496](../../web/pipeline/scripts/sync_regional_ccgp.py#L496)：仅acceptance_ready时调用records writer；失败不创建输出、不重写原地或单独已有输出，安全report保存后返回2。新增acceptance_ready、acceptance_blockers、records_written、acceptance_scope。
- [15项行为测试:113](../../web/pipeline/tests/test_regional_cli_completeness.py#L113)：覆盖成功/合法空/fallback、各类失败、输出未创建/保留及9种report路径别名，另验证records不能覆盖plan。断言退出码、状态、文件字节及客户端调用数。

acceptance_scope是**配置内有界扫描**：分页/候选上限、地区匹配与产品解析均未变，不宣称全历史召回、每市场独立提交或覆盖水位。失败report的new_verified_record_count/merged_record_count只是内存候选计数，records_written=false表示没有写入部分新事实。合法空不删除已有verified事实；完全空输入/扫描才输出[]。

这是普通CLI文件保护，不是文件系统事务、CAS或数据库提交协议；未改原writer，不保证恶意并发路径替换或磁盘故障/进程中断下的多文件原子性。F1同次调用止损/跨进程冷却/Retry-After与F2墙钟预算未实现：限流使本批拒绝不等于后续查询已停止。

既有[workflow:96](../../.github/workflows/regional-medical-refresh.yml#L96)以set-e调用CLI，退出2可阻断该调用后的发布；未修改或执行工作流，未确认当前是否运行。runtime独立来源处理不变，不把CLI整批拒绝说成每市场独立完成。

## 验证与权限

- 全部1046项Python通过（原1031＋新增15），日志18.343秒；包括必要runtime、市场/产品及内核/守卫回归。audit hook阻断外部socket/DNS及真实vercel SDK导入；既有重定向安全测试使用本机loopback桩，未访问外部网络。F3测试连socket/opener都禁止。[同等阻断回归命令](validation/regional-cli-f3-2026-11-07/run-regression.py)、[日志](validation/regional-cli-f3-2026-11-07/regression.log)。既有prewarm/generated输出来自本地测试替身，不是模型请求。
- 冻结模板10/10、原bootstrap CLI3/3通过；后者仍隔离空事件watch，只证明候选/发现门禁。没有前端修改，不重复JS构建。
- 395份2911c92已有data/fixture/validation文件SHA256逐一不变；原始历史数据、旧证据与公开快照未写入。新增artifact只保存报告/哈希/日志，未另建解析或模拟引擎。
- 无真实SDK安装/导入/执行、云端/业务/缓存/数据库/函数/Queue/模型调用，无新环境/路由、锁/计划/变量/权限变更、部署或推送。apply_allowed=false、migration_usable=false；真实迁移、CAS及线上恢复未完成。

[证据索引](validation/regional-cli-f3-2026-11-07/manifest.json)。F3离线门禁已完成；下一轮需明确授权后才处理F1区域CLI单次调用止损子项，不扩到共享存储或F2。见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。
