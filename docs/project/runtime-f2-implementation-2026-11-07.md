# Queue区域runtime F2协作式预算：离线实现

2026-11-07（Asia/Shanghai）。起点83b434c，分支codex/p0-reliability-contracts、工作树干净，仅当前根代理，无相关在途工作。开始2026-11-06T18:34:26Z，前台截止18:54:26Z。已读取最新协议/状态/checkpoint/next-task、runtime合同、CLI/CI报告及验收合同。按最新明确授权，只修改列明6个既有代码/测试文件，另加文档与验收artifact。

代码提交`bba3716d1b71e3fa6731d9bfd4b2d6d9d81a60c1`。**只完成Queue注册区域主/备用阶段的离线协作式子项，不是全runtime预算或真实服务验收。** SDK保持CLOSED NO-GO，apply_allowed=false、migration_usable=false。

## 实际变更

- [CliBudget:68](../../web/pipeline/scripts/sync_regional_ccgp.py#L68)增加可选total_seconds、work_seconds、started_at，验证有限正预算及非未来原点。CLI默认900/840/60保留；request_timeout、sleep、snapshot复用同一个原语，不另建预算或模拟引擎。
- [Queue入口:413](../../web/collector_queue.py#L413)记录本地monotonic原点，保留原payload/epoch/owner/依赖检查。仅注册区域主/备用阶段建立270/210/60预算，预检消耗不会被run_stage重置；不读取payload中的deadline。非区域、增量、事件与publish保持原run_stage调用方式和路由。
- [_run_regional_market:1320](../../web/collector_runtime.py#L1320)可选接预算；请求前、sleep、发现/详情/解析返回和canonical写前检查。共享session已有warmup预算异常重抛路径得到复用，HTTP仍用原30/90/30上限并按余量减1秒取小，4秒间隔不足就拒绝，不压短后继续请求。
- [run_stage:1786](../../web/collector_runtime.py#L1786)把写前预算耗尽转固定CollectorStageBlocked，retryable=True，沿原FAILED/503、失败健康和重试路径处理。普通首次失败重试、普通第二次失败立即DEGRADED推进、显式旧恢复例外、terminal replay及依赖跳过保持；没有修改Queue配置或owner/lease/pending协议。

canonical提交仍调用既有_cache_set与pending检查，不增加部分新事实发布或自动清理其他源pending。现有缺失canonical的seed初始化仍是旧bootstrap路径，不冒充本轮新扫描或成功时钟；预算在准备/源请求准入前检查，不能把元数据/seed与本轮新canonical提交混同。

## 提交前后与状态不确定性

| 触发 | 本地实际行为 |
|---|---|
| 工作/解析/sleep/提交准入已过期 | REGIONAL_WORK_BUDGET_EXCEEDED，FAILED/503、retryable=True；新canonical写入未开始，旧canonical、最后成功时钟、其他源pending/ledger保留 |
| canonical写入返回确认后才发现270秒迟到 | 仍沿原已完成事实的COMPLETED/健康分支，增加budget_finalization_overrun；不当作写前失败、不重复写或回滚、不宣称按时完成 |
| canonical写入异常，可能未写或已经写 | REGIONAL_CANONICAL_WRITE_RESULT_UNKNOWN，canonical_mutation_possible=true、canonical_write_completed=null，沿原失败处理；不声称旧值肯定未变 |
| canonical之后状态/健康保存失败 | REGIONAL_FINALIZATION_RESULT_UNKNOWN，明确canonical及stage/health可能变化；保留原异常传播行为，不另造健康终态或用失败消息假称已回滚 |
| 失败状态/健康本身不能保存 | REGIONAL_FAILURE_STATE_RESULT_UNKNOWN，明确stage_or_health_mutation_possible；可能仍显示RUNNING，不能宣称FAILED已可靠持久化 |

成功区域结果的预算观察点为CANONICAL_RETURN；run_stage返回层另标STAGE_RETURN，避免把canonical刚返回的快照当成后续所有状态/健康I/O的最终耗时。标记只报告本地观察，不是持久化/300秒保证。没有改变成功扫描、fallback_required/fallback_skipped或来源健康时钟的原有判定。

## 验证

新增**19项行为测试**：CLI参数化/默认值3项、区域runtime10项、Queue编排6项。最终**1098项Python、冻结模板10/10、原bootstrap CLI3/3全部通过**；完整回归25.127秒。CLI原48项及新增参数测试保持，已有增量12/13详情、pending/硬停、owner/epoch与终局重试回归包含在全套中。原CLI3/3仍隔离空事件watch，不冒称完整事件业务验收。

测试复用既有MemoryCache、冻结河北官方详情与原parser、假时钟和临时目录，没有真实SDK/缓存客户端或新模拟层。初版测试阻断器误拦asyncio本地socketpair，已改为阻断连接/DNS、保留本地事件循环通道；Queue34项定向与最终全套通过。完整回归仍阻断外部网络/DNS和真实SDK导入，已有loopback重定向测试仅使用本机桩；预热/generated输出来自既有本地替身，不是项目模型调用。

[21组区域实际状态/哈希](validation/runtime-f2-implementation-2026-11-07/regional-cases.json)与[6组Queue原点/重试/拒绝断言](validation/runtime-f2-implementation-2026-11-07/queue-cases.json)覆盖：

- 预检205秒后，预算原点仍0，搜索timeout按余量得到4秒；工作边界210/R=1时零新session/HTTP。
- sleep不足和醒来超期、搜索/fallback/详情/解析迟到，全局停止后续请求；旧canonical、其他源pending/ledger和最后成功时钟保留。
- 完整primary/fallback/合法空成功，fallback_required原语义不变；普通超时仍处理其他查询；详情实际timeout可收紧到1秒。
- 首次失败FAILED/attempt1，第二次DEGRADED/attempt2并推进，重复投递不第三次抓取；终局主阶段的fallback跳过后其他源继续。
- foreign/owner拒绝、非区域和增量路由无预算注入；canonical写前/写后异常均明确结果未知；健康保存失败与失败状态保存失败有可审计异常诊断。

460份83b434c已有data/fixture/历史验收文件逐一SHA256不变。代码差异恰好为授权的3个代码文件与3个测试文件；没有改共享HTTP helper、增量源码、API入口、workflow、vercel.json、锁或计划。[证据索引](validation/runtime-f2-implementation-2026-11-07/manifest.json)。静态verify.py已核对6文件提交/当前字节、460份保护输入、21/6组行为记录及1098/10/3输出，全部通过；不重复执行应用或测试。

## 权限与未完成

仅本地内存/临时目录验收。没有联网、真实SDK安装/导入/执行、凭据/环境值/运行日志查询、真实云端/业务接口/缓存/数据库/函数/Queue/模型调用，没有新环境/路由、变量/权限/计划变化、部署/推送、workflow触发或运行数据/原始历史数据/公开快照写入。旧验收文件只做字节哈希，不解析其日志内容。

**未完成/不放行**：增量、事件、医院、publish时间预算；密集fallback按时完整完成；270/300秒硬时限、同步HTTP/缓存强制取消、原子owner/时间/跨key提交、真实SDK可靠报错/持久化及部署验收。900秒owner活性和Queue配置保持原值；未知写入没有自动回滚或新CAS保证。假时钟/MemoryCache通过不是来源恢复、实际延迟或真实持久化证据。

下一轮建议仅离线制定增量源tjzyefy的时间预算与pending恢复合同，审查逐URL staging/barrier/ledger、bucket完成和publish边界，先形成唯一最小方案，不直接把区域方案拷过去、不改代码或重跑未变测试。详见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
