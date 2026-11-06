# tjzyefy增量时间预算与pending恢复合同（仅离线方案）

2026-11-07（Asia/Shanghai）。起点`d6a9cee`，区域代码`bba3716`；现有分支codex/p0-reliability-contracts、工作树干净，检查时仅根代理，无相关在途工作。开始2026-11-06T18:49:48Z，前台截止19:09:48Z。按最新用户授权只静态阅读源码/既有测试、修改文档和新增artifact；没有导入/执行应用、SDK或测试。1098/10/3为bba3716已有结果，本轮不重跑、不算新增通过。

## 唯一决策与预算

**唯一推荐：下一轮经明确授权，只实现Queue `mode=incremental, source_id=tjzyefy`的协作式请求准入、逐URL保存观察及超期恢复。** 复用既有CliBudget，逻辑总270秒，业务工作180秒，尾部单URL保存预留30秒，最终化至少预留60秒。不给其他源、deep医院阶段、事件或publish内部接预算；不修改任何Queue配置、lease、ledger/barrier格式或健康终态。增量保留原SDK投递/正常tick恢复，不套用区域deep的两次attempt后DEGRADED规则。

| 窗口/规则（全部拟议，尚未实现） | 依据与准确含义 |
|---|---|
| `t0`：process_collector_payload入口monotonic | [queue:413](../../web/collector_queue.py#L413)已有原点；往增量分支传同一个对象/原点，覆盖schema/epoch、日期/bucket、lease、bootstrap和缓存预检。不得从payload读deadline，不在run_incremental_source重新计时 |
| 逻辑总270，外层名义余量30 | [函数配置300:18](../../web/vercel.json#L18)减30；不是实际部署上限证据，也没有覆盖进入process之前的SDK分发耗时。消息lease300见[API:38](../../web/api/collector-queue.py#L38)，它不等于可用工作时间 |
| 业务截止`t0+180` | 270−30单URL尾部保存−60最终化=180；业务包括发现/详情请求、重试等待、解码解析、规划及此前已完成保存的实际耗时。不是照搬区域210。所有业务返回/解析包括显式非事实None都要在180前核验 |
| 单URL保存观察上限30，尾部最迟`t0+210` | 一条事实已有“staging→本URL barrier→ledger”三次保存，[incremental:598](../../web/collector_incremental_runtime.py#L598)；须给一个已准入单元留独立尾部空间。30是明确的保守预算政策，**没有实测缓存P95，也不是三次SDK写能在30秒完成的事实**。每个单元保存准入截止`min(save_started+30,t0+210)`；每一步调用前后检查，超期不再进入下一成功状态变更。前面各URL保存也消耗180工作窗口，不能给12个URL各新增30秒全局预算 |
| 最终化准入不晚于`t0+210`，逻辑最终截止`t0+270` | 已无时间中断、已知保存完成、范围完整才进入原有canonical/清理/健康/发布/bucket链；60是最低名义预留，不要求等到210才开始，也不为每个操作重置60。失败收尾同样消耗总预算 |
| HTTP上限30，最多2次，3秒原间隔保持 | [底层:150](../../web/pipeline/medical_channel_pipeline/tjzyefy_discovery.py#L150)、[retry:31](../../web/pipeline/scripts/sync_tjzyefy_market_research.py#L31)、[retry helper:71](../../web/pipeline/scripts/sync_tjzyefy_market_research.py#L71)。每次`timeout=min(30,t0+180−clock−1)`；余量<=1拒绝；sleep余量<=3+1拒绝，不能压短原间隔。未耗尽的普通网络错误保留原一次重试，不扩做host冷却/Retry-After |

[CliBudget:68](../../web/pipeline/scripts/sync_regional_ccgp.py#L68)已有可注入monotonic/sleep、可信started_at、request_timeout/check/sleep_checked；保持CLI900/840/60及区域270/210/60。单URL保存仅用同一clock记录局部观察截止，不另建预算类、模拟器或线程/future层。

**GO只表示可在下列六文件离线实施并行为验收，不是当前代码已有增量时间预算。** 硬取消、严格270/300秒退出、每次缓存写timeout/取消、跨key原子提交/owner fence、12条必然按时完整、真实部署或持久化保证全部NO-GO。公开SDK工作流保持CLOSED NO-GO，不为本方案重开。

## 一次tjzyefy消息的现有调用链

| 边界 | 当前实现与应保留的事实 | 最小预算处理（拟议） |
|---|---|---|
| tick与调度 | [queue:339](../../web/collector_queue.py#L339)先排下个tick再选择来源；[scheduler:146](../../web/collector_incremental_scheduler.py#L146)只有成功入Queue的attempt才参与间隔。pending不走quiet双倍退避，见[scheduler:80](../../web/collector_incremental_scheduler.py#L80) | 不改tick、选择、公平性、attempt、间隔或调度。某源503不能停止已排队的独立tick/其他源 |
| 身份与日期 | [queue:416](../../web/collector_queue.py#L416)跨epoch在cache前拒绝；[queue:272](../../web/collector_queue.py#L272)校验source/有时区时钟/bucket/中国同日。payload时钟只用于身份，传给扫描的是delivered_at，runner再按交付时钟计算实际bucket；跨bucket重投不能声称完成原payload bucket | 继续零副作用拒绝foreign/非法/跨日/错bucket；不把payload时钟当monotonic或重置预算 |
| lease | [queue:229](../../web/collector_queue.py#L229)检查deep/incremental owner、set/readback再查deep；[queue:267](../../web/collector_queue.py#L267)finally只释放匹配scan_id；TTL[namespace:27](../../web/collector_namespace.py#L27)900秒 | 原检查/释放顺序保持；不是跨key原子锁。预算异常仍经finally释放，硬停不能保证finally执行；不新增续租或owner CAS |
| 预检与发现 | [queue:299](../../web/collector_queue.py#L299)预bootstrap不带discovered；[bootstrap:108](../../web/collector_incremental_bootstrap.py#L108)直接DISCOVERY_REQUIRED，不请求。真正扫描在[incremental:539](../../web/collector_incremental_runtime.py#L539)一次发现，传同一结果给bootstrap | discovery入/返回/parse后检查，迟到结果不得bootstrap为新VERIFIED，不再发详情。bootstrap可沿原有近期canonical核验证据修复，不能把它说成本轮新网络核验 |
| tjzyefy适配 | [发现:301](../../web/collector_incremental_runtime.py#L301)最多20候选；[详情:311](../../web/collector_incremental_runtime.py#L311)retry helper→官方parser，支持的非事实错误转None | 可选budget只给tjzyefy适配器。parse返回与非事实异常转None之前均检查180，迟到None不能解除屏障 |
| 数量与carryover | [policy:25](../../web/collector_incremental.py#L25)60分钟/24小时/12详情；[planner:309](../../web/collector_incremental.py#L309)48小时carryover、[334](../../web/collector_incremental.py#L334)最多3个预留槽。不是时间限制，也不是全历史覆盖 | 不改变12/20/48小时或排序；时间未执行的selected仍在已有ledger/barrier中保持可补做，不制造VERIFIED |
| 预存屏障 | [incremental:573](../../web/collector_incremental_runtime.py#L573)selected+deferred并入旧barrier，先保存barrier、ledger，再读staging | 在任何详情请求前确认这组预存正常返回；中途错误/结果未知停止业务，不能声称全量保护已持久化 |
| 逐URL保存 | [incremental:598](../../web/collector_incremental_runtime.py#L598)核验→有事实先staging→本URL barrier删除→内存ledger成功→finally保存ledger。非事实无staging，仅解除自己的URL | 进入单元前确认解析及时；保存各步调用前后检查局部截止，保持原写序和finally。超期停止后续成功变更，转既有失败/pending保存路径；不删除已保存兄弟记录。已发出写迟到只能结果未知，不把新时间检查包装成原子保证 |
| 原失败/待补分支 | [663](../../web/collector_incremental_runtime.py#L663)本轮失败503不开bucket；[677](../../web/collector_incremental_runtime.py#L677)仅旧pending/数量deferred可200 COMPLETED、snapshot_refreshed=false | 时间中断单独503/固定预算原因，bucket不完成；不能落到“仅pending”分支冒充本轮完成。已有数量deferred分支保持200但不代表整源成功 |
| 完整源提交 | [702](../../web/collector_incremental_runtime.py#L702)无失败/未解决barrier后合并canonical→清pending→成功健康；[_cache_set:296](../../web/collector_runtime.py#L296)写canonical前验证barrier，set后才清理 | 原序不变；180前核验且保存完成、210前最终化准入、270前canonical调用准入才可提交；不能在_cache_set内部插入预算异常或改清屏障协议 |
| 发布与bucket | [724](../../web/collector_incremental_runtime.py#L724)同步_publish_snapshot_if_ready；[504](../../web/collector_incremental_runtime.py#L504)只将CollectorPrecondition转“未刷新”；[740](../../web/collector_incremental_runtime.py#L740)发布后才标bucket | 发布前至少余31秒才准入（原HTTP cap30+1），还需总预算检查；不是整个publish有31秒保证。不准入返回503，不能假造publish_result/标bucket完成；发布正常返回后保留既有完成分支并记录迟到，不假称撤销 |

## 现有保护、确切缺口与运行未知

1. **已有且不重复修复**：旧canonical/失败源成功时钟保护、12/13条延后、已核验兄弟staging、逐URL非事实证据、硬停后carryover、空扫描不清旧pending。源码如上；既有[12条测试:89](../../web/pipeline/tests/test_collector_deferred_budget.py#L89)、[13条:106](../../web/pipeline/tests/test_collector_deferred_budget.py#L106)、[周期重验延后:139](../../web/pipeline/tests/test_collector_deferred_budget.py#L139)、[硬停:198](../../web/pipeline/tests/test_collector_deferred_budget.py#L198)、[49小时空扫描:235](../../web/pipeline/tests/test_collector_deferred_budget.py#L235)。硬停例当前用tjzxfc，不冒称已有tjzyefy专用时间中断测试。
2. **设计缺口，尚未行为复现**：增量runner及tjzyefy retry不接budget，初次3秒sleep在try外、每个详情异常只累加后继续；HTTP/解析迟到目前没有拒绝门槛。不是已确认线上超时故障，也不是区域补丁失败。
3. **现有恢复边界**：未执行的周期重验可能仍带旧VERIFIED，必须复用[_mark_budget_deferred:74](../../web/collector_incremental_runtime.py#L74)处理剩余selected，以便消失于下次index仍可carryover。不得更新last_verified_at或把未请求URL记为详情成功。已有保留/48小时上限保持，超过窗口不自动清barrier或承诺必定排空。
4. **运行未知/NO-GO**：真实SDK是否可靠报错、请求实际时延/持续读/缓存返回、部署版本、租约并发、原子性、来源健康未核实。同步[response.read:162](../../web/pipeline/medical_channel_pipeline/tjzyefy_discovery.py#L162)及[decode:165](../../web/pipeline/medical_channel_pipeline/tjzyefy_discovery.py#L165)不能由socket timeout推导整个调用上界。publish还含[快照set/读回:1745](../../web/collector_runtime.py#L1745)、[权威写入:1759](../../web/collector_runtime.py#L1759)、[公开副本:1763](../../web/collector_runtime.py#L1763)，只检查入口不构成完整publish预算。

## 超期、提交与恢复的唯一规则

- **发现前/发现返回或解析迟到**：无后续业务请求、不使用迟到发现结果引导新ledger核验；保留旧canonical/pending/成功时钟，固定预算失败503，不完成bucket。允许已有身份/lease/元数据写入，不称零缓存写。
- **规划预存完成后的时间中断**：剩余selected（包括尚未准入、sleep不足、迟到fact/None的当前URL）复用_mark_budget_deferred，与plan.deferred同样保留barrier；保存ledger，保留已正常返回的兄弟staging。停止业务，失败健康保持最后成功时钟，返回503/INCREMENTAL_TIME_BUDGET_EXCEEDED、snapshot_refreshed=false，不发布、不标bucket完成。不要为每条未执行URL伪造独立HTTP失败。
- **及时核验的单URL单元**：解析在180前完成才准入，保存截止为min(save_started+30,t0+210)；保持既有写序和finally。每步调用前后检查；staging后过期不得再解除本URL barrier，barrier返回后过期不得再构造成功ledger。当前URL和剩余selected复用失败/延后路径，正常返回的staging保留，整次503、不canonical提交。非事实同样不能在解析迟到时解除屏障，及时非事实也只解除自己的URL。
- **在途保存写迟到**：时间检查不能阻止已经发出的barrier/ledger写入。此时不报告该URL按时VERIFIED或屏障肯定未变，标pending_or_ledger_mutation_possible/save_unit_overrun及结果未知；用现有失败分支将当前URL并回barrier、保存非成功ledger，只有调用正常确认才能报告恢复观察。若无剩余总预算或修复写失败，直接保留未知，不声称屏障已恢复，不删除兄弟staging、不自动回滚。要求“在途写过期后物理上绝不成为VERIFIED/清屏障”则本方案NO-GO；该强保证不能靠本六文件协作式检查获得。
- **保存异常/硬停**：实际I/O异常按原失败/finally顺序，不以时间错误覆盖真实错误；finally保存的必须是该路径实际判定的ledger，不额外构造VERIFIED。停止后续请求，明确pending_or_ledger_mutation_possible、结果未知。没有可靠保存确认时不报告“已完整保存/已安全回滚”。budget不会使多key原子化；KeyboardInterrupt等硬停不吞掉。finally/lease释放可能不执行，仍依赖原租约/投递恢复，不改协议或自动重放新请求。
- **时间耗尽但所有业务已核验**：先看保存单元是否已正常完成且未超其观察截止；否则只能保留staging返回503。完整数量范围但有plan.deferred/旧barrier，仍只走原pending分支，绝不源成功；没有时间中断且仅数量延后时原200/bucket语义保持。
- **最终化入口已过210，或canonical调用准入已过270**：拒绝新canonical，保留所有已经保存的事实/pending，失败收尾只用剩余总预算；超期后不能保证全部失败健康/bucket/lease I/O成功。诊断区分SOURCE_WORK、URL_SAVE、PRE_CANONICAL、POST_CANONICAL、PUBLISH、BUCKET、LEASE_RELEASE，不发明新健康终态。
- **canonical调用开始后**：其内部含写入与清理；任何异常一律不能推定零写入。返回确认后迟到或健康/清理失败，明确canonical_mutation_possible/后续状态未知，保留已知写入，不能回滚/重新套“旧canonical未变”。[健康:237](../../web/collector_runtime.py#L237)只在完整源正常提交分支记成功；canonical成功后publish失败本来就可能已更新源成功时钟，本方案不把它改成未核验或称公开刷新成功。
- **publish不准入**：canonical可能已经成功，沿503/不开bucket的失败回执，snapshot_refreshed=false仅表示未调用publish，不表示canonical/健康零写。下一次按原幂等/ledger规则重试，不能增加新Queue消息。publish开始后失败/迟到须区分未确认与已确认公开提交；已确认成功返回保留原bucket完成分支、记录overrun，不在写入后抛预算错假装没发布。bucket/lease保存异常同样结果未知，不冒称COMPLETED已持久化。

总截止之后不新开业务HTTP、canonical或publish；**已发出的同步写入不能取消；失败/finally和已提交后的原有收尾只报告已知结果及迟到**，因此这份合同从未承诺270秒绝不再有缓存I/O。要求“deadline后任何写入都不发生”或“未知SDK写也能保证保存恢复”时，本最小方案NO-GO。

## 容量算术：不承诺12条按时完成

一index+12详情=13次逻辑fetch；无重试名义13×30+12×3=426秒。全部一次重试名义26×30+13×3+12×3=855秒；两者都未计解析、DNS、bootstrap/至少36次逐URL保存及publish，不是实际墙钟上界。180秒工作扣12次原间隔36，13次请求/解析/此前保存只剩144秒。全部重试再扣39，26次请求及解析/保存只剩105秒。

因此不能保证每轮12条、20条发现范围全部核验或来源恢复。合法早停只产生显式不完整和后续carryover，不下调12/20后假称完整。270/180/30/60是政策分配，非实测SLA；若需要密集场景按时完整或自动排空超过48小时的backlog，须独立协议/能力设计，当前NO-GO。

## 唯一最小修改文件（下轮待授权）

| 文件 | 必要改动 |
|---|---|
| web/collector_queue.py | 仅tjzyefy增量传入口预算/原点到_process_incremental_payload及runner；保留所有原身份/lease/时间/结果判定；不改变其他源/区域/tick/deep调用参数 |
| web/collector_incremental_runtime.py | 可选budget只用于tjzyefy discover/verify、3秒sleep、解析/None返回、预存屏障、逐URL保存准入/返回检查与时间中断503；最终化/发布只做入口检查和返回后观察，原保存、健康与bucket顺序不变 |
| web/pipeline/scripts/sync_tjzyefy_market_research.py | fetch_page_with_retry增加可选budget，30上限、2次及原retry分类不变；每次请求/返回和重试sleep使用同一预算。预算检查放在fetch错误捕获边界之外或显式重抛，避免当普通网络错误重试；无budget的CLI/deep/intent调用仍原行为 |
| web/pipeline/tests/test_collector_deferred_budget.py | 复用MemoryCache、真实planner/runner和既有fixture方法，覆盖tjzyefy时间中断、fact/None、保存边界、carryover与最终化未知；必要时复用仓库官方HTML验证实际parser路径 |
| web/pipeline/tests/test_collector_orchestration_behavior.py | 同一Queue入口原点/预检耗时、拒绝/lease finally、只向tjzyefy传预算、失败仍按原投递/独立tick行为，不改区域已验收用例 |
| web/pipeline/tests/test_tjzyefy_sync.py | 假时钟验证30 cap/余量−1、2次上限、3秒sleep不压短、预算异常无重试及无budget原CLI行为 |

不需要修改CliBudget、底层URL/解码器、bootstrap、planner、scheduler、runtime._cache_set或publish内部；如实现发现必须更改这些文件或禁止协议，**停止并给证据NO-GO**，不能悄悄扩范围。现有只读源码字符串门禁仍须保持，不能为了通过而删除其保护；原“发现只一次并复用bootstrap”语义不得改变。

## 后续离线行为验收（本轮未执行）

1. 入口预检消耗不重置；foreign/错source/跨日/错bucket在副作用前拒绝；deep/其他源/区域/CLI不注入新预算，owner拒绝与lease finally原行为保持。
2. 准入余量<=1零业务请求；发现返回/解码/parse超180不使用结果；详情fact及非事实None迟到均不得staging、VERIFIED或解除本URL barrier；初次/重试sleep不足及醒来超期都停止后续HTTP。验证timeout实际参数和最多2次。
3. 及时URL三步保存次序、30/210超期不再准入下一成功变更；staging迟到保留屏障、barrier/ledger在途迟到明确未知及现有失败恢复观察。保存每个步骤前后实际异常、finally失败及硬停均有证据。兄弟staging不丢、未执行周期重验仍可carryover，旧canonical和成功时钟在提交前预算失败时不变。
4. 时限中断无论pending多少都503/不开bucket/不publish；原12条完整、13条数量延后、合法空、旧pending空扫描、48小时carryover、非事实和深度清理门禁保持。不能将bucket完成等同源成功或公共刷新。
5. 210最终化准入/270调用准入，canonical调用前拒绝与写后迟到/写结果未知分开；publish余量不足31不调用、canonical/健康可能已变；publisher已确认迟到、异常或bucket/lease结果未知均不谎报零写、回滚、按时或持久化成功。
6. 复用既有网络/真实SDK阻断的本地桩、假时钟、临时目录与冻结证据；实现后运行必要回归与10/3并记录实际新增数量。应用/测试本轮未改，因此1098/10/3不重跑；真实HTTP/SDK/来源恢复和持久化仍未核实。

## 本轮静态验收与权限

证据见[manifest](validation/tjzyefy-incremental-contract-2026-11-07/manifest.json)：源码行号/内容及SHA、预算/容量算术、GO/NO-GO和保护文件摘要。静态verify.py已通过：44个精确源码引用、470份保护输入、源码保存/提交顺序、实际policy、预算/容量算术与文档差异范围。只用标准库读取源码/JSON/哈希与本地Git，不导入应用、不执行既有测试。仅文档及新artifact差异；原数据、fixture、旧证据与全部应用/测试/config保持原字节。没有联网、SDK安装/导入/执行、凭据/环境值/运行日志查询、云端/业务接口/缓存/数据库/函数/Queue/模型调用、环境/路由/计划/权限变更、部署、推送、workflow触发或运行数据写入。旧证据只做字节哈希，不解析日志。

本轮已完成合同和唯一最小方案，**代码未实现、行为验收未执行**。下一轮须明确上述六文件本地离线授权；仅“继续”不扩大为云端或真实写入授权。apply_allowed=false、migration_usable=false。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
