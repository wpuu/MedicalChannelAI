# F2：区域CLI协作式时间预算合同与唯一最小实现方案

2026-11-07（Asia/Shanghai）。起点98f5503，现有分支codex/p0-reliability-contracts，工作树干净，仅根代理，无相关在途工作。开始2026-11-06T17:46:59Z，前台截止18:06:59Z。本轮仅本地源码/文档读取、静态算术与完整性验证，不执行应用、CLI采集、SDK或测试。F1实现01ccaa9、最终测试b97bc09的1059/10/3保留版本绑定；F3已关闭，SDK保持CLOSED NO-GO。

## 决策与准确边界

**唯一推荐：下一轮获本地代码授权后，实施CLI专用的协作式monotonic预算，逻辑总预算900秒、工作阶段840秒、失败/提交收尾预留60秒。** 保留既有HTTP单次上限和最小请求间隔，实际timeout取剩余预算与原上限的较小值。预算不足或返回过期时停止该次CLI的后续业务请求，未完成批次沿F3返回2、保留原records。

这是待实现的本地方案，不是已有能力、耗时测量或硬退出SLA。**900秒内强制退出、任意同步HTTP/磁盘调用可取消，以及整个25分钟job保证成功均NO-GO。** 不用future停止等待冒充底层取消，不引入子进程/信号执行载体，也不重开SDK路线。若业务要求的是上述硬保证，本方案不能放行，不能靠重复模拟补成已支持。

## 当前调用链与不同时间边界

| 对象 | 当前准确源码 | 本合同含义 |
|---|---|---|
| 真实CLI调用者 | [workflow:96](../../.github/workflows/regional-medical-refresh.yml#L96)，set-e执行main并原地输出records，成功后才运行快照发布 | 仓库非测试入口检索仅发现这一处CLI启动；不证明线上当前启用/正在运行 |
| 整个job | [workflow:47](../../.github/workflows/regional-medical-refresh.yml#L47) timeout-minutes:25 | 1500秒涵盖前置测试、行政区生成、诊断、CLI、发布/读回/提交和预热；不是CLI获配1500秒 |
| 后置预热 | [workflow:179](../../.github/workflows/regional-medical-refresh.yml#L179)，step上限8分钟、best effort | 480秒是配置，不是实测；它并未独立于job总时限 |
| CLI前置任务 | [行政区:69](../../.github/workflows/regional-medical-refresh.yml#L69)、[搜索诊断:89](../../.github/workflows/regional-medical-refresh.yml#L89) | 未读取当前执行日志/剩余时间；900秒默认只能留名义600秒给其他步骤，扣480后仅120秒，不能由此证明足够 |
| runtime导入 | [runtime:113](../../web/collector_runtime.py#L113)、[实例化:1371](../../web/collector_runtime.py#L1371)导入同一个session/helper，没有调用CLI main | 新预算只由CLI注入；runtime默认budget=None保持原行为，runtime F2仍未解决 |
| 平台函数 | [vercel.json:15](../../web/vercel.json#L15) run60秒、queue300秒，另有投递配置 | 是另一执行载体；不拿300秒给CLI定预算，也不因CLI预算补丁宣称runtime有共同deadline |
| 前台20分钟 | working-protocol第3条 | 本次人工工作截止，与业务CLI运行合同无关 |

## 静态负载与预算依据

默认[计划:3](../../web/pipeline/data/multi_region_query_plan.json#L3)为5地区、5关键词、2公告类型、每市场最多10详情、delay4秒；[fallback常量:47](../../web/pipeline/scripts/sync_regional_ccgp.py#L47)最多3页，national查询按关键词×类型全局一次，而不是每个空市场复制一次。

| 配置内场景 | scoped/fallback/详情/主页请求数 | 固定sleep名义值 | 原timeout参数相加＋sleep |
|---|---|---|---|
| 无fallback且选满50详情 | 50/0/50/1，共101 | 50×4＋50×4＋1＝401秒 | 50×90＋50×30＋30＋401＝6431秒 |
| fallback各查询满3页且选满50详情 | 50/30/50/1，共131 | 200＋30×4＋10×4＋200＋1＝561秒 | 80×90＋50×30＋30＋561＝9291秒 |
| 完整空：scoped及fallback首屏均空 | 50/10/0/1，共61 | 200＋10×4＋1＝241秒 | 60×90＋30＋241＝5671秒 |

计数依据：[scoped循环/睡眠:302](../../web/pipeline/scripts/sync_regional_ccgp.py#L302)、[fallback双层睡眠:406](../../web/pipeline/scripts/sync_regional_ccgp.py#L406)、[详情延迟:447](../../web/pipeline/scripts/sync_regional_ccgp.py#L447)、[warmup:83](../../web/pipeline/scripts/sync_regional_ccgp.py#L83)。这些是特定分支下的参数算术，不是实测，也不是urllib真实墙钟上界；解析、DNS、重定向、持续响应与本地I/O没有因此被界定。

选择900/840/60是**明确的保守策略建议**：900不占满job1500，840覆盖上述401/561秒固定等待并预留工作余量，60专留本地收尾；没有延迟分位数证明它是最优值。无fallback满详情时840−401＝439秒给101次请求及解析等；满fallback时只剩279秒给131次请求及解析等，不能称正常来源一定完成。按既有timeout组成的慢路径明显不能在此预算内完成，应整批有界降级而不是缩减查询后冒称完整。

**GO/NO-GO**：离线实现协作式预算有明确落点；默认五地区按时完整成功、现有workflow整体按时成功均尚无证据，NO-GO作保证。完整合法空只有所有必需查询都实际完成且无失败才成功；预算退出不是合法空。25分钟workflow是否还剩足够900秒，当前CLI无可信传入接口，禁止猜造当前job剩余时间；本轮和下一轮最小补丁均不改workflow/预热/定时。

| 放行对象 | 决策 | 原因 |
|---|---|---|
| 下一轮仅本地实现CLI协作式准入/超期拒绝 | GO，待该代码范围明确授权 | 两个既有文件可落地，F1/F3边界可用离线行为测试验证 |
| 声称当前F2已实现 | NO-GO | 本轮只写文档；当前main没有统一deadline |
| 声称默认五地区900秒必完整 | NO-GO | 只有静态容量算术，无真实延迟/完成率证据；慢路径应整批降级 |
| 声称25分钟job必完成 | NO-GO | 前后步骤占用和调用时剩余时间未核实，900不是父任务剩余预算 |
| 900秒硬退出、磁盘/HTTP任意卡死可取消、提交时钟原子比较 | NO-GO | 现有同步I/O与文件提交没有这些能力 |
| runtime各阶段共同deadline、共享冷却 | NO-GO，本子项不覆盖 | runtime不注入CLI预算；不更改跨进程协议 |

## 唯一实现接口与算法（均为拟议，当前未实现）

只修改`web/pipeline/scripts/sync_regional_ccgp.py`及现有`web/pipeline/tests/test_regional_cli_completeness.py`，另更新文档/新增artifact。不新增独立预算/采集/模拟引擎，不改共享HTTP模块、runtime、workflow、计划或锁。

1. 在脚本内增加小型`CliBudget`值对象与`CliBudgetExceeded`固定异常；构造接收`monotonic`、`sleep`可注入函数，默认总900、收尾保留60。`main(*, monotonic=None, sleep=None)`保持无参入口兼容，在main进入时记t0；参数解析/输入加载后、客户端建立前检查预算。不是用公告as_of计算耗时，不新增环境变量或CLI调参项。
2. 唯一工作deadline `Dw=t0+840`、提交准入deadline `Dt=t0+900`。`now>=deadline`视为耗尽。工作阶段包括warmup、sleep、HTTP、解码/搜索解析、候选/详情解析及扫描整理；提前完成立即收尾，不等待840秒。60是预留而非硬可抢占保证，最终化也不得再采集。
3. `request_timeout(cap)`每次重算`R=Dw-monotonic()`：R<=1秒拒绝启动，否则返回`min(cap,R-1)`，必须为正有限值。1秒只是返回后检查余量，不是解析耗时保证。warmup cap30、search cap90来自[session:83/100](../../web/pipeline/scripts/sync_regional_ccgp.py#L83)，detail cap30来自[detail:1433](../../web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1433)；不降低原上限来凑通过，不增加重试。
4. `sleep_checked(delay)`在R<=delay+1时拒绝，不能缩短原4秒礼貌间隔后继续请求；足够时才睡原delay，醒来重查。包括warmup的1秒和scoped/fallback/详情所有现有sleep。被F1阻断的请求不再为了“覆盖完整”消费时间或重试。
5. `CcgpSearchSession(..., budget=None)`可选注入；CLI传同一预算，runtime不传。`_read`在open前取timeout、open返回/读取前、read/解码返回后复查；`fetch`在warmup返回后重新取搜索timeout。warmup显式`except CliBudgetExceeded: raise`，不能被现有best-effort catch吞掉后再搜索。
6. `fetch_candidates_page`接口不变，session承担I/O预算；返回后CLI复查搜索解析耗时。详情复用现有`fetch_ccgp_detail_html(url, timeout_seconds=budget.request_timeout(30))`，无需修改该共享函数。详情返回及adapter解析后都重查，超期结果不加入候选/新事实。socket timeout不是整个read硬deadline，卡死调用可能在返回前无法报告。
7. 各阶段对预算异常做独立全局终止标志，不能当普通网络错误继续下个查询，也不能误分类成F1某host被拒绝。后续work请求/sleep为0，标记未执行scoped/详情与fallback覆盖不完整；条件性后续页数未知就保留未知。F1按host停止与该全局预算终止同时保留，403与预算原因可并列记录。

## 收尾、文件边界与不可伪造的结果

在Dw前做最后扫描/解析准入检查，确定所有所需工作完成后才允许候选成功。F3[acceptance:508](../../web/pipeline/scripts/sync_regional_ccgp.py#L508)再合入BUDGET_EXCEEDED与阶段枚举、未执行范围；任何预算未完成都返回2、records_written=false，不刷新数据/来源成功时钟。

收尾预留60秒用于合并/验证、准备诊断与本地文件提交。现有[write_json:51](../../web/pipeline/scripts/sync_ccgp_query.py#L51)直接write_text会先打开目标，不适合作为预算检查后的可撤销准备操作。**最小补丁应在CLI内复用该writer写同文件系统的临时records候选，完成序列化后再检查Dt与完整性，最后才os.replace目标。** 不修改全局writer，不让超期序列化先截断原records。候选验证/准备失败、提交前预算耗尽时只清理本轮临时文件，原records与所有输入保持原字节，安全report可尽力记录失败。

路径预检沿用F3的resolve/samefile，危险report路径在任何临时写入前拒绝；若records-output是符号链接，提交指向预检记录的解析后目标，避免静默替换链接本身。不同名字的硬链接在成功原子替换后可能不再共享inode，此方案不承诺硬链接别名同步更新。只保障明确records目标；并发路径替换/恶意本地修改不在该协作式补丁保证内，不冒称CAS。

**边界必须明说**：本地os.replace也不能把“读时钟＋改文件”变成原子时间比较，磁盘调用可能跨Dt；records/report也不是跨文件事务。因此提交前已检测的超期结果必须拒绝；提交调用已开始后才发现迟到，不能声称原records未写、不能自动回滚或重试。记录`commit_state=COMMITTED`及`post_commit_overrun=true`；若提交结果未知则`COMMIT_UNKNOWN`，若records已提交而report失败则`COMMITTED_REPORTING_INCOMPLETE`，非零退出并如实区分。此类运行不能计作按时完整通过。

所有同步I/O返回后都能检查预算，不等于所有调用能在900秒内返回。若验收要求“任意时刻跨900秒都必然零写入/强制取消/成对文件原子提交”，本最小方案NO-GO，不能通过隐藏提交边界、future或无证据的回滚宣称满足。budget指标不进入canonical事实；诊断失败不得覆盖输入。

拟议report：`budget.total_seconds=900`、`work_seconds=840`、`finalize_reserve_seconds=60`、`elapsed_seconds`、`exhausted_phase`、`work_complete`、`commit_state`、`post_commit_overrun`及按已知范围统计的deferred；elapsed只来自monotonic，as_of不改。成功必须无预算失败、范围完整且提交确认；预算耗尽时report不能把部分new_verified计数解释成已写入。

## 后续行为验收门槛（本轮不执行）

| 必测触发 | 预期行为 |
|---|---|
| 输入准备已耗尽；Dw精确边界；R<=1 | 客户端/HTTP0，不写records，exit2 |
| warmup耗尽、warmup返回超期 | 不被catch吞掉，搜索0，不写records |
| HTTP timeout预算、warmup之后预算 | cap分别30/90/30且<=当次R−1；重算而非缓存旧值 |
| sleep不足/醒来超期 | 不缩短4秒去发请求；不新增请求；全局停止而非误判某host不可用 |
| search/detail read、解码、解析后超期 | 过期返回内容不进入可提交新事实，无后续业务请求 |
| scoped/fallback/详情只完成部分；表面空 | exit2，report明确BUDGET_EXCEEDED与未完成范围，原records不变 |
| 完整成功/完整合法空/普通单项目错误 | 正常成功保持；普通错误不误触发host停止，仍由F3判不完整 |
| finalize/序列化耗尽、临时写入失败 | 原records/input字节不变，临时文件清理；危险report别名零写入 |
| replace或report返回超期/失败 | 明确COMMITTED、COMMIT_UNKNOWN或COMMITTED_REPORTING_INCOMPLETE，非零，不伪称回滚/零写入/按时成功 |
| runtime不注入、F1明确拒绝、默认双公告类型 | 保持现有默认行为与F1/F3回归；CLI新预算不扩至runtime |

复用当前unittest入口/冻结HTML/临时目录，注入假时钟和现有I/O桩，不新建模拟器。测试要验证实际调用参数、次数、退出码、report和文件字节，不能只断言源码字符串；假时钟只证明协作逻辑，不证明真实网络取消或时延SLA。实现后才跑必要回归、1059基线与冻结10/3；数量按实际新增为准，不能提前写通过。

## 本轮验证与权限

本轮对引用位置、文件SHA256、静态计数/预算关系做离线核对，420份98f5503已有data/fixture/验收文件字节不变，web/.github与b97bc09一致；旧验收文件仅做字节哈希，不解析测试日志内容，没有重跑1059/10/3或导入应用/SDK。它们是已有成果，不能算本轮新行为验证。[本轮证据](validation/regional-cli-f2-contract-2026-11-07/manifest.json)。

没有联网、凭据/环境值或运行日志查询、云端/业务/缓存/数据库/函数/Queue/模型调用，没有应用/测试/锁/计划/权限/环境/路由修改、部署、推送或运行数据/原始历史数据/快照写入。apply_allowed=false、migration_usable=false。

下一轮需明确本地代码授权后，才按上述唯一协作式方案修改两个既有文件；不授权硬退出或真实来源验收，不放开F1/F3，不把本次文档完成写成F2已实现。见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际运行设置未核实。
