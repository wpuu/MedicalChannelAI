# tjzyefy增量协作式预算与pending恢复：离线实现

2026-11-07（Asia/Shanghai）。起点d2d23cb，区域代码bba3716；分支codex/p0-reliability-contracts，起始工作树干净，仅根代理，无相关在途工作。开始2026-11-06T18:59:27Z，前台截止19:19:27Z。已核对最新用户授权、协议/状态/checkpoint/next-task、增量预算合同、区域实现报告和行动雷达合同。

代码提交 **b584bcf3b09e00a1d742e0c684b5a9f9c72cc03a**。只修改授权六个既有文件，另更新文档/新增artifact。仅完成Queue tjzyefy增量的本地协作式子项；SDK保持CLOSED NO-GO，apply_allowed=false、migration_usable=false。

## 实际实现

- [Queue增量入口:272](../../web/collector_queue.py#L272)在原source/日期/bucket/lease检查下接预算，原点来自process_collector_payload最初monotonic，包含预检/lease耗时，不读payload deadline、不在runner重置。只为tjzyefy传预算，其他源、区域、tick和deep继续原路径；不改配置、调度、lease或owner协议。原交付时钟delivered_at保留，增量不套用区域deep两次attempt降级规则。
- [retry helper:71](../../web/pipeline/scripts/sync_tjzyefy_market_research.py#L71)可选budget，Queue路径HTTP cap30/最多2次；timeout取工作余量减1秒与30的小值，余量<=1拒绝。初次/重试3秒sleep不足就拒绝，不压缩间隔；请求/解码返回复查，预算异常不会被当网络错误重试。无budget仍按原CLI/deep/intent行为。
- [tjzyefy discovery:302](../../web/collector_incremental_runtime.py#L302)、[verify:316](../../web/collector_incremental_runtime.py#L316)传同一预算，检查发现选择/详情解析及显式非事实None。180秒后返回的事实或None不能成为新核验或解除URL屏障的证据；未发请求不伪造HTTP成功/失败。
- [runner:523](../../web/collector_incremental_runtime.py#L523)复用唯一原执行体_run_incremental_source，仅在受控源增加异常回执与恢复处理，不新建扫描/模拟引擎。[执行体:584](../../web/collector_incremental_runtime.py#L584)保持一次discovery复用bootstrap、12数量上限、48小时carryover与原staging/barrier/ledger顺序。逐URL局部截止min(save_started+30,t0+210)，保存调用前后检查；finally保留，清理异常不能覆盖原I/O错误或吞掉KeyboardInterrupt。

原CliBudget只有工作/收尾两段，因此原始snapshot中的finalize_reserve_seconds为**90=30 URL尾部保存+60源最终化**，不是把最终化合同改成90。实际业务截止180、URL尾部截止210、最终总截止270；没有改CliBudget、CLI900/840/60或区域270/210/60。30和60均为逻辑政策预留，不是缓存I/O耗时或取消保证。

## 停止、恢复与提交边界

| 触发 | 本地实际行为 |
|---|---|
| 准入/发现/详情/解析/None/sleep超期 | 固定INCREMENTAL_TIME_BUDGET_EXCEEDED、503；停止后续业务、不开bucket、不新提交canonical或publish。规划已完成时剩余selected复用_mark_budget_deferred，含旧VERIFIED的周期重验，保留carryover资格 |
| staging写返回超局部截止 | 已写staging保留；不再解除本URL barrier或构造成功ledger，转失败/延后恢复，旧canonical和最后成功时钟保留 |
| barrier/ledger在途写迟到 | 写可能已生效，不报告按时VERIFIED或屏障未变。恢复先读取并合并最新屏障，再并回当前/剩余URL，保存非成功ledger；正常确认才报告recovery_confirmed，且scope仅PENDING_BARRIER_AND_LEDGER_ONLY |
| 恢复自身失败或总预算无余量 | recovery_confirmed=false并记录固定类型；pending_or_ledger_mutation_possible仍true，不能声称屏障已恢复、自动回滚或真实持久化。旧兄弟staging不被恢复过程覆盖/删除 |
| 保存I/O错误、finally又遇超期/保存错误 | 保留原错误类型和阶段，另记failure_ledger_error_type，不用预算错误掩盖已发生I/O问题；不继续其他业务请求。真实错误/写结果未知走固定INCREMENTAL_STATE_RESULT_UNKNOWN |
| 210最终化/270canonical调用准入不通过 | 保留已正常暂存事实，不新调用canonical；剩余pending/健康失败收尾在原总预算内尝试，不能承诺全部收尾成功 |
| canonical调用异常 | canonical_mutation_possible=true、canonical_write_completed=null；可能未写或已经写，不假称旧值未变或回滚 |
| canonical正常返回后迟到/健康失败 | 保留canonical已确认完成标记，沿原清理/健康顺序；不把已知提交改称零写或写前拒绝。完整源扫描的成功时钟和公开发布是不同事实 |
| publish余量不足31或总截止已过 | 不调用publish，503/不开bucket；canonical/健康可能已经更新，回执明确，不说整次未写 |
| publisher确认后迟到 | 保留publication_outcome=CONFIRMED，沿原bucket分支完成并报告budget_finalization_overrun，不用时间错误假称未发布 |
| publisher异常、bucket保存异常 | 发布异常为UNKNOWN；若发布已确认但bucket写失败，503仍保留snapshot_refreshed=true及确认时钟，同时bucket_mutation_possible=true，不能声称bucket已可靠完成 |
| lease获取/释放I/O异常 | 固定LEASE_ACQUIRE/RELEASE_RESULT_UNKNOWN及lease_mutation_possible；释放异常保存已有scan_result，已知owner拒绝仍保留原路径；不新增解锁/续租协议 |

时间中断503与原“仅数量延后/旧pending”的200 COMPLETED、snapshot_refreshed=false分开。后者不被误称整源成功，budget.work_complete也只有无失败/未解决屏障时才true。其他源pending、旧canonical及成功时钟在提交前失败路径保持；canonical确认后的健康/发布失败不倒退为“从未提交”。

恢复前再读屏障只减少覆盖已知新pending的风险，不构成owner/CAS或跨key原子性；异常或硬停仍可能留下部分在途写，最终依赖原投递/租约恢复。270之后不会新开业务HTTP/canonical/publish，但已发出调用及原有finally/提交后收尾可能迟到，本实现没有硬取消或严格时限保证。

## 验证与证据

新增**23项行为测试**：既有deferred预算模块15项、Queue编排5项、tjzyefy retry模块3项；另更新既有“增量不接区域预算”的断言，验证收到的是180工作预算而非区域210。最终**1121项Python回归通过（26.829秒）、冻结模板10/10、原bootstrap CLI3/3通过**。原CLI3/3仍隔离空事件watch，只证明原候选/发现门禁，不是完整事件业务验收。

- [40组实际内存状态/哈希](validation/tjzyefy-incremental-implementation-2026-11-07/source-cases.json)：准入、返回、sleep、fact/None、保存三步前后、恢复I/O失败、finally错误、周期重验carryover、12/13/合法空/旧屏障、canonical前后、健康/发布/bucket未知及硬停。每组保留其他源屏障。
- [6组Queue断言](validation/tjzyefy-incremental-implementation-2026-11-07/queue-cases.json)：原点/175秒lease预检后timeout4、payload deadline忽略、foreign/日期/bucket/owner拒绝、其他源原调用、lease获取/释放未知及原区域预算隔离。
- 复用既有MemoryCache/transport桩、实际planner/runner、冻结官方制剂室检验服务HTML及实际parser；及时事实通过、迟到事实及非事实都拒绝。没有真实SDK/真实缓存/外部网络或项目模型调用；既有回归的prewarm/generated输出是本地替身，loopback仅已有重定向安全测试使用。
- 首次全套发现既有交付时钟字符串门禁不匹配新增条件分支的调用缩进；已保持原调用形式并只增加可选budget kwargs，没有修改该测试保护或交付时钟语义。最终全套通过；恢复写入自身失败也有明确负例，未把中间通过数当最终结果。
- 480份d2d23cb已有data/fixture/验收artifact SHA256逐一不变。代码差异恰好为授权3代码+3测试，无workflow/依赖锁/计划/变量/权限/路由变化。静态verify.py核对提交与当前源哈希、门禁输出、40/6证据和保护文件；不重复执行业务或测试。

[证据索引](validation/tjzyefy-incremental-implementation-2026-11-07/manifest.json)、[验证摘要](validation/tjzyefy-incremental-implementation-2026-11-07/validation-summary.json)。40组回放复用既有测试helper，明确为合成本地桩，不另造运行/迁移引擎或输入类型。

## 权限与未完成

仅现有隔离分支的离线实现、测试和本地artifact。无外部联网、真实SDK安装/导入/执行、凭据/环境值/运行日志查询、真实云端/业务接口/缓存/数据库/函数/Queue/模型调用；无新环境/路由、计划/变量/权限改变、部署/推送、workflow触发或运行数据/历史原始数据/公开快照写入。旧验收文件只做字节哈希，不解析其日志。

**未完成/NO-GO**：真实部署/来源恢复/持久化、每轮12条或20候选按时完整、硬270/300秒退出、在途写绝不迟到、跨key原子提交/owner fence/回滚，以及其他源/事件/deep医院/publish内部时间预算。canonical与公开快照可能已经提交但bucket/lease结果未知，不等于真实取消或数据库事务。

下一轮建议仅离线制定publish时间预算与“已确认发布/结果未知/回执失败”的唯一最小合同，先审查现有发布顺序和版本门禁，不改代码、不重跑未变1121/10/3、不重开SDK审计或追加模拟层；无安全最小方案则NO-GO结束该子项。[完整下一轮任务](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
