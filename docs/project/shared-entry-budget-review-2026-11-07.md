# 共享官方入口限流与重试预算：离线审查

2026-11-07（北京时间）00:43:55开始，前台截止01:03:55。起点d9882a0，工作树干净，仅根代理运行。已读取最新任务、协议、状态/checkpoint、SDK关闭决策、事件重试/来源精度报告与相关源码/既有测试。SDK工作流保持关闭。本轮没有联网或执行采集、业务/SDK/缓存函数，也没有运行测试；以下是静态调用链和当前测试覆盖的审查，不是新增线上故障复现。

## 调用链与隔离边界

| 路径 | 源码调用链 | 当前限额/处理 |
|---|---|---|
| 天津CCGP发现 | [runtime:673](../../web/collector_runtime.py#L673) → [sync_ccgp_query.discover_candidates:160](../../web/pipeline/scripts/sync_ccgp_query.py#L160) → [fetch_search_page:244](../../web/pipeline/medical_channel_pipeline/ccgp_discovery.py#L244) | 同入口`search.ccgp.gov.cn/bxsearch`，每请求默认30秒，关键词间/公告类型间固定4秒；失败记入failures后循环继续 |
| 天津/区域详情及事件详情 | [runtime:705](../../web/collector_runtime.py#L705)、[区域:1492](../../web/collector_runtime.py#L1492)、[事件扫描:85](../../web/pipeline/scripts/sync_ccgp_query.py#L85) → [fetch_ccgp_detail_html:1433](../../web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1433) | 详情实际host为www.ccgp.gov.cn或允许的裸域，默认30秒；源码保留HTTPError异常链但没有消费Retry-After |
| 区域runtime发现 | [runtime:1371](../../web/collector_runtime.py#L1371)每阶段新建session → [fetch_candidates_page:182](../../web/pipeline/scripts/sync_regional_ccgp.py#L182) → [session.fetch:85](../../web/pipeline/scripts/sync_regional_ccgp.py#L85) | 首页warmup最多30秒＋固定1秒；搜索默认90秒，发现明确限流/401/403/429已立即阻断该阶段 |
| 区域独立CLI | [main:229](../../web/pipeline/scripts/sync_regional_ccgp.py#L229)共用该CLI内一个session → markets/keywords/types，必要时national fallback | 五地区×五关键词×两类型，单市场详情上限10；4秒间隔，异常收集后继续；无跨进程共享状态 |
| 医院增量/深度 | [增量发现:539](../../web/collector_incremental_runtime.py#L539)、[详情:593](../../web/collector_incremental_runtime.py#L593) → 源适配器/同步脚本retry helper | 如[TEDA:71](../../web/pipeline/scripts/sync_teda_market_research.py#L71)最多3次、[TJZYEFY:71](../../web/pipeline/scripts/sync_tjzyefy_market_research.py#L71)最多2次；按固定delay重试，非共享host冷却 |
| Queue外层 | run_stage → [worker:491](../../web/collector_queue.py#L491)检查retryable/retry_exhausted | 本轮attempt预算与平台投递是另一层；[配置:18](../../web/vercel.json#L18)maxDuration300、maxDeliveries3、retryAfter150，不能代替各HTTP请求的剩余阶段预算 |

search.ccgp.gov.cn和www.ccgp.gov.cn是**不同host**。共同父域不证明服务端共享限流，不建议一处超时就停止整个ccgp.gov.cn。应按实际入口/host记录反馈，只有经确认的共享策略才合并。当前GitHub天津/区域workflow的[同branch concurrency组](../../.github/workflows/regional-medical-refresh.yml#L36)已串行化；d内deep/incremental也有owner互斥。它们都不等价于跨branch、跨epoch、CI与Vercel之间的官方入口协调；本轮未确认这些执行者当前同时运行。

## 已修/已有机制，不重复报修

| 机制 | 当前源码与既有测试证据 | 本轮判断 |
|---|---|---|
| runtime区域发现限流止损，旧canonical不变 | [runtime:1405](../../web/collector_runtime.py#L1405)、[test_runtime_source_parity_behavior:353](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L353)期望fetch只1次 | 已有覆盖，不能再报“区域runtime发现持续查询” |
| runtime区域部分发现/详情失败不提交 | [runtime:1512](../../web/collector_runtime.py#L1512)在_cache_set前拒绝；[既有测试:311](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L311) | 已有覆盖，不推定存在部分canonical成功 |
| 最后实际失败立即降级推进，无额外一轮等待 | [worker:500](../../web/collector_queue.py#L500)、[测试:147](../../web/pipeline/tests/test_collector_orchestration_behavior.py#L147) | 已修。F2关注一次阶段执行内部的墙钟预算，不重复旧终局等待问题 |
| 首次瞬态失败保留正常重试；确定性403不反复花attempt | [测试:136](../../web/pipeline/tests/test_collector_orchestration_behavior.py#L136)、[176](../../web/pipeline/tests/test_collector_orchestration_behavior.py#L176)；[TEDA分类测试:365](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L365) | 不把普通网络超时改成全host永久熔断，不删除有界瞬态重试 |
| 主阶段已DEGRADED不再无效等待fallback | [测试:226](../../web/pipeline/tests/test_collector_orchestration_behavior.py#L226)；FAILED/RUNNING仍保留正确依赖处理 | 已修，不重复 |
| 12条详情上限、deferred/pending保留、硬停恢复 | [test_collector_deferred_budget:106](../../web/pipeline/tests/test_collector_deferred_budget.py#L106)、[198](../../web/pipeline/tests/test_collector_deferred_budget.py#L198)、[251](../../web/pipeline/tests/test_collector_deferred_budget.py#L251) | 数量和状态安全已有覆盖；不等于HTTP墙钟预算或入口限流协调 |

以上测试本轮仅阅读，未执行；历史通过不能写成本轮新验证。

## 三项优先问题（全部尚无本轮行为/线上复现）

### F1 / P1：入口限流反馈与止损在路径间不一致（静态设计缺口）

触发条件：明确HTTP429、官方“访问频繁”页或明确拒绝访问。区域runtime发现能在该次查询后退出，但[Tianjin discover:183](../../web/pipeline/scripts/sync_ccgp_query.py#L183)把异常记下并继续公告类型，调用方继续后续关键词；[runtime详情:718](../../web/collector_runtime.py#L718)、[区域详情:1509](../../web/collector_runtime.py#L1509)也记录后继续后续项目。区域CLI[scoped catch:288](../../web/pipeline/scripts/sync_regional_ccgp.py#L288)、[fallback catch:323](../../web/pipeline/scripts/sync_regional_ccgp.py#L323)不会统一结束其他查询。Retry-After在所审请求/重试链未被消费，医院helper按固定sleep重试429；不同地区阶段还会各自新建session。

因此当前源码没有显示可向同入口其他扫描者传递的统一冷却/请求预算。本结论不证明当前发生了并发冲击，也不声称Retry-After头被物理删除（HTTPError异常链仍可能保留）。旧环境/历史限流仅为历史背景。

最小修复分层：先在同次调用内统一明确限流/拒绝分类和停止后续请求，保留普通单项目超时的有界容错；原异常原因及已有canonical/pending安全规则不变。再设计按实际host/入口协调的冷却/Retry-After预算，跨进程存储/原子性需另审，不能用本地dict伪称跨部署共享，也不能为了协调重开已关闭RuntimeCache SDK分支。

准确涉及文件：sync_ccgp_query.py、sync_regional_ccgp.py、collector_runtime.py、ccgp_discovery.py/ccgp_detail.py，以及实际接入的医院retry helper。后续验收须用现有框架离线证明：明确429后后续同入口请求0；其他host不被误停；一般网络超时不触发全入口熔断；Retry-After解析/上限/剩余预算正确，跨进程协调不能仅靠同对象测试宣称完成。

### F2 / P1：请求超时/固定sleep未接受阶段剩余墙钟预算（静态设计缺口）

[区域session:74](../../web/pipeline/scripts/sync_regional_ccgp.py#L74)的warmup30秒＋1秒、搜索90秒及4秒间隔，和[runtime区域循环:1377](../../web/collector_runtime.py#L1377)的多次请求没有共同monotonic截止参数；[详情接口:1433](../../web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1433)支持独立timeout，但调用方未传剩余预算。医院增量在[593行](../../web/collector_incremental_runtime.py#L593)逐项sleep/verify，candidate数量上限也不等于剩余时间。

例如按当前区域plan，5关键词×2类型=10次搜索；仅一次warmup＋3个各耗满90秒的搜索＋固定等待就可能超过300秒worker配置。这是参数组成的静态耗时情形，不是实际延迟测量；urllib timeout也不是整段响应/整个扫描的硬墙钟保证。Queue终局立即推进的修复不能让尚未返回的阶段函数提前发现耗尽。

最小修复文件：collector_runtime.py、collector_incremental_runtime.py、sync_regional_ccgp.py及被调用的HTTP helper。将阶段monotonic剩余预算传到warmup、请求和每次sleep，预留失败状态/pending保存与返回时间；预算不足不再发新请求或睡完整间隔。既有事实时钟cycle_as_of不能拿来计算执行剩余时长。

后续验收：假时钟覆盖“启动前不足、warmup耗尽、重试/sleep前不足、返回超期”，确认后续请求0、真实可用剩余预算被传入、状态保留不冒充完整；不能把thread future停止等待说成底层请求已取消，不修改云端时长/计划来掩盖缺口。

### F3 / P1（建议先处理）：区域CLI部分失败仍可成功退出（静态可达流程缺口，待离线CLI复现）

[sync_regional_ccgp:350](../../web/pipeline/scripts/sync_regional_ccgp.py#L350)仅在所有scoped＋fallback查询总成功数<=0时拒绝；一旦至少一条成功，其他市场/查询/详情的失败仅进入report。[440行](../../web/pipeline/scripts/sync_regional_ccgp.py#L440)随后合并，471/472行写records和report，478行return0，没有runtime那样的“任一失败阻断本源提交”门禁。

实际仓库工作流[96行](../../.github/workflows/regional-medical-refresh.yml#L96)调用该CLI并把records-output指向历史文件；下一步[106行](../../.github/workflows/regional-medical-refresh.yml#L106)在命令成功后发布组合快照。[publish_web_snapshot:154](../../web/pipeline/scripts/publish_web_snapshot.py#L154)读取canonical/event数组，不接受regional_sync_report作为采集完整性门禁。事实验证与本次扫描完整性是两回事：已有/new记录可能仍全是合法facts，但失败扫描不应仅凭退出0当完整刷新。

这与现有[验收合同第32行](action-radar-acceptance-contract.md#L32)的单源fail-closed边界需要对齐：失败源不发布部分新事实，其他独立来源可继续，降级覆盖须明确。当前CLI没有提供与runtime等价的完整性放行边界；本轮据此列为优先复现项，不直接宣称发生过线上违规。

这说明存在需要CLI负例验证的静态路径，**不证明该工作流目前已启用、不证明发生过部分发布，也不把正确facts称为伪造**。它不同于已修的天津bootstrap CLI3/3，也不同于runtime区域失败阻断，不能用那两组历史门禁代替本CLI验收。

建议最先用现有冻结样本/既有unittest方式复现，再最小修复sync_regional_ccgp.py：在任何records输出前判定本批是否完整，部分查询/详情/限流失败返回非零且保留原records字节，诊断可写到显式本地report；完整合法空成功，不从旧快照凑完整，不改工作流定时或扩大权限。此举可让现有set-e阻止后续发布，无需先接入云端缓存或改SDK。

第一步可以采用保守的整批阻断；这不等于已实现每市场独立提交/覆盖水位，不能用它冒充该后续能力。其他runtime来源继续执行的现有行为应保持不变。

后续实际CLI验收：全成功、完整空、部分scoped失败、部分详情失败、单条限流、所有失败、fallback局部失败；非完整情况records输入和既有输出不变、exit非0、report理由明确；不改原始数据，candidate/report仅系统临时目录或新增验收目录。已完成的市场/产品解析和runtime部分提交门禁保持通过。

## 权限、验证与下一轮

本轮仅解析/阅读本地源码、计划、工作流和既有测试，做引用/文件hash完整性检查；未新增测试、mock或HTTP执行器，未运行CLI/业务函数/SDK/测试套件，未联网或查询项目元数据/日志/凭据/环境值，没有应用、锁文件、计划、权限、路由、环境、部署、推送或运行数据变化。SDK分支仍关闭，apply_allowed=false、migration_usable=false。1031/10/3仍为历史门禁。

建议下一轮仅在明确授权本地代码/测试修改后，先离线复现并修复F3；F1/F2留作分立后续，不一轮引入共享缓存、调度变更或全量重构。[下一轮完整任务](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际运行设置未核实。
