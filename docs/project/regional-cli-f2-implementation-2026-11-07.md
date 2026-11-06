# F2区域CLI协作式预算：离线实现与验收

2026-11-07（Asia/Shanghai）。起点2826b30，codex/p0-reliability-contracts工作树干净，仅根代理，无相关在途工作。开始2026-11-06T17:57:41Z，前台截止18:17:41Z。读取最新协议、状态/checkpoint、next-task、F2合同、F1/F3报告及验收合同后，只实施最新授权的两个代码/测试文件。

代码提交`58e7e6b4b1c14d27b7fa9eaeb48ad15d5f2293dd`。本地协作式子项已实现；没有真实来源、云端运行或部署验收。SDK保持CLOSED NO-GO，apply_allowed=false、migration_usable=false。

## 实际实现

- [CliBudget:68](../../web/pipeline/scripts/sync_regional_ccgp.py#L68)：main进入时记录注入的monotonic，逻辑总900秒、工作840秒、收尾预留60秒；边界相等视为耗尽。每次HTTP timeout取原上限与工作余量减1秒的较小值，R<=1拒绝；sleep不足delay+1时不睡、不缩短4秒间隔，不发下一请求。
- [session:108](../../web/pipeline/scripts/sync_regional_ccgp.py#L108)：可选budget=None；CLI注入同一预算，runtime不传时维持原30/90秒和warmup sleep。open返回、read、解码之后检查；warmup的CliBudgetExceeded单独向上抛出，不被best-effort吞掉，warmup后重新算搜索timeout。
- [main:382](../../web/pipeline/scripts/sync_regional_ccgp.py#L382)：输入准备与首次请求余量检查在建立session之前；scoped/fallback/详情及解析结果完成前检查，预算失败全局终止后续业务请求和sleep，统计未完成/丢弃的查询或详情。普通网络错误不触发host熔断，F1明确拒绝的按host止损继续保持。
- 详情复用共享helper原有timeout_seconds参数；main提供本地detail_transport注入，并用partial绑定该次timeout，保留实际单参数详情调用形式。没有修改既有源码形态回归或用注释伪造调用；新增测试验证实际timeout参数，原上限30/90/30不变。
- [输出准备:315](../../web/pipeline/scripts/sync_regional_ccgp.py#L315)：records目标在F3路径预检后resolve并记录；CLI内同文件系统临时候选调用原writer，序列化完成后再检查总预算，最后os.replace明确目标。超期准备/合并/临时写入失败均不截断原records，清理本轮临时文件；不修改共享writer。
- [工作完成检查:703](../../web/pipeline/scripts/sync_regional_ccgp.py#L703)：只有配置范围实际完整、无失败且预算通过才可提交；合法完整空仍成功，预算中断的空不成功。报告包含预算阶段/耗时、work_complete、预算跳过计数、fallback未完成标志及提交状态，候选计数不冒充已写入。

提交前预算失败返回2，提交后迟到/报告失败或提交结果未知返回3；预算异常不是F1的host故障分类，也不会被普通异常处理后继续下一次业务请求。公告as_of、事实时钟、来源成功时钟、原产品解析及候选范围不因预算而放宽。

## 文件提交状态，避免把部分结果当整批完成

| 状态 | 退出码 | records_written | 文件及报告语义 |
|---|---|---|---|
| NOT_COMMITTED | 2 | false | 来源/预算/准备失败，原records保持；安全路径report尽力保存 |
| COMMIT_UNKNOWN | 3 | null | replace调用抛异常，可能未替换或已经替换；不声称零写入，不自动重试/回滚 |
| COMMITTED且post_commit_overrun=true | 3 | true | records已替换后发现总预算迟到；明确不算按时完整成功 |
| COMMITTED_REPORTING_INCOMPLETE | 3 | true | records已提交、report写入失败；结构化stderr回执不能被报告文件缺失掩盖 |
| COMMITTED、无迟到/失败 | 0 | true | 本地明确目标替换返回确认，最终report检查通过；不是跨文件事务/数据库提交 |

report返回超期后最多一次有界更正，不循环等待或无限重试。对报告写入失败提供结构化stderr。符号链接records-output的成功写入更新解析后目标并保留链接；不同路径的硬链接不承诺inode同步更新。并发路径替换、磁盘卡死、进程被杀和持久化崩溃恢复没有因此获得原子性或硬保证。

## 本轮验证

新增20项行为测试，区域CLI共48项；**全部1079项Python、冻结模板10/10及原bootstrap CLI3/3通过**。完整回归日志20.796秒；第一次完整回归中一条既有源码调用形态检查不兼容，已通过真实绑定timeout的详情调用修正后重跑全套，没有修改获授权范围外的测试。冻结门禁也绑定最终应用代码重跑。

新增测试覆盖：输入已耗尽/精确边界/R=1时客户端和HTTP0；warmup异常不吞/之后搜索timeout重算；open后禁止继续read、解码与详情解析后超期丢弃；sleep不足和醒来过期无后续请求；部分发现/fallback/空状态拒绝；实际详情timeout按余量得到6秒/2秒；完整成功和完整空；合并/序列化过期、临时写入失败清理；replace前后异常的未知状态；提交后迟到/report失败；输出符号链接目标保护。原F1/F3、默认双公告类型、9种report别名检查继续通过。

冻结官方HTML和原解析器用于事实核验，搜索/详情I/O替身、假时钟及故障注入只在现有unittest文件内；所有运行输入/records/report及候选文件都在TemporaryDirectory。F2/F1/F3测试阻断socket/create_connection/真实build_opener；完整回归另阻断外部网络/DNS和真实SDK导入，保留已有loopback重定向单元测试。日志里的prewarm/generated来自旧本地替身，不是项目模型调用。原CLI3/3仍隔离空事件watch，不能当完整事件业务验收。

[20组实际CLI状态/文件哈希](validation/regional-cli-f2-implementation-2026-11-07/cli-cases.json)包含提交前失败字节不变和提交后已写/未知两类证据；成功用例允许原地更新临时records，不能把它与仓库输入变更混同。429份2826b30已有data/fixture/历史验收文件逐一SHA256不变。测试源码及应用变更仅sync_regional_ccgp.py、test_regional_cli_completeness.py；runtime、共享HTTP helper、分类器、workflow、计划及锁均未改。

[完整证据索引](validation/regional-cli-f2-implementation-2026-11-07/manifest.json)。没有外网、真实SDK安装/导入/执行、云端/业务/缓存/数据库/函数/Queue/模型调用，没有新环境/路由、变量/凭据/权限/定时计划变更、部署/推送或运行数据/原始历史数据/公开快照写入。

## 尚未完成与下一轮

**只完成CLI协作式预算子项。** 900秒硬退出、同步urllib/磁盘调用强制取消、时钟检查与文件提交原子比较、跨文件事务、默认五地区按时完整完成、整个25分钟workflow按时成功仍未证实/NO-GO。runtime各阶段F2及跨进程共享冷却/Retry-After仍未实施。假时钟测试不是实际网络延迟、来源恢复或真实取消证明，不安排当前权限之外的探测。

下一轮建议仅本地补齐区域CI的CLI离线测试门禁：现有[workflow测试清单:60](../../.github/workflows/regional-medical-refresh.yml#L60)没有tests.test_regional_cli_completeness，paths也未包含该测试文件；这只是仓库配置事实，不代表GitHub当前运行情况。需明确授权后，只增加该路径和该模块，不改schedule、concurrency、权限、时限或业务发布/预热步骤，不推送或触发workflow。完整任务见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。
