# CCGP发现/事实阶段预算与staging/watch准备合同（仅离线方案）

2026-11-07（Asia/Shanghai）。起点 **fc7e4895854ebee24aec616021b8ffa4afce8ba5**，应用代码 **5d2fe858c5c478ebdcfbba53df1da9eadca1ed21**，现有隔离分支codex/p0-reliability-contracts，初始工作树干净，无其他在途代理。按持续推进目标及上一轮完整下一任务，只做静态文档。前台16:09:45开始、16:29:45截止（UTC08:09:45–08:29:45）。已读取最新指令/协议/状态/checkpoint/next-task、事件实现/合同、区域R1及行动雷达合同。

**唯一推荐：仅Queue的ccgp阶段复用CliBudget，总270秒、工作150秒、双键准备与读回最多60秒、原状态/Queue尾部预留60秒。** 先完整核验当前配置范围，再按既有staging→watch写入顺序准备；只有两键本地读回均在窗口内匹配候选，才可把ccgp阶段记为准备完成并推进事件。不是跨键事务、真实持久化确认或CCGP源完整提交。

当前未实现，离线最小方案有条件GO；真实部署、全部范围按时完成、持久化和公开交付NO-GO。SDK、硬取消/严格时限、原子CAS/跨键提交、自动回滚与崩溃持久回执强保证CLOSED NO-GO。上一轮明确授权只限事件阶段且禁止其他阶段预算，自动继续不新增批准，本轮不改代码。

## 实际调用链与不能重复报修的保护

| 边界 | 当前代码事实 | 合同要求 |
| --- | --- | --- |
| Queue及准入 | [入口](../../web/collector_queue.py#L429)有本地原点及epoch/owner预检；[现有预算分支](../../web/collector_queue.py#L494)不含ccgp；[run_stage](../../web/collector_runtime.py#L1975)清除其budget | 新预算只注入stage==ccgp，沿同一原点包括_prepare_stage，不接payload deadline；其他阶段、attempt/owner/租约保持 |
| 计划与基线 | [_run_ccgp](../../web/collector_runtime.py#L660)读天津计划、两次_cached_list后读committed对；有committed则以其records/events为基线 | 计划/基线/序列化读后检查。合法空list不是缺失；存在损坏committed仍拒绝，不以公开snapshot回填 |
| 原始seed副作用 | [_cached_list](../../web/collector_runtime.py#L441)遇非list时会bootstrap并写raw canonical；bootstrap读仓库已知版本 | 保留既有初始化行为，不改全局helper。调用前保守标记bootstrap可能写入，正常返回才结合bootstrapped布尔收紧；返回超期仍可能已写旧seed，不能说全系统零写 |
| 搜索 | [discover_candidates](../../web/pipeline/scripts/sync_ccgp_query.py#L192)每关键词依次两类型、每类型页1、类型间sleep；外层关键词间也sleep | 可选budget按现有cap30及剩余工作−1传timeout；睡眠不足就拒绝，不缩短，不新增HTTP重试/页数 |
| 选择与详情 | [选择](../../web/collector_runtime.py#L707)当前直接截取max_candidates；选中项逐一睡眠、详情、adapter | Queue预算路径发现数超过max_candidates须在详情前整批拒绝；13不能静默当12完整。此为静态缺口，未行为复现/未声称线上漏扫；不把已修CLI F3当runtime能力 |
| 完整性 | [publish_gate](../../web/pipeline/scripts/sync_tianjin_plan.py#L146)仅判断至少部分发现/核验；[runtime随后failures门禁](../../web/collector_runtime.py#L750)拒绝任何发现/详情失败 | 原失败保护保留；未执行、None或超期结果不成为事实，不能借计数/合法空掩盖遗漏 |
| 合并与watch | [merge及active watch](../../web/collector_runtime.py#L752)后检查计划watch cap | merge、watch构造及候选digest也属于150秒工作；watch超过min(计划上限,6×EVENT_BATCH_SIZE)时准备前拒绝，不改计划或分片 |
| 两次保存 | [staging](../../web/collector_runtime.py#L761)先写，后写[watch list](../../web/collector_runtime.py#L764)，当前无两键读回匹配门禁 | 写入顺序和两键格式不变；插入只读确认，并分别记录每键写/读回状态，不把正常返回当持久确认 |
| 配对/健康/发布 | [event6配对门禁](../../web/collector_runtime.py#L868)、[ccgp仅标待事件核验](../../web/collector_runtime.py#L2076)、[publish读committed](../../web/collector_runtime.py#L1812) | ccgp只准备，不写COMMITTED_STATE_KEY，不刷新源成功时钟，不调用publish。七阶段、pending、版本/健康和独立来源合同不变 |
| 失败恢复 | [_prepare_stage](../../web/collector_runtime.py#L560)拒绝前序FAILED/RUNNING；Queue只在原完成/终局条件推进 | 准备未确认走原FAILED/503及有界重试，最后失败降级；首个真实重试、独立调度及owner检查不删改 |

没有新行为复现。已修区域、事件、CLI、增量与publish保持既有版本证据；1181/10/3本轮不重跑。上述“完整”仅限配置关键词/类型/日期与已请求页1的发现、并全部核验所发现集合，不是采购全集召回或历史迁移证明。

## 时间与容量依据

[默认计划](../../web/pipeline/data/tianjin_query_plan.json#L4)5关键词×2类型=10次搜索，上限12详情，delay=4。类型间5次sleep与关键词间4次sleep共36秒，12详情前sleep48秒，满额固定等待84秒；HTTP搜索和详情原cap均30秒。

- 零详情的名义参数总和：10×30+36=**336秒**。
- 12详情名义参数总和：(10+12)×30+36+48=**744秒**。
- 以上不含bootstrap、缓存、解析、merge/digest，且urllib timeout不是同步调用总硬上界；不是测得真实时延。默认满配置完整且按时完成NO-GO，快响应可完成，慢响应须有界失败，不缩小范围后报告完整。

270沿用当前Queue逻辑包络，与仓库[300秒声明](../../web/vercel.json#L19)留30秒政策余量，不把平台配置当运行保证。保留原尾部60，因准备涉及两个键，另留共同60窗口（两份30秒政策份额，不是每个SDK调用有30秒上限），剩150用于读取/发现/详情/构造。因此不同于事件180+单键30、区域210或CLI900。

统一工作截止`t0+150`，双键准备局部截止`min(prepare_started+60,t0+210)`，逻辑总`t0+270`。CliBudget(total270,work150)的snapshot reserve120表示双键60+尾部60，不能误称尾部120。没有第二个预算引擎，不在helper/第二个键重置原点。

## 唯一最小接口与准备门禁

1. **限定传递。** Queue只为ccgp注入同一CliBudget；run_stage和_run_ccgp接可选实例。discover_candidates增加budget=None，沿[scan_events已有延迟导入模式](../../web/pipeline/scripts/sync_ccgp_query.py#L85)取得原异常类型，避免区域脚本顶层反向依赖。共享HTTP helper/CliBudget不改，CLI与无budget默认路径不被新增预算影响。
2. **超期拒绝。** 计划/cache/bootstrap返回、每关键词/类型/候选准入、请求返回含read/decode、搜索及详情解析、去重/排序/选择、每次sleep及merge/watch/digest前后都检查。generic catch先重抛预算异常；普通异常返回时也先检查当前工作截止，迟到None/失败不能被当普通失败后继续，更不能append事实。
3. **显式输入范围。** 新Queue路径发现唯一候选数>计划max_candidates就整批拒绝，不另加pending种类或增加详情上限；watch同时受现有六片容量约束。所有查询/选中详情无失败、范围未截断、merge/watch完成且候选digest在150内完成，才标work_complete。该标志不证明双键准备或公开提交。
4. **复用数据与digest。** 构造原形状`{cycle_as_of,records,events}`及原watch list；复用[_digest](../../web/collector_runtime.py#L1375)计算候选和读回摘要，保持JSON/字段内容，不加receipt或周期字段到watch，不修改既有staging/配对schema。
5. **一次60秒准备窗口。** 顺序固定为STAGING写→STAGING读回/匹配→WATCH写→WATCH读回/匹配；每个I/O及摘要校验前后检查同一局部截止。读回类型、cycle/完整候选摘要、watch list都须匹配；缺失/None、旧watch、错cycle或错摘要均不得“准备完成”。不以公开snapshot、raw shard或仓库输入冒充读回。两键均匹配才可返回PREPARED_LOCAL_READBACK；仅本地读回匹配，不称原子性/真实持久化。
6. **逐键回执。** 每键区分write_attempted、write_call_returned、mutation_possible和readback NOT_ATTEMPTED/MATCHED/MISMATCH/UNKNOWN/LATE；正常写返回只为CALL_RETURNED_UNVERIFIED。另记bootstrap可能副作用、总体NOT_STARTED/INCOMPLETE/PREPARED_LOCAL_READBACK及source_transaction_committed=false。固定字段只在workflow结果/异常诊断，不进staging/watch/公开snapshot，不回显原文或凭据。
7. **准备迟到的特别处理。** staging写已返回而watch未获准、任一写/读回异常、读回返回超期，即使两个写调用都返回过，也为准备不完整/未知，原FAILED/503，不排队event1。已发出写照实保留，不称写前零写、不回滚或盲补第二键；旧committed对保持。这里不同于event6已完成配对数据写的迟到观察，不能将两条路径机械合并。
8. **准备完成之后。** 两键读回在窗口内确认匹配后，原_mark_completed、EVENT_VERIFICATION_PENDING、Queue heartbeat/owner/推进继续；尾部晚到只附overrun，真实状态/健康/enqueue错误另标CCGP_FINALIZATION_RESULT_UNKNOWN并保留准备回执。不得因预算跳过原独立调度或释放，不改变既有异常/重试/终局协议。
9. **恢复。** 准备失败的重投沿原attempt重新完整核验并准备同周期；不直接用部分staging或旧watch跳过采集/门禁。已COMPLETED重复投递沿原ALREADY_COMPLETED结果，不另写数据。当前callback读回不能阻止读后并发变化，owner/CAS/跨崩溃恢复强保证仍NO-GO；若实施必须改变这些协议才安全，则停止，不扩大。

## 状态判定与行为验收

| 故障或结果 | 允许结论 |
| --- | --- |
| 工作过期 | 后续业务及准备停止，FAILED/503；原seed/元数据可能已变化，不能称全系统零写 |
| 普通发现/详情失败、候选超量/watch超量 | 整体准备拒绝；普通错误保留原有有界扫描，不推断全host失效；已知超量按上述准入点提前拒绝 |
| 首键写前拒绝 | 两准备键未尝试；旧committed及未解决pending保留 |
| staging写后/读回失败，watch未发出 | staging可能已变，watch NOT_ATTEMPTED，准备INCOMPLETE；不推进事件、不删除staging |
| staging匹配，watch写已发出但未知/迟到 | 两键逐项如实记录，不能说watch未写或双键准备完成 |
| 两写都返回，任一读回旧值/None/错误或超期 | 准备未获确认，FAILED/503，不把“调用返回”升级为提交 |
| 两键按时匹配，状态/健康/Queue尾部失败 | 保留PREPARED_LOCAL_READBACK与尾部未知；不是整源成功或公开提交 |
| 合法空发现/零watch且全部查询完整 | 仍保存/读回原候选与空watch，按原七阶段配对流程推进，不回填公开旧卡片 |

后续须只用既有MemoryCache/transport桩、冻结搜索/详情样本、假时钟与临时目录验证：入口/预检/seed原点；搜索/详情timeout和sleep；正常/异常/None/解析/merge/watch/digest超期；10查询完整空、12候选完整与13候选拒绝、watch超量；warm与cold初始化副作用口径；每个写/读回/摘要步骤的前后失败/迟到；错cycle/旧watch/None/不匹配、首键可能已变而次键未知；原committed/pending/其他源staging/成功时钟保护；准备完成后尾部失败、首次/最终失败、重复投递、foreign/owner；CLI无budget及既有事件/区域/publish不退化。代码变化后才跑必要Python及10/3，按实测新增数量记载，不预填通过数。

## 唯一五文件实施范围及当前结论

待下一轮明确授权，仅修改以下五个既有文件，另更新文档和artifact：

- `web/collector_queue.py`：ccgp同原点150工作预算及异常回执传递，保留原尾部语句/attempt/owner。
- `web/collector_runtime.py`：_run_ccgp预算、范围门禁、原双键准备/读回、逐键回执和run_stage分类；不改_cache_set、_cached_list、pending/健康/配对helper。
- `web/pipeline/scripts/sync_ccgp_query.py`：只给discover_candidates增加可选预算，复用原异常类、HTTP helper及已有lazy-import模式；scan_events不改。
- `web/pipeline/tests/test_runtime_source_parity_behavior.py`：复用既有runtime/MemoryCache/冻结样本，覆盖发现helper、事实阶段和双键准备全部边界；不新建引擎。
- `web/pipeline/tests/test_collector_orchestration_behavior.py`：入口原点、准备未完成不推进、原重试/降级/owner/独立源与尾部回执；其他模块不改。

本轮只标准库AST、源码行号/哈希、静态容量算术及既有JSON证据核对，应用仍5d2fe85；没有导入执行应用/SDK/模型/采集/测试，没有网络、实际环境值/凭据/运行日志、云端/业务/缓存/数据库/函数/Queue访问或部署/推送/计划权限及运行数据变更。具体静态核对数量见[摘要](validation/ccgp-discovery-stage-budget-contract-2026-11-07/validation-summary.json)与[清单](validation/ccgp-discovery-stage-budget-contract-2026-11-07/manifest.json)。

**离线方案有条件GO，当前实现和真实放行NO-GO。** 已完成具体方案；下一步属于用户上一轮明确禁止的“其他阶段预算”，自动推进停在此来源范围授权边界，不自动改ccgp代码或继续多轮模拟。apply_allowed、migration_usable=false。

[完整下一任务](next-task.md)为上述五文件离线实现授权提示词。当前界面无法生成该按钮；提供完整可复制提示词。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
