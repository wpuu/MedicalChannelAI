# runtime F2阶段预算合同与唯一最小方案

2026-11-07（Asia/Shanghai）。起点62c039e，分支codex/p0-reliability-contracts，工作树干净，仅根代理，无相关在途工作。开始2026-11-06T18:22:45Z，前台截止18:42:45Z。按最新任务只阅读源码/既有测试和文档，做静态算术、引用及完整性验证；不导入或执行应用、SDK、采集、Queue、模型或测试。

## 决策

**唯一推荐的最小实现范围：Queue deep区域主/备用阶段的协作式预算，逻辑总270秒、采集/解析工作210秒、状态收尾预留60秒。** 以`regional_he`及`regional_he_fallback`为代表，由同一既有区域函数覆盖已注册区域阶段；不同时给增量、事件、医院或publish阶段接入预算。下一轮须明确离线代码授权后才实施。

这是政策建议，不是已有实现或已测SLA。300秒函数配置减30秒名义外层余量得到270，270再减60收尾得到210；60用于现有缓存/状态/健康/heartbeat/enqueue收尾，不代表每个SDK调用有60秒总硬上限。**完整runtime统一预算、硬300秒退出、同步HTTP/缓存取消、原子owner/时间/提交及实际部署放行均NO-GO。** 默认密集fallback的完整完成率未知，必须允许整批失败/降级；不能缩短查询范围后假称完整。

CLI900/840/60不是本合同。人工前台20分钟、API调度60秒、Queue函数300秒、Queue消息lease300秒、应用owner活性15分钟及缓存TTL是不同边界，不能互换。

以下时限、attempt和lease数值均为当前仓库配置/代码声明；未查询部署元数据或执行回执，不证明现有部署已采用、SDK实际执行行为或平台运行上限已核实。

## 一次真实阶段的完整调用链

| 边界 | 当前源码事实 | 拟议预算处理 |
|---|---|---|
| Queue入口 | [api worker:21](../../web/api/collector-queue.py#L21) → [process:412](../../web/collector_queue.py#L412)；payload/epoch检查在cache/lease/enqueue前 | 在process函数进入时读取本地monotonic原点，但只给通过原身份检查的注册区域消息建立预算；不从payload接收deadline |
| 配置载体 | [vercel.json:18](../../web/vercel.json#L18)300秒；[accept_and_handle:38](../../web/api/collector-queue.py#L38)lease_duration300；订阅retry_after150/max_attempts3 | 保持全部配置，270仅为回调内逻辑预算；SDK分发/请求解析的已耗时间没有可信接口，30秒余量不是证明 |
| owner预检 | [queue:432](../../web/collector_queue.py#L432)恢复过期owner、确认cycle/as_of、heartbeat；依赖已DEGRADED时直接跳过 | 预检耗时也消耗同一预算，不在run_stage里重新开始计时；所有现有owner/epoch拒绝保留 |
| stage准入 | [run_stage:1741](../../web/collector_runtime.py#L1741)构造cache，[_prepare_stage:507](../../web/collector_runtime.py#L507)检查日期/前序/attempt后写RUNNING | 不改变准入、计数、日期及前序合同；预算失败仍属于本次已准入attempt，不以新消息/新租约重置成本 |
| 区域采集 | [_run_regional_market:1318](../../web/collector_runtime.py#L1318) → session → scoped或national fallback → 选择/详情/解析 | 可选budget向下传同一原点；每次请求/sleep准入及返回/解析后检查；耗尽抛出专门预算异常，不能被普通catch吞后继续查询 |
| canonical提交 | [runtime:1519](../../web/collector_runtime.py#L1519)合并后[_cache_set:294](../../web/collector_runtime.py#L294)；[待核验屏障检查:316](../../web/collector_runtime.py#L316)先于cache.set，清理在set之后 | 工作范围完整且收尾准入通过才进入原写入器；不新增部分发布、不绕过pending检查，不改全局cache写入协议 |
| 状态/健康 | [异常:1779](../../web/collector_runtime.py#L1779)FAILED/503及失败健康；[成功:1800](../../web/collector_runtime.py#L1800)COMPLETED后按complete_scan/fallback规则记健康 | 保留现有状态与健康合同；预算中断在canonical写入前转CollectorStageBlocked，retryable=True；最后成功时钟不被失败刷新 |
| worker收尾 | [queue:470](../../web/collector_queue.py#L470)run_stage后再次heartbeat；COMPLETED/终局DEGRADED推进下一阶段，临时失败抛异常等待既有投递 | 不改send/idempotency/retry/degrade决策，不增加额外手工投递或等待 |

仓库非测试调用检索中，run_stage仅由该Queue路径调用；[collector-run](../../web/api/collector-run.py#L195)主要排队启动/增量消息，不在60秒入口内直接执行run_stage。只说明当前仓库调用关系，不证明部署版本或线上调度状态。

## 已有保护，不能重复报修

1. 区域runtime发现明确拒绝即停止，部分发现/详情失败在canonical写入前阻断：[1405](../../web/collector_runtime.py#L1405)、[1512](../../web/collector_runtime.py#L1512)，既有[行为测试311/353](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L311)。CLI/CI修复不能冒充这些runtime能力的新增实现。
2. 重试不是无限循环：[runtime:131](../../web/collector_runtime.py#L131)普通stage每日attempt上限2，[_stage_retry_limit_reached:481](../../web/collector_runtime.py#L481)含显式旧恢复例外；[Queue:500](../../web/collector_queue.py#L500)最后一次实际失败立即降级/推进，publish失败保持FAILED并释放owner。SDK投递3次和业务attempt2不是同一个计数。[测试136/147](../../web/pipeline/tests/test_collector_orchestration_behavior.py#L136)已覆盖首次重试及最终推进，本轮不重跑。
3. owner缓存保留2天不同于活性：[namespace:26](../../web/collector_namespace.py#L26)深度owner TTL2天，增量owner TTL15分钟，deep执行活性按[wall heartbeat:80](../../web/collector_namespace.py#L80)15分钟判定，不能用冻结cycle_as_of证明活性。预算补丁不修改这些数值或续租协议。

## 增量pending/barrier链：审查并保留，暂不接预算

[Queue增量:290](../../web/collector_queue.py#L290)获取scan lease，运行源扫描，finally按scan_id释放；[run_incremental_source:539](../../web/collector_incremental_runtime.py#L539)只做一次实际discovery，然后把结果传给bootstrap。[bootstrap:98](../../web/collector_incremental_bootstrap.py#L98)明确不发官方请求，未提供discovered时返回DISCOVERY_REQUIRED；不能把Queue前置bootstrap误报为重复抓取。

扫描先把selected/deferred URL并入barrier并保存ledger，[575](../../web/collector_incremental_runtime.py#L575)；每条事实按[598](../../web/collector_incremental_runtime.py#L598)“核验→持久staging→解除本URL barrier→更新VERIFIED ledger”排序，并在finally保存ledger。失败/未选详情和旧未解决URL在[637](../../web/collector_incremental_runtime.py#L637)重新并入pending；有失败返回503；只有pending、没有本轮失败时沿[677](../../web/collector_incremental_runtime.py#L677)现有bucket完成但snapshot_refreshed=false的路径，并不是源完整刷新。全范围解除后才写canonical、清pending、记成功、尝试publish和完成bucket。

既有[12条/第13条延后](../../web/pipeline/tests/test_collector_deferred_budget.py#L89)、[硬停先保存事实/非事实证据](../../web/pipeline/tests/test_collector_deferred_budget.py#L198)、[旧barrier后续空扫描仍保留](../../web/pipeline/tests/test_collector_deferred_budget.py#L235)应保持。未来若给增量接预算，未执行或超期详情绝不能标VERIFIED/成功解除barrier，先前已核验staging不能删除；不能简单在for循环外加一个抛错就放弃这些保存步骤。

**本最小补丁不修改collector_incremental_runtime.py、bootstrap、ledger/屏障格式或bucket/发布协议。** 区域canonical key不在[增量pending映射:323](../../web/collector_runtime.py#L323)中，不能假称给区域预算就实现了增量时间预算。测试须证明既有其他来源pending/ledger未被区域失败触及。

## 静态容量与数字依据

默认每地区5关键词×2类型=10个scoped请求，最多10详情。national fallback是**该地区自己的另一个stage**，最多10×3=30请求，而不是CLI跨地区共用一次。当前[sleep:1409](../../web/collector_runtime.py#L1409)、[1449/1450](../../web/collector_runtime.py#L1449)、[1497](../../web/collector_runtime.py#L1497)及session warmup1秒：

| 单stage分支 | 请求数（含主页） | 固定等待 | 按原timeout参数组成的名义串行值 | 210秒工作预算扣等待 |
|---|---|---|---|---|
| 区域primary且选满10详情 | 10搜索＋10详情＋1＝21 | 10×4＋10×4＋1＝81秒 | 10×90＋10×30＋30＋81＝1311秒 | 129秒 |
| 区域fallback各query满3页且10详情 | 30搜索＋10详情＋1＝41 | 30×4＋10×4＋10×4＋1＝201秒 | 30×90＋10×30＋30＋201＝3231秒 | 9秒 |
| fallback各query首屏完整空 | 10搜索＋1＝11 | 10×4＋1＝41秒 | 10×90＋30＋41＝971秒 | 169秒 |

名义串行值不是实测/墙钟上界，DNS、持续响应、解码/解析及缓存I/O不由这些timeout保证。primary工作余量129给21个请求及解析；密集fallback只剩9给41个请求及解析，正常完整完成**没有证据，NO-GO作保证**。重试会重扫现有范围，当前区域阶段没有持久分页续跑水位，不能声称第二次必然补齐；两次都耗尽就沿现有策略降级，保留最后核验状态，不放宽完整性或强减查询。

医院/增量也不能直接套这一个值：[TJZYEFY retry:71](../../web/pipeline/scripts/sync_tjzyefy_market_research.py#L71)最多2次，[TEDA:71](../../web/pipeline/scripts/sync_teda_market_research.py#L71)最多3次，底层默认30秒、retry间固定sleep；增量每源最多12详情是数量预算，不是时间预算。实际重试是否发生、HTTP时延分布、缓存完成时间及当前来源健康均未核实。

## 唯一最小接口与修改文件（待授权，未实现）

| 文件 | 必要改动 |
|---|---|
| web/pipeline/scripts/sync_regional_ccgp.py | 只把既有CliBudget参数化为total/work/可信started_at，默认仍900/840/60；保留已有异常和request_timeout/check/sleep接口，不另造引擎。现有session的可选budget可直接复用，warmup已经专门重抛该预算异常 |
| web/collector_queue.py | process入口记录本地monotonic原点，原payload/epoch/owner检查之后仅为注册区域stage建立270/210/60预算并传run_stage；预检耗时扣同一个原点。其他stage/增量/publish原调用方式不变，不修改Queue配置、lease、重试或排队策略 |
| web/collector_runtime.py | run_stage与_run_regional_market增加可选budget；只在已注册区域路径传session/详情timeout、检查sleep和解析返回、canonical写入前检查。预算异常不得落入普通错误catch继续循环；写前转固定CollectorStageBlocked，复用原FAILED/503/健康失败逻辑 |
| web/pipeline/tests/test_regional_cli_completeness.py | 验证参数化仍保持CLI900/840/60及原行为，新增数值/原点边界，不更改CLI合同 |
| web/pipeline/tests/test_runtime_source_parity_behavior.py | 区域primary/fallback假时钟、超期内容丢弃、旧canonical/其他源pending不变、合法空与fallback_required语义及提交边界 |
| web/pipeline/tests/test_collector_orchestration_behavior.py | 预检耗时不重置、首次失败保留重试、第二次耗尽立即降级推进、foreign/owner拒绝、其他stage不被注入预算 |

`request_timeout(cap)=min(cap,210−elapsed−1)`，剩余<=1拒绝；sleep不足原delay+1时拒绝，不把4秒压短后发请求；open/read/解码/解析后复查；后续业务请求与sleep为0。保留原warmup30/search90/detail30上限，普通网络错误不是全host故障。错误诊断只加固定阶段/原因和有界预算数字，不持久化原始URL/查询/异常文本。

工作完成后才进入60秒收尾；提交前检测超期，旧canonical不能被新部分事实覆盖、未解决pending不能清理。`_cached_list`可能初始化缺失canonical为已有仓库seed，[436](../../web/collector_runtime.py#L436)，这是现有bootstrap路径，不是本轮新核验或成功时钟；不宣称所有失败都零缓存元数据/seed写入。

## 状态、恢复与不可承诺项

- **写前预算耗尽**：拒绝本次新事实，按已有CollectorStageBlocked retryable=True→FAILED/503→既有投递重试。保留最后成功时钟/旧canonical/pending；第二个普通attempt失败即现有终局降级并推进其他来源，不新增第三次业务attempt。显式旧恢复例外仍保留。
- **已完整核验并进入canonical写入后才迟到**：不能再抛“写前预算未完成”并声称旧值不变。仅增加有界overrun/写入阶段诊断，沿既有已知提交结果与健康/状态分支完成，不把COMPLETED提升为“按时完成”。不能自动回滚或重放写入。
- **缓存写入/清理/健康保存异常**：沿现有失败路径并明确canonical_mutation_possible/结果未知，不伪称零写入或数据库事务。不能为了适配预算增加新健康终态或吞错标成功。现有SDK是否可靠报错/持久化确认属于运行事实未核实，本轮不重开SDK审计来补这个缺口。
- **owner变化**：保留Queue前后检查和现有日期检查；[_latest_stage_state_for_update:610](../../web/collector_runtime.py#L610)不是跨key的owner fence。budget不创造atomic owner/CAS；若要求owner变化后绝不写旧阶段结果，当前最小方案NO-GO，必须独立解决写入协议，不能以加一次get假称已解决。
- **硬中断**：同步HTTP/cache可能不返回，270/60预留不能强制执行finally。保持现有900秒owner活性恢复与平台后续投递；不改租约、不用future冒称取消，不承诺硬终止后即时收尾。

## 后续验收与GO/NO-GO

| 验收目标 | 门槛/决策 |
|---|---|
| 仅本地实现上述区域协作式准入 | GO，需明确这6文件代码授权；必须使用既有本地cache/transport桩并阻断网络/真实SDK |
| 原点/时间耗尽 | Queue预检已耗时不能重置；<=1余量零新HTTP；warmup/sleep/HTTP/解析耗尽后零后续请求，新事实不入canonical |
| 状态/数据安全 | 首次预算失败可重试，普通第二次失败立即降级推进；旧canonical/成功时钟/其他源pending不变；完整空、primary→fallback与terminal replay原行为保持 |
| 提交后迟到/未知 | 不谎报旧值未变、不自动回滚、不把已提交事实按写前失败重复处理；不改健康终态/lease/Queue策略 |
| CLI/增量回归 | CLI默认值、已有48用例保持；既有12/13详情、硬停、旧barrier与ledger先后序测试保持。实现后才跑必要回归和10/3，数量按实际结果记录 |
| 全runtime、增量/事件/publish一起接入 | NO-GO，本最小方案不覆盖；不能用区域测试代表其余来源 |
| 密集fallback/270或300秒必完整、真实持久化/取消/原子提交 | NO-GO，只有静态容量和源码边界，没有运行时能力/时延/一致性证据 |

本轮没有新行为复现，不把这些设计缺口写成新线上bug。若后续实现需要改重试次数、健康/租约/Queue协议或私有SDK才能通过，停止并给证据NO-GO，不追加模拟层或改合同凑通过。

## 本轮证据和权限

静态引用、预算算术、源文件与450份起点data/fixture/旧验收文件哈希校验见[证据索引](validation/runtime-f2-contract-2026-11-07/manifest.json)。应用/测试/workflow/锁/计划未变。既有CI8模块94项、58e7e6b的1079/10/3是历史版本结果，本轮未重跑。没有应用/SDK导入执行、联网、运行日志/凭据/环境值查询或云端/缓存/数据库/函数/Queue/模型调用，没有新环境/路由、权限变更、部署/推送、workflow触发或运行数据/原始历史数据/快照写入。旧验收文件仅随完整性检查做字节哈希，不解析其日志内容。

apply_allowed=false、migration_usable=false；SDK仍CLOSED NO-GO。下一轮仅在明确本地代码授权后按上述单一范围推进，不把本合同当已实现。详见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
