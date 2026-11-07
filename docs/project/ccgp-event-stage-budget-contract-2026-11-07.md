# CCGP 共用事件阶段时间预算及配对提交合同（仅离线方案）

2026-11-07（Asia/Shanghai）。起点 **e9ca0d976692a8014bf40eded2ccb91ffbfb7daf**，应用代码 **4916d69de3568e8bd22fc8d659da34833596c852**，现有分支codex/p0-reliability-contracts，工作树初始干净，无相关在途代理。按上一轮完整下一任务及持续推进目标执行静态审查；没有获得扩展应用文件的授权。开始15:32:17、截止15:52:17（UTC07:32:17–07:52:17）。已读取最新协议/状态/checkpoint/next-task、区域R1实现、收口报告、区域预算合同、publish实现及行动雷达合同。

**唯一推荐：只给Queue的event1–event6共用路径增加协作式270秒逻辑总预算，工作180秒、一次批次数据保存最多30秒、状态/Queue尾部预留60秒。** 这是拟议政策，未实现、未行为验收，不是硬取消/严格时限、真实缓存持久化或来源完整扫描保证。只有在获得下述六文件离线代码授权后才可实施；当前仅文档。真实部署/来源/完整时延/公开发布放行NO-GO；SDK及强保证分支CLOSED NO-GO，不重新审计。

## 当前实际调用与已有保护

| 边界 | 最新代码事实 | 必须保留 |
| --- | --- | --- |
| Queue入口 | [入口原点](../../web/collector_queue.py#L429)在payload、epoch、owner和heartbeat之前；[event依赖](../../web/collector_queue.py#L462)已DEGRADED则跳过，[现有预算白名单](../../web/collector_queue.py#L494)未包含event | foreign/owner拒绝仍在任何业务请求之前；不能从payload接受deadline，不增加租约或投递 |
| stage准入 | [run_stage](../../web/collector_runtime.py#L1918)主动清除非区域/publish预算；[_prepare_stage](../../web/collector_runtime.py#L512)管理日期/前序/attempt及RUNNING | 每stage独立原点，首次真实失败保留重试，普通第二次失败仍立即降级推进，不重置attempt成本 |
| CCGP事实准备 | [_run_ccgp](../../web/collector_runtime.py#L660)核验后计算watch，[_run_ccgp暂存](../../web/collector_runtime.py#L761)写周期records/events及watch；未提交本轮事实 | 本方案不为ccgp发现阶段加预算，不改变watch生成或两阶段源事务 |
| event分片 | [_run_event_batch](../../web/collector_runtime.py#L783)按EVENT_BATCH_SIZE=5切片；watch/staging必须存在，cycle_as_of及records/events类型须匹配 | event1–6完整覆盖默认最多30项目；不得通过裁剪watch或详情数量假称完整 |
| 单项目扫描 | [scan_events](../../web/pipeline/scripts/sync_ccgp_query.py#L85)依次更正/终止两种查询，页1；按项目号筛详情，详情前及每类结束后sleep | 无本地HTTP重试；普通单项目错误不能推断全host不可用，失败仍使整片不完整 |
| 请求/解析 | [搜索helper](../../web/pipeline/medical_channel_pipeline/ccgp_discovery.py#L244)、[详情helper](../../web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1433)原timeout均30秒；read/decode在helper内部同步执行 | 只传已有timeout_seconds，不改变helper、编码、版本或parser，不声称能抢占read/解析 |
| 失败与本地事件 | [helper失败](../../web/pipeline/scripts/sync_ccgp_query.py#L108)记录后继续；[详情失败fallback](../../web/pipeline/scripts/sync_ccgp_query.py#L145)可能产生discovery-only事件；[runtime完整性门禁](../../web/collector_runtime.py#L832)有任何失败就拒绝 | CLI原fallback保留；预算超期必须先重抛，不能借fallback把迟到结果变新证据 |
| 分片数据保存 | [event1–5](../../web/collector_runtime.py#L844)仅更新staging；[event6](../../web/collector_runtime.py#L837)要求ccgp与event1–5全COMPLETED、检查pending后写单个COMMITTED_STATE_KEY | 不能拆成分别写records/events，不清未解决pending，不把中间片成功当整源成功 |
| 健康与发布 | [成功时钟](../../web/collector_runtime.py#L2011)要求全部七阶段COMPLETED；[publish优先读配对版本](../../web/collector_runtime.py#L1755) | event阶段不调用publish。watch非空、batch完成、新事件数量、整源成功、公开提交是不同证据 |
| 尾部 | [Queue原heartbeat/推进](../../web/collector_queue.py#L499)、[失败终局](../../web/collector_queue.py#L536)保持 | 不因预算跳过原owner检查、推进或独立调度/释放；尾部I/O失败仍可能中断后续操作，不能声称必已完成 |

目前未解决的是累计时间预算，不是上述配对/健康保护缺失。已有[配对提交回归](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L1029)、[非空watch最终片提交](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L1185)、[七阶段健康](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L1016)及[依赖失败后其他源继续](../../web/pipeline/tests/test_collector_orchestration_behavior.py#L545)已有本地证据，本轮不重跑或重新报修。

## 数值依据与覆盖限制

[默认计划](../../web/pipeline/data/tianjin_query_plan.json#L18)max_event_watch_projects=30、delay_seconds=4；5项目/片，每项目2查询。零详情且各查询耗到原30秒参数时，名义串行值为 **5×(2×30+2×4)=340秒**，已超过仓库[Queue函数配置](../../web/vercel.json#L19)/[消息lease](../../web/api/collector-queue.py#L38)声明的300秒。该值只是参数算术，不是测得的真实时延或HTTP总硬上界；response.read/decode、解析和缓存耗时尚未计入。

更正/终止只查页1；当前scan_events未实现累计详情准入数量上限，不能把查询页大小当成强制候选上限。额外D条详情再增加名义34D秒。因此，默认五项目全部按时完整、完整事件召回、270秒硬退出均NO-GO；快响应可能完整完成，慢或密集响应必须整片失败并沿原有界重试/降级，不能缩小范围后报告成功。

270沿用此Queue载体已采用的逻辑包络，与仓库300秒声明之间保留30秒政策余量，**不是把maxDuration当成CLI或运行保证**。事件有独立的批次staging/配对数据写入，所以从270先保留60给原状态/健康/heartbeat/enqueue，再保留30给单次数据保存/校验，剩180给读状态、请求、睡眠、解析及merge；不是照搬区域210秒，也不是增量逐URL保存预算。30/60是协作式准入窗口，不是已测SDK耗时上限。

边界统一为`t0+180`工作截止、`t0+210`数据保存最晚返回观察点、`t0+270`逻辑总截止；每片保存局部截止`min(save_started+30,t0+210)`。t0来自Queue进入process的monotonic，包含预检与_prepare_stage。CLI900/840/60、前台20分钟、平台SDK解析与消息lease、owner活性900秒各自独立，不互相替代。

静态额外覆盖条件：计划loader允许max_event_watch_projects到100，而注册六片×5只能覆盖30。默认30无冲突；最小实现须在event读取watch后、任何业务请求前拒绝`len(watch)>6×EVENT_BATCH_SIZE`，不能静默只处理前30或改分片/计划。此为拟议读前完整性检查，不声称已出现31项目线上漏扫。

## 唯一接口与超期合同

1. **限定注入。** Queue仅对STAGE_ORDER中明确注册的event1–6创建`CliBudget(clock,sleep,total_seconds=270,work_seconds=180,started_at=entered_at)`；run_stage及_run_event_batch接受同一可选实例，不重置。其他stage及非Queue/CLI不注入时保持默认。
2. **helper复用及导入边界。** `scan_events(...,budget=None)`仅可选向现有搜索/详情helper传`budget.request_timeout(30,phase)`，即`min(30,工作余量−1)`；余量<=1零请求。保留4秒间隔，不够就拒绝，不压短。[sync_regional_ccgp顶层](../../web/pipeline/scripts/sync_regional_ccgp.py#L42)导入sync_ccgp_query，故**禁止query顶层反向导入CliBudget/异常形成循环**；有budget时在scan_events函数内延迟取得既有CliBudgetExceeded，实例仍由Queue创建，不新建预算原语。
3. **每个业务边界。** cache/plan读取后、每项目/类型/候选准入、请求返回（含read/decode）、搜索解析返回、详情解析返回、event追加、sleep醒来及merge后检查工作截止。普通异常catch首先检查剩余工作预算；已超期就抛原预算异常，不能记录普通失败后继续。专门预算异常须先于generic catch重抛，runtime也不能将其包成普通EVENT_WATCH_SCAN_FAILED。迟到None、解析失败及discovery-only fallback同样不能产生新核验证据。
4. **只保存完整片。** 所选项目/查询/详情全部完成、failures为空且merge在180秒前完成后，构造新的staged候选字典（不原地修改读回对象）。不新增每项目或每URLcheckpoint，不保存本片部分结果；已持久化的前序兄弟staging保留。当前片预算失败可由既有下一次attempt整片重做；event_id/stable_id及[merge去重](../../web/pipeline/medical_channel_pipeline/state.py#L79)保持。
5. **保存阶段。** 以同一时钟检查局部截止前后；event6的前序校验与原_assert_pending_canonical_commit也纳入30秒窗口。每步调用前后检查；pending校验迟到不得再发数据写。现有[_assert_pending的seed豁免](../../web/collector_runtime.py#L321)在原records键缺失时直接返回；event6须先在本调用读取并确认原CCGP_RECORDS_KEY为list（合法空list允许），缺失/损坏保守拒绝，避免把本轮配对提交当初次seed绕过旧pending。只加event调用者准入，不修改seed/pending helper或其协议，不宣称解决并发删除/CAS。写前失败走CollectorStageBlocked(retryable=True)、FAILED/503，旧配对版本和成功时钟保留。不改_cache_set、pending清理、缓存TTL/数据格式或owner原子性。
6. **已经发出的写。** 显式区分目标STAGING/COMMITTED_PAIR、write_attempted、write_call_returned及mutation_possible。缓存调用异常或未返回为结果未知，不能说零写或回滚；正常返回只表明本地调用返回，不等于真实持久化确认。完整片的数据写返回迟到时保留既有已发出写及原完成/收尾路径，附overrun，不改称写前拒绝或自动重复提交。保存窗口/总窗口不是强制取消器。
7. **状态与交付。** run_stage针对event预算使用EVENT固定错误码及保留数据写诊断，不复用REGIONAL_*造成错误目标/零写结论。stage/健康保存失败与Queue尾部失败分别保留数据写已知/未知信息；沿原异常和重试路径，不新增尾部deadline短路。receipt只在workflow结果/诊断，不改公开snapshot、健康schema、canonical配对格式、版本或Queue/lease协议。

## 提交/恢复判定表

| 时点 | 允许结果 | 不允许结论 |
| --- | --- | --- |
| 180前请求/解析/merge失败或超期 | 后续业务停止，当前片不保存；保留前序staging、旧committed、pending/成功时钟；503并有界重试 | 跳过项目也称片完整、迟到fallback算核验 |
| merge完成，pending检查或写前准入超期 | 不发数据写，FAILED/503；元数据RUNNING/失败健康可能已经改变 | 全系统零写、删除旧staging重来 |
| 数据写已发出，异常或返回未知 | 明确目标及mutation_possible；保留原重试/配对幂等；恢复须读取原键/同cycle证据，不换版本或清屏障 | 原数据必定未变、已回滚、保存成功 |
| 完整数据写正常返回但迟到 | 保留CALL_RETURNED_UNVERIFIED及overrun；原状态/健康/Queue顺序继续；后续I/O错误另标未知 | 真实持久确认、按时、硬退出或自动撤销写 |
| event1–5成功 | staging更新，单片COMPLETED；committed对与整源成功时钟保持旧值 | 本轮CCGP完整成功、公开发布完成 |
| event6前序不全或旧pending不满足 | 原门禁拒绝，不提交新配对 | 为按时清pending或独立提交records |
| event6成功返回，状态/健康/heartbeat/enqueue失败 | 数据写返回与尾部结果分开；原owner/重试恢复，不新增CAS | 所有状态可靠完成、公开快照已更新 |
| 合法空watch或无新事件 | 仍跑六片状态和event6配对门禁；全部七阶段完成才有源成功 | 以“无详情”绕过pending或前序门禁 |

缓存/owner原子CAS、硬终止和崩溃后持久回执不在此方案；如果实施必须改变这些协议才能满足验收，则NO-GO结束，不扩大文件或重复模拟补证。

## 唯一最小修改文件及后续行为验收

下一轮必须明确授权以下**六个既有文件**，当前轮没有修改它们：

1. `web/collector_queue.py`：仅已注册event的同原点预算注入；原路由/owner/attempt/推进不变。
2. `web/collector_runtime.py`：event可选预算传递、完整片数据保存窗口/回执、源与尾部异常保真及watch覆盖准入；不改ccgp采集、_cache_set或配对协议。
3. `web/pipeline/scripts/sync_ccgp_query.py`：仅scan_events可选预算、延迟异常类型导入、请求/sleep/返回/解析/catch检查；CLI默认路径不变。
4. `web/pipeline/tests/test_runtime_source_parity_behavior.py`：复用MemoryCache/假时钟/事件样本，覆盖各片与保存前后、旧committed/前序staging/pending/健康。
5. `web/pipeline/tests/test_collector_orchestration_behavior.py`：原点/预检耗时、foreign/owner、首次及最终失败、依赖跳过/其他源继续及非event不受影响。
6. `web/pipeline/tests/test_ccgp_events.py`：既有事件parser/样本与注入transport覆盖scan_events预算、导入顺序和无budget兼容；不新建引擎/模块。

行为验收须包含：零请求拒绝；search/detail超时参数cap30及余量−1；sleep准入与醒来超期；成功/异常/None及搜索/事件解析返回超期；generic catch不能吞预算或产生fallback；5项目与31项目范围拒绝；event1–5不动committed，event6只写单个配对键；空watch/无新事件/前序失败/旧pending/原records缺失或损坏；预写、写后迟到、写前/写后抛错、stage/健康/Queue尾部未知；重复投递不重复事件；成功时钟/版本/独立源与原CLI保持。实现变化后才运行必要离线Python回归及10/3，按实际新增数量记载，不预填通过数。

当前F1边界也已静态审查：搜索helper会识别频繁访问页，但scan_events会记录失败后继续另一类型；runtime只有单项目两次搜索都失败才立即阻断，单次明确拒绝没有全片host止损。普通单项目失败最终也阻断整片提交。预算方案不声称修复跨进程共享冷却/Retry-After或所有事件拒绝止损，真实来源放行仍需独立满足合同。

## 本轮验收、授权与结束条件

本轮只标准库静态核对最新源码行号/SHA256、AST调用及导入方向、配置/预算算术、历史1157/10/3 JSON记录和既有输入字节；不执行应用/SDK/测试，不新增模拟，不联网或查询运行日志/实际环境值。代码和配置保持4916d69。具体数量与时间见[验收摘要](validation/ccgp-event-stage-budget-contract-2026-11-07/validation-summary.json)、[证据清单](validation/ccgp-event-stage-budget-contract-2026-11-07/manifest.json)。

判定：**离线协作式方案有条件GO；当前实现、真实部署/完整扫描/持久化放行NO-GO。** 后续六文件与最近用户明确授权的区域R1两文件范围不同，自动持续推进不构成新增批准；已完成方案，自动工作停在应用扩范围授权边界，不继续改代码，也不拆成更多模拟轮。

[下一轮完整任务](next-task.md)列明六文件实现及行为验收，只有用户明确授权该范围后才执行。当前界面无法生成该按钮；提供完整可复制提示词。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。apply_allowed、migration_usable=false；没有云端、部署、推送、计划/变量/权限变更或运行数据写入。
