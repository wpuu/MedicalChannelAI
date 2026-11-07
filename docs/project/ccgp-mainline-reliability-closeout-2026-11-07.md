# CCGP主链F1/F2/F3工程收口与唯一后续优先项

2026-11-07（Asia/Shanghai）。本轮仅离线静态审查。起点 **1f40e91**，当前应用代码 **fea6fc70350b17366f20a86eac9ec02396a36fa9**，现有工作树`/workspace/MedicalChannelAI-p0`、分支`codex/p0-reliability-contracts`。开始工作树干净，仅根代理，无相关在途工作；另一个3216fd9工作树未改。前台09:17:03Z开始、09:37:03Z截止。已读取最新用户指令、working-protocol/current-state/checkpoint/next-task、发现/事件/区域止损/区域预算/增量/publish实现、旧收口及行动雷达验收合同。

**结论：现有实现方向正确，已完成的局部预算、完整性和回执保护不重复施工；不能宣称全项目F1/F2/F3或真实交付完成。唯一下一优先项R1：离线复现并最小修复Queue CCGP发现/事实及事件共用路径的单次stage明确拒绝止损，保留安全诊断。** 当前只授权文档，下一轮四文件代码方案须用户明确选择后实施。

## 版本与证据的含义

- **1202项Python、10/10模板、原CLI3/3是fea6fc7已有通过结果，本轮未重跑。** 读取冻结JSON摘要，核对五文件SHA256与当前代码一致；原CLI门禁仍隔离空事件watch，不是非空事件端到端验收。此前1157/1181/1145等只归其对应版本，不叠加冒充新结果。
- 最新源码/行号/哈希见[110处引用](validation/ccgp-mainline-reliability-closeout-2026-11-07/source-references.json)；[八组函数AST版本绑定](validation/ccgp-mainline-reliability-closeout-2026-11-07/version-bindings.json)确认已验收实现仍在：CLI主函数58e7e6b、CliBudget参数化bba3716、区域R1函数4916d69、事件5d2fe85、发现fea6fc7、publish及增量执行体a352b7a。相同函数AST不意味着当前部署或依赖已核实。
- 本轮只执行标准库源码/AST/JSON/哈希及git元数据检查，不导入应用、SDK，不执行测试、采集、模型或模拟。595份既有data/fixture/历史artifact字节保持；455份web/workflow文件保持。旧日志artifact仅计算字节哈希，不解析日志；未打开实际环境值或凭据。清单见[manifest](validation/ccgp-mainline-reliability-closeout-2026-11-07/manifest.json)。
- 真实Preview部署、消费者消息SHA、来源恢复、实际延迟/完整召回、真实持久化及客户交付全部**未核实**。本地mock、两键读回、配对写调用返回、权威ACK、bucket完成均不替代这些证据。
- `apply_allowed=false`、`migration_usable=false`。SDK、硬取消/严格时限、跨键原子提交/自动回滚及崩溃持久回执强保证保持 **CLOSED NO-GO**，不重开或用模拟补证。

## 实际覆盖矩阵

“已实现且本地验证”均指上述版本绑定的既有证据；不是本轮测试、真实云端验收或全量召回保证。

| 范围 | 最新源码定位 | 实际状态与边界 |
| --- | --- | --- |
| 区域CLI F3完整性 | [完整性汇总](../../web/pipeline/scripts/sync_regional_ccgp.py#L730)、[安全准备/替换](../../web/pipeline/scripts/sync_regional_ccgp.py#L323)、[退出码](../../web/pipeline/scripts/sync_regional_ccgp.py#L384) | 已关闭：部分发现/fallback/详情失败不覆盖records，合法完整空可成功；report别名保护保留。仅配置范围的区域CLI，不泛化成所有CLI完整性已完成 |
| 区域CLI F1与F2 | [预算原语](../../web/pipeline/scripts/sync_regional_ccgp.py#L68)、[分类器](../../web/pipeline/scripts/sync_regional_ccgp.py#L309)、[main](../../web/pipeline/scripts/sync_regional_ccgp.py#L390) | 已实现且本地验证：实际host单次调用止损，普通超时不封全host；900/840/60、候选准备后提交、迟到/未知分别报告；无跨文件事务或共享冷却 |
| 区域CI接线 | [paths](../../.github/workflows/regional-medical-refresh.yml#L29)、[set-e及模块](../../.github/workflows/regional-medical-refresh.yml#L59) | 已接线，6d4eb1b当时8模块94项本地通过；本轮未运行workflow或GitHub runner |
| Queue原点与路由 | [入口原点/epoch](../../web/collector_queue.py#L429)、[限定预算分支](../../web/collector_queue.py#L494) | 已实现且本地验证：原点含预检/stage准入，增量含lease，不接受payload deadline；25 deep中18个接预算，8增量中1个接预算 |
| CCGP发现/事实 F2、完整性 | [发现调用](../../web/collector_runtime.py#L729)、[候选上限](../../web/collector_runtime.py#L764)、[失败拒绝](../../web/collector_runtime.py#L801) | 已实现且本地验证：270/工作150/准备60/尾部60；发现超计划候选在详情前拒绝，watch超计划或六片容量拒绝，不截断后称完整；原始候选范围仍受计划/第一页发现边界约束，不是全站召回 |
| CCGP基线与双键准备 | [旧seed初始化/committed优先](../../web/collector_runtime.py#L714)、[写入/读回](../../web/collector_runtime.py#L687)、[共同截止](../../web/collector_runtime.py#L838) | 已实现且本地验证：staging写→匹配读回→watch写→匹配读回，截止min(开始+60,t0+210)；只有两键按时匹配才PREPARED_LOCAL_READBACK。不是配对canonical提交；旧seed可能已写，部分准备不称零写或回滚 |
| event1–6 F2与配对提交 | [完整片循环](../../web/collector_runtime.py#L924)、[event6门禁](../../web/collector_runtime.py#L967)、[单键配对写](../../web/collector_runtime.py#L984) | 已实现且本地验证：270/180/单批30/尾部60；完整片才保存、前五片只staging，第六片核对前序COMPLETED、原records及pending再单键提交records/events；保留兄弟staging。写返回不等于真实持久化 |
| CCGP健康与重投 | [七阶段成功时钟](../../web/collector_runtime.py#L2186)、[完成/降级重投](../../web/collector_runtime.py#L525)、[Queue依赖降级](../../web/collector_queue.py#L462) | 已实现且本地验证：ccgp准备成功仍EVENT_VERIFICATION_PENDING，七阶段完成才成功；首次失败可重试、最终降级推进；已完成重投不重扫。未核实的状态保存/硬停仍依赖原恢复协议 |
| 区域Queue F1/F2 | [host回调](../../web/collector_runtime.py#L1537)、[详情止损](../../web/collector_runtime.py#L1700) | 已实现且本地验证：主/备用270/210/60；warmup反馈与实际host拒绝集合、marker/包装cause；普通超时/503/解析失败不封整个host。旧R1已修，不再报修 |
| tjzyefy增量F2/pending | [限定源](../../web/collector_incremental_runtime.py#L524)、[URL保存](../../web/collector_incremental_runtime.py#L715)、[pending分支](../../web/collector_incremental_runtime.py#L833) | 已实现且本地验证：270/180/URL30/最终化60，12数量预算/carryover、staging→本URL barrier→ledger/finally、兄弟staging及未知恢复保留。bucket COMPLETED且snapshot_refreshed=false不是源完整成功 |
| deep/tjzyefy publish调用者 | [210工作截止](../../web/collector_runtime.py#L1786)、[严格ACK](../../web/collector_runtime.py#L1875)、[两份副本](../../web/collector_runtime.py#L2023)、[增量31秒准入](../../web/collector_incremental_runtime.py#L897) | 已实现且本地验证：deep270/210/60；增量同parent，未误用180作为publish截止。NOT_ATTEMPTED/UNKNOWN/CONFIRMED与Node/Python副本分别保存，合法迟到ACK不降成未提交；尾部失败保留确认事实 |
| pending/版本/权威协议 | [提交前pending](../../web/collector_runtime.py#L321)、[publish配对优先](../../web/collector_runtime.py#L1909)、[权威先持久写后ACK](../../web/api/public-snapshot.js#L128)、[微秒版本](../../web/api/_snapshotRevision.js#L3) | 原实现保持：源提交先核对pending，降级发布可使用旧已验证canonical；不是publish禁止所有旧pending。相同版本幂等/冲突校验不变；本轮未运行Node/JS或真实数据库 |
| CCGP同stage F1 | [发现通用catch](../../web/pipeline/scripts/sync_ccgp_query.py#L235)、[事实通用catch](../../web/collector_runtime.py#L787)、[事件搜索catch](../../web/pipeline/scripts/sync_ccgp_query.py#L129) | 静态缺口R1：明确拒绝仍可能进入下一同host请求；时间预算不能替代拒绝止损。未做行为复现或宣称当前线上限流 |
| 其他F2及共享协调 | [余下stage默认路径](../../web/collector_queue.py#L505)、[其他增量清预算](../../web/collector_incremental_runtime.py#L529) | 未覆盖R2：7个deep、7个其他增量；共享host跨进程冷却/Retry-After仅合同要求、未实现。未覆盖不等于当前已超时，不能机械扩预算 |
| 真实部署与交付 | [版本绑定历史JSON](validation/ccgp-mainline-reliability-closeout-2026-11-07/historical-gates.json) | 运行事实未核实R3；当前离线结果不放行Preview/Production或客户交付 |

## 调用链与故障保护

Queue入口原点/epoch→owner/预检→ccgp stage准入→旧seed与committed基线→关键词/类型发现→详情核验→完整性、merge、watch、digest→STAGING写/读回→WATCH写/读回→状态/失败健康→owner/重试/推进event1。准备不完整仍503，不提前写COMMITTED、不刷新成功时钟；首键已写或第二键未知的回执保留，不盲补或回滚。

每个event stage沿独立消息原点→同片最多5项目→每项目更正/终止搜索及详情→完整片merge→event1–5 staging或event6前序/pending门禁与单键配对提交→状态/七阶段健康→Queue尾部。当前事件通用详情失败仍可生成保守discovery_event，但任一failures最终阻止当前片提交；不能把这个内部fallback说成已发布部分新事件。预算超期则已有专门异常路径，不能再制造迟到fallback。

publish读取committed配对优先及其他源canonical完整集→merge/build/健康/JSON与digest→LATEST候选写/读回→权威PUT→HTTP200、ok/durable_committed严格true、精确版本及整数数量ACK→Node/Python副本状态→原stage或bucket/heartbeat/reconcile/tick/owner/lease。确认、未确认、候选写、副本重试与尾部未知分别处理；snapshot_refreshed=false不能证明零写。

区域CLI/Queue及增量保持独立路径。源失败不抹去旧canonical，未解决pending阻止该源部分新事实提交；已核验兄弟staging保留。Queue普通第二次失败立即降级/依赖跳过，publish失败仍FAILED且按原owner释放；[原有独立调度与释放顺序](../../web/collector_queue.py#L519)不因新增预算被跳过。原协议不是跨调用原子owner fence或崩溃可靠回执，已关闭强保证不再重新审计。

## 三项剩余缺口与决策

### R1 / P1：CCGP明确拒绝未在同一stage内止损（唯一下一优先项）

**静态依据：** discover_candidates在[通用catch](../../web/pipeline/scripts/sync_ccgp_query.py#L235)记failure、candidates=[]后继续下一notice type；_run_ccgp的[关键词循环](../../web/collector_runtime.py#L729)没有跨关键词拒绝表，[详情catch](../../web/collector_runtime.py#L787)只记failure后继续下一候选。scan_events在[搜索catch](../../web/pipeline/scripts/sync_ccgp_query.py#L129)continue第二类型，在[详情catch/fallback](../../web/pipeline/scripts/sync_ccgp_query.py#L160)后继续候选及类型；[runtime项目循环](../../web/collector_runtime.py#L924)只在两次搜索都失败后才立即阻断，因此一次明确拒绝仍有额外同host请求路径。以上均未调用现有access_block_reason或维护stage局部拒绝host。AST证据见[control-flow](validation/ccgp-mainline-reliability-closeout-2026-11-07/static-control-flow.json)。

搜索helper本身已识别[限流marker](../../web/pipeline/medical_channel_pipeline/ccgp_discovery.py#L244)，详情helper已保留[HTTP cause](../../web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1448)；问题在调用者仍按普通错误继续，不是helper没有分类素材。事实详情adapter前还没有区域路径已有的marker检测。完整性门禁仍在，不能报告为部分事实已泄漏进canonical。

同一失败处理链还需保持安全诊断：_run_ccgp[拼接原异常message](../../web/collector_runtime.py#L807)进入CollectorStageBlocked，再经[_mark_failed](../../web/collector_runtime.py#L639)保存；截取300字符不是固定原因码/有界哈希。事件/区域已有安全汇总，不应重复修其已通过的诊断，也不应复制此原文拼接到新拒绝路径。这里仅静态发现，未读取或证明存在任何真实敏感值泄漏。

**影响：** 拒绝后增加同入口负担和预算消耗，违背F1本轮扇出止损合同；普通超时与明确拒绝混同也不利于诊断。当前是否发生真实限流、请求次数及延迟均未核实。

**唯一最小后续四文件：** `web/collector_runtime.py`、`web/pipeline/scripts/sync_ccgp_query.py`、`web/pipeline/tests/test_runtime_source_parity_behavior.py`、`web/pipeline/tests/test_ccgp_events.py`。只针对Queue ccgp/event1–6入口显式启用；在既有runtime函数中创建一次stage的host字典，通过helper可选参数传递，复用现有access_block_reason、RATE_LIMIT_MARKERS、failure_row/failure_summary，反向区域依赖必须函数内延迟取得，不能引入循环。发现跨关键词和事件跨项目必须共享同一stage范围；不同stage/重试不继承拒绝集合，不新建引擎或共享协调器。

**行为验收：** 先在现有runtime/helper入口用原MemoryCache/transport桩、冻结样本、假时钟和临时目录复现；HTTP401/403/429、marker及包装cause明确拒绝后同实际hostname后续业务请求为0；搜索、www及裸域不合并，合法另一详情host仍可独立核验。搜索拒绝可立即拒绝该不完整stage；不得借止损修改独立来源执行。普通及时TimeoutError/URLError、503、解析错误不封整个host，原有界处理及及时普通事件fallback保持；拒绝/被跳过详情不生成新核验或fallback。覆盖两个类型、两个关键词/同host详情、同片两个项目、event1/event6、下一次stage重试、合法空/完整成功、无guard CLI兼容和两种导入顺序。当前预算/配对/pending/健康/seed及写后未知回执均保持；诊断只固定原因/计数/最多5个哈希，无URL/标题/项目号/异常正文。代码变化后才运行必要Python回归和10/3，记录真实新增数，不机械沿用1202。

当前轮不具备代码授权；只形成上述方案。下一轮必须明确四文件本地离线授权。若不能复现或已修给证据关闭；需改helper、Queue/lease/健康/pending/版本协议或超出四文件则NO-GO，不扩范围。共享进程冷却、Retry-After、重定向逐跳拦截和其他来源止损不在此子项。

### R2 / P2：F2仍是局部覆盖，未覆盖来源没有新的累计时间预算

[25个stage](../../web/collector_runtime.py#L186)与[Queue分支](../../web/collector_queue.py#L494)交叉核对：18个已接预算；剩余`tjmugh/tjnothop/tjzyefy/tjzyefy_intent/tjzxfc/teda/tjfch`七个deep仍原路径。八个增量源仅tjzyefy接parent，其余`tjmugh/tjnothop/teda/tjfch/tjfch_test/tjzyefy_intent/tjzxfc`七个未接，runner主动清除不支持源budget。清单见[coverage](validation/ccgp-mainline-reliability-closeout-2026-11-07/coverage.json)。

这是静态覆盖缺口，不是已复现超时/硬停故障。已经接入的CCGP也只保证有界拒绝和诚实回执，不保证默认完整范围按时完成或全历史召回；不得放宽完整性或把maxDuration当工程预算。共享host跨进程冷却/Retry-After也尚未实现，但不是重开硬取消/原子状态分支的理由。

最小后续：R1关闭后，依据产品范围与实际证据只选一个来源先做文档合同；明确请求/sleep/保存/健康/恢复及其他源独立边界，再确定是否有安全且获授权的最小实现。现在不指定未经来源审查的预算数值或代码扩散文件。行为验收至少含晚到事实/None、pending/兄弟staging/成功时钟和安全拒绝，不把未执行标VERIFIED；需要另行单源合同及后续代码授权。本轮不推荐同时展开。

### R3 / P1发布放行阻断：最新代码缺少真实运行与交付证据

fea6fc7的1202/10/3是本地离线结果，历史云端记录不是当前部署。当前禁止云端读取与触发，故无法核实项目/部署/消费者SHA、epoch、实际canonical/pending/健康、水位、权威快照读回、副本/尾部状态或客户动作。此项为证据门槛，不是新复现代码bug。

最小后续是R1必要离线闭环之后，另行形成**一次范围明确、可以审核的现有d周期Preview验收放行包**，逐项列版本身份、请求/写入上限、退出条件、可读数据和副作用、来源完整性、单源降级/旧canonical/pending、精确公开版本与内容读回、ACK/副本/stage/bucket/lease的独立判据及恢复边界。只读核实、部署、真实采集触发和读回须分别具备明确授权；不能因其中一个通过而放行其余，也不能绕过SDK CLOSED NO-GO。当前不访问任何外部目标或申请权限；不足即NO-GO。

## 本轮收口及权限

已完成：最新版本绑定的覆盖矩阵、主链调用顺序、静态拒绝路径、三项缺口与唯一R1四文件方案。静态验证110处引用、8组函数AST绑定、595份保护输入、455份源码/配置不变，以及文档范围、完整性清单与本轮未执行测试的声明。详细结果见[validation-summary](validation/ccgp-mainline-reliability-closeout-2026-11-07/validation-summary.json)。未修改应用、测试、workflow、依赖锁或任何计划/权限。

未完成：R1行为复现/修复、R2其余源合同、共享冷却/Retry-After及R3真实验收。没有外网、应用/SDK/模型/测试执行、实际环境值/凭据/运行日志读取、真实云端/业务/缓存/数据库/函数/Queue访问；没有新环境/路由、部署/推送/workflow触发或运行数据/原始历史数据/公开快照写入。

[下一轮完整任务](next-task.md)仅在用户明确选择R1四文件授权后执行。当前界面无法生成该按钮；不以弹窗/链接冒充，提供可复制完整提示词。推荐**GPT-6.1 Sol xhigh**，实际设置**未核实**。
