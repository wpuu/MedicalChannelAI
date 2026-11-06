# publish协作式预算与提交回执合同（仅离线方案）

2026-11-07（Asia/Shanghai）。起点82c1006，代码b584bcf；现有隔离分支codex/p0-reliability-contracts，初始工作树干净、仅根代理，无相关在途工作。开始2026-11-06T19:14:30Z，前台截止19:34:30Z。已读取最新用户指令、工作协议/状态/checkpoint/next-task、增量实现/合同、区域实现及行动雷达合同。只静态阅读，不导入/执行应用、SDK或测试。

## 唯一推荐与边界

**唯一推荐：下一轮经明确授权，只实现Python发布调用者侧的协作式准入与现有ACK回执保真，限定七文件。** 同一_run_publish服务Queue deep publish与已接预算的tjzyefy增量；Node HTTP/数据库/公开版本协议原样保留，不创建路由、表、持久回执存储、模拟层或SDK接入工作流。已有1121/10/3不重跑、不计作本轮新通过。

本方案不是端到端强时限方案。**Python→Node→数据库/Node缓存统一可取消deadline、在途写零变化、崩溃后可靠回执/自动对账、owner/跨key原子提交均NO-GO，当前审查关闭这些强保证子项，不再追加模拟或SDK补证。** 只对本地可观察边界给出准入、已确认与未知回执。真实部署、SDK持久化和权限事实仍未核实。

## 现有完整调用链

| 边界 | 当前源码事实 |
|---|---|
| deep入口 | [queue:430](../../web/collector_queue.py#L430)记录monotonic，验证epoch/cycle/owner/heartbeat；[494](../../web/collector_queue.py#L494)仅区域传budget，publish目前走无budget调用。[run_stage:1786](../../web/collector_runtime.py#L1786)也清除非区域budget；[1822](../../web/collector_runtime.py#L1822)调用_run_publish |
| 增量入口 | source canonical提交/清pending/[健康:887](../../web/collector_incremental_runtime.py#L887)在publish之前；[895](../../web/collector_incremental_runtime.py#L895)tjzyefy已有总余量31准入，但[helper:515](../../web/collector_incremental_runtime.py#L515)不向_run_publish传budget。其他增量源仍未接预算，不能冒充已覆盖 |
| canonical与pending | [runtime:1667](../../web/collector_runtime.py#L1667)读取全部canonical列表及events，优先CCGP committed records/events对；[1701](../../web/collector_runtime.py#L1701)缺任何列表拒绝。源级新canonical在[_assert_pending:318](../../web/collector_runtime.py#L318)受屏障保护。publish不全局拒绝所有其他源pending，而是允许使用其最后核验canonical并携带健康覆盖，不能为预算加入全局pending阻断或清屏障 |
| 构造与本地候选 | [1727](../../web/collector_runtime.py#L1727)用cycle_as_of构造/合并/投影/健康及digest；[1745](../../web/collector_runtime.py#L1745)LATEST set/readback。它不是公开权威提交点；此处成功不能称公开发布成功，失败也不能推定所有缓存零写 |
| Python权威PUT | [1608](../../web/collector_runtime.py#L1608)校验现有发布目标/认证配置，序列化后PUT，cap[30秒:166](../../web/collector_runtime.py#L166)；[1633](../../web/collector_runtime.py#L1633)同步open/read/JSON解析。Preview主机固定规则[1590](../../web/collector_runtime.py#L1590)保持，不读取实际环境值来核实 |
| Node预检 | [public-snapshot:111](../../web/api/public-snapshot.js#L111)认证；[122](../../web/api/public-snapshot.js#L122)完整结构/大小/版本/未来预检及database/remote-reader配置检查，然后才persist。requestBodyValue的流式完整读取在[66](../../web/api/public-snapshot.js#L66)，1.9MB限额在[_verifiedSnapshot:247](../../web/api/_verifiedSnapshot.js#L247)事务前校验，不是流式读取时间/内存上界保证 |
| 权威事务 | [_publicIntelligenceDb:331](../../web/api/_publicIntelligenceDb.js#L331)ensureSchema后sql.begin；[347](../../web/api/_publicIntelligenceDb.js#L347)事务内全发布advisory lock、最新revision检查、写入及hash/payload/timestamp读回；只有begin正常返回后才返回persisted=true。源码声明SQL事务不是本轮真实数据库执行证据 |
| Node副本与ACK | [endpoint:128](../../web/api/public-snapshot.js#L128)await persist完成，随后invalidate memo、[134](../../web/api/public-snapshot.js#L134)await Node缓存副本；副本失败仍200并RETRY_REQUIRED。ACK[144](../../web/api/public-snapshot.js#L144)有ok、durable_committed=true、cache_status、同版本和pool count。Node缓存调用发生在ACK之前，Python断开/超时不能取消已提交或在途服务端操作 |
| Python副本 | [1759](../../web/collector_runtime.py#L1759)PUT返回后，Python再次set/read PUBLISHED副本，失败已有RETRY_REQUIRED保护；[1773](../../web/collector_runtime.py#L1773)再返回发布结果。不把LATEST或任一副本当权威数据库 |
| deep收尾 | [_mark_completed:626](../../web/collector_runtime.py#L626)写stage；[run_stage:1864](../../web/collector_runtime.py#L1864)收尾异常目前无publish专用已确认回执；[queue:499](../../web/collector_queue.py#L499)heartbeat/推进或pending按证据reconcile→独立tick→owner释放。publish终局失败[532](../../web/collector_queue.py#L532)保留FAILED并释放owner，不改这些协议 |
| 增量收尾 | [901](../../web/collector_incremental_runtime.py#L901)publisher返回后记录CONFIRMED/NO_REFRESH；[924](../../web/collector_incremental_runtime.py#L924)标bucket。tjzyefy已能在bucket失败时保留已确认发布，lease释放未知[queue:317](../../web/collector_queue.py#L317)保留scan_result。无budget来源的旧回执能力不等于此能力已覆盖所有增量 |

实际Node GET优先remote（已配置时），否则数据库再runtime/bundle，见[_verifiedSnapshot:384](../../web/api/_verifiedSnapshot.js#L384)。fresh GET绕CDN/memo并非本轮执行；事务内读回与客户端公开GET回验是不同证据，不能混称。

## 已有保护与三项确切缺口

| 优先级/分类 | 最新证据、影响与最小处理 |
|---|---|
| P1 ACK保真，静态确认接受路径，未做新行为复现 | [Python:1655](../../web/collector_runtime.py#L1655)只校验ok、版本、整数pool count，没有要求现有durable_committed=true；既有[测试桩:48](../../web/pipeline/tests/test_collector_publish_environment.py#L48)也缺该字段而被设计为成功。下一轮用真实既有字段加强ACK校验，缺失/false/malformed或错身份为UNKNOWN，不得CONFIRMED。不是当前线上伪ACK事故证明 |
| P1 双副本回执信息丢失，静态设计缺口 | Node可返回RETRY_REQUIRED，但[Python:1761](../../web/collector_runtime.py#L1761)重新从READY计算，只使用durable_result.snapshot_as_of。下一轮分别保留Node和Python副本状态，任一未确认就保守RETRY_REQUIRED；未经真实绑定证据不能假称Python副本成功已修复Node副本。未断言目前缓存真的失效 |
| P1 时间/尾部确认缺口，静态设计缺口 | deep publish无budget，增量只有外层31准入；请求cap30不是构造/缓存/数据库/Node postcommit缓存/完整响应的总预算。公开已确认后stage/heartbeat/lease失败也不能变成“没发布”。下一轮只补调用者同原点准入及分阶段本地回执，不承诺Node取消、硬退出或可靠持久回执 |

已有Node提交后副本失败保持200/RETRY_REQUIRED、数据库回退/冲突防护、事务读回失败回滚、跨revision并发锁和微秒精度不能重复报修：既有[publication门禁:164](../../web/scripts/check-p0-publication.mjs#L164)、[缓存失败/幂等:173](../../web/scripts/check-p0-publication.mjs#L173)、[微秒:143](../../web/scripts/check-p0-publication.mjs#L143)已有本地源码用例；本轮只读，不声称这些用例本轮通过或真实DB已验收。

## 唯一预算合同（拟议，未实现）

| 规则 | 数值、依据及接口 |
|---|---|
| deep publish逻辑总270 | 沿同一Queue入口t0，配置[300秒:18](../../web/vercel.json#L18)减30名义外层余量；不是实际部署SLA。API解析/SDK分发在t0之前的成本未覆盖。不从payload接deadline |
| publish工作截止t0+210，回执预留60 | 工作包括canonical读取、构造/序列化、LATEST候选读写，以及权威PUT与ACK校验；60给已确认后的可选Python副本、stage/bucket/heartbeat/tick/lease原收尾。210+60=270是逻辑政策，不是这些缓存步骤实际<=60的证明 |
| 提交是工作窗口内的子预算cap30 | PUT timeout=min(30, publish_work_deadline−clock−1)，余量<=1不发PUT，零本地HTTP重试；若需保留完整cap30及1秒余量，构造/LATEST需在t0+179前完成。179=270−60−30−1，只是容量阈值，不能宣称已测完成 |
| tjzyefy增量复用原270绝对总截止 | 原source工作180/URL尾部30/最终化60不变，不在发布入口重置270，不修改parent.work_seconds。publish_work_deadline=min(parent.started+210,parent.started+parent.total_seconds−60)，只用同一clock与原语做局部准入；已有外层31准入仍保留，但不足以替代内部工作检查。进publish已过210则拒绝新PUT，source canonical/健康可能已提交，不能说本次零写 |
| 其他增量来源 | 不新接时间预算；本轮最小代码授权只覆盖deep publish及已接budget的tjzyefy。公共Python ACK消费统一使用现有字段，其他未覆盖预算仍明确未覆盖 |
| 调用接口 | Queue stage=publish注入既有CliBudget(total270,work210,started_at=t0)；run_stage只扩准入到publish；_run_publish/_persist_verified_snapshot_durably增加可选budget和有界本地receipt上下文；incremental helper只在已有budget时传递同一对象。无新预算类、transport层、HTTP header或数据库参数 |

每次canonical get、构造/merge/投影/JSON/digest、LATEST set/get前后检查工作deadline；不更改canonical和CCGP committed pair选择、不从仓库/公开快照回填合法空或缺失canonical。超期中止后续业务，不抹掉已正常保存的候选/旧canonical，不为了让发布通过而清pending。

PUT未开始前可报告NOT_ATTEMPTED；一旦调用urlopen，立即标UNKNOWN。**返回迟到时先验证ACK，再判断时间**：200、ok严格true、durable_committed严格true、原有精确snapshot_as_of与整数pool count校验全部通过才CONFIRMED。合法ACK即使超210/270也保留CONFIRMED和overrun，不用预算异常改成未提交。无ACK、错误ACK、网络断开/非200/解码失败均不能排除服务端已提交。校验不新增服务端字段，也不能将本地candidate digest当ACK未返回的数据库snapshot_hash。

确认后可选Python副本每个调用前检查总余量，耗尽就跳过后续副本操作、RETRY_REQUIRED；已经发出的调用迟到/异常保留cache_mutation_possible，不撤销权威提交。Node ACK自带的cache_status必须单独保留，不静默覆盖。未知/缺失副本状态保守保留，不能反推权威失败。

60秒是预留，不是到270强行中断。**已确认后的原stage/bucket/heartbeat/pending按证据reconcile/tick/lease收尾顺序保持**，不能因budget在中间抛错就跳过owner释放或独立调度，也不能假称尾部写一定成功。超期仅增加回执观察，写失败保持其真实类型与未知状态，不引入新终态或自动回滚。

## 回执与故障恢复合同

本地receipt仅放在既有workflow结果/异常诊断，绝不加入公开snapshot或改变其hash、source_health、snapshot_as_of。parent.work_complete只表示原源工作完成，不证明公开提交；deep publish工作完成须以合法ACK为准。receipt仅添加固定枚举、阶段、已有版本、候选本地digest和有界时间/布尔值；不放入原始响应体、凭据/URL或查询文本。它是本次调用观察，不是跨崩溃持久回执。

| 观察点 | 必须报告及恢复边界 |
|---|---|
| 读/构造/LATEST前后拒绝 | authority=NOT_ATTEMPTED；LATEST/元数据可能已写，canonical/公开权威未由本次PUT触及；不称全系统零写。保留原失败/503与重试限额 |
| PUT发出后超时/非200/坏ACK | authority=UNKNOWN，公开提交可能已发生；FAILED只能指本次workflow未获确认，绝不是权威回滚证明。不增加本地重试或换新时间戳绕过冲突 |
| ACK已确认，任一副本未确认 | authority=CONFIRMED，cache=RETRY_REQUIRED/分副本状态，正常已发布结果不变；禁止降为未提交或自动再提交 |
| ACK已确认，stage/bucket写失败 | 保留authority=CONFIRMED及版本，workflow_state_mutation_possible；回执保存/交付未知，不能声称已可靠COMPLETED，也不改写成新的FAILED公开状态 |
| ACK未知，失败状态也保存失败 | 两项独立未知；不伪造FAILED已持久化。沿原异常/后续投递与owner活性恢复，不能增加解锁/续租/重投协议 |
| heartbeat/owner替换/lease失败 | 原身份拒绝和所有权释放规则不变，不在错误owner下推进；已确认公开快照不回滚。Queue正常返回只说明回调路径完成，不代替SQL确认，反之回调失败也不否定已确认SQL |
| 重试/版本 | 保留原max attempts、显式旧恢复例外及owner处理。相同版本同内容重试不插入新快照版本，但仍可能开SQL事务/修复旧截断列；同版本异内容与回退仍拒绝。不能为budget改snapshot_as_of/健康字段来规避冲突 |

版本依据：[_snapshotRevision:3](../../web/api/_snapshotRevision.js#L3)最多六位微秒，SQL优先payload revision，并以[::text::timestamptz:370](../../web/api/_publicIntelligenceDb.js#L370)避免JS Date截断；[事务:360](../../web/api/_publicIntelligenceDb.js#L360)拒绝回退和同版本异hash。现有权威存储协议原样保留，没有新增CAS或回滚能力。

## 唯一最小修改文件（下轮须明确授权，当前未实现）

| 文件 | 必要变化 |
|---|---|
| web/collector_runtime.py | publish可选预算/本地receipt，既有ACK字段严格消费，预PUT与后ACK检查顺序、副本状态保真；run_stage只增加publish分支的异常诊断，保留原状态/健康与confirmed之后的已知结果 |
| web/collector_queue.py | 只给deep publish传同入口budget；保留原epoch/owner/heartbeat、重试、终局publish失败释放、pending/tick/lease收尾规则；尾部失败携带已有本地receipt，不新增协议 |
| web/collector_incremental_runtime.py | 已有tjzyefy budget传到helper/_run_publish，读取其NOT_ATTEMPTED/UNKNOWN/CONFIRMED诊断，不能在helper前就把未发PUT归UNKNOWN；保留已确认发布后的bucket/lease未知回执和其他源原路由 |
| web/pipeline/tests/test_collector_publish_environment.py | 原Preview目标/身份/无泄露门禁保持；既有ACK桩补齐当前Node已有字段，并新增缺失/false durable_committed、时间/数量错误、超期ACK与timeout参数用例 |
| web/pipeline/tests/test_runtime_source_parity_behavior.py | 实际publisher读取/构造/LATEST/PUT/副本准入与迟到、两份副本状态、stage确认后异常、合法空/缺canonical/CCGP committed对和其他源pending保护；保留原门禁 |
| web/pipeline/tests/test_collector_orchestration_behavior.py | deep publish原点/预检与原终局/owner/tick/lease收尾，明确publish新增预算；其他stage不误接，不删除原调用边界保护 |
| web/pipeline/tests/test_collector_deferred_budget.py | tjzyefy共享原点和内部发布预算、未发PUT vs真实UNKNOWN、确认后bucket/lease未知、旧pending/成功时钟/其他来源不回归 |

**不修改**Node endpoint、_publicIntelligenceDb、_verifiedSnapshot、_snapshotRevision、_privateDb、CliBudget、依赖锁或平台配置；也不执行/新建JS事务模拟器。上述七文件无法安全满足时立即给证据NO-GO，不偷偷增加HTTP字段、query取消、server deadline或持久回执存储。

## 后续行为验收（本轮未执行）

1. 假时钟证明deep预检计入t0；tjzyefy复用原t0且180/30/60不重置；publish工作210/总270、HTTP cap30及余量−1；超期后零新PUT。cache/JSON/parse返回超期不得继续发送该候选，不保证抢占I/O。
2. PUT前NOT_ATTEMPTED与PUT后UNKNOWN严格区分；缺/false durable_committed、ok非true、错误版本/数量/坏JSON不得CONFIRMED。正确ACK即使迟到也保留确认，不新增HTTP重试。
3. LATEST写后失败/超期不称权威已提交或全系统零写；Node副本RETRY_REQUIRED不被Python READY掩盖；确认后Python副本跳过/迟到/失败仍CONFIRMED并RETRY_REQUIRED。
4. 已确认后的stage/bucket/heartbeat/tick/lease失败/owner变更单独标未知，不回滚，不跳过原独立调度/释放协议或伪造完成。实际状态保存失败保持原异常类型；UNKNOWN不升级CONFIRMED。
5. 保持合法空、缺canonical拒绝、CCGP records/events committed对、其他源pending与最后核验数据、健康时钟、原attempt例外。不得删除或放宽微秒/同版本冲突/rollback/事务读回门禁。
6. 仅既有本地cache/HTTP桩、冻结证据、假时钟和临时目录，阻断真实SDK/外部网络；实现后仅运行必要Python回归和10/3并记录实际新增数量；Node/SQL/JS门禁源码未变时不重跑JS，只核对其保护未被改动，不安装/导入真实SDK。mock不证明真实事务/取消/部署，当前1121/10/3仍是历史通过。

## GO/NO-GO与本轮静态验收

| 目标 | 决策 |
|---|---|
| 当前仅文档合同/引用/算术/字节保护 | GO，当前授权已完成；未改应用或测试 |
| 上述七文件调用者侧离线实现/行为验收 | 可形成安全最小方案，待下一轮明确授权；不等于本轮已实现 |
| 跨Python/Node/SQL/缓存统一严格时限或取消 | NO-GO并关闭：HTTP30、DB connect_timeout10/idle_timeout20不是事务/锁/缓存总上限，见[_privateDb:26](../../web/api/_privateDb.js#L26)；不修改协议无法传递可信跨进程deadline，client断开不证明server停止 |
| 硬停后必有持久回执/自动确认UNKNOWN | NO-GO并关闭：现有本地观察/元数据写入均可能丢失；不新建存储或对账协议，不追加模拟层 |
| 真实运行、身份、SDK、权限与部署放行 | 未核实，NO-GO；SDK工作流保持CLOSED NO-GO，不重开审计 |

静态证据见[manifest](validation/publish-budget-contract-2026-11-07/manifest.json)：最新行号/原文/源码SHA、调用与回执决策、预算算术、保护输入字节。静态verify.py已通过46处精确引用、492份保护输入、源码提交/ACK顺序、三项缺口和270/210/60算术核对。检查仅用标准库读取源码/JSON/哈希及本地Git，不导入/执行应用、SDK、模型、采集或测试，不联网/查询云端、凭据、实际环境值或运行日志。旧证据仅做字节哈希，不解析日志。无环境/路由/计划/权限/变量变化、部署/推送/workflow触发、数据库/真实缓存/运行数据/历史数据/公开快照写入。apply_allowed=false、migration_usable=false。

本轮交付是合同与唯一七文件最小方案；**代码/新行为测试未实施，当前来源/公开快照/数据库状态未查询。** 下一轮完整任务见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
