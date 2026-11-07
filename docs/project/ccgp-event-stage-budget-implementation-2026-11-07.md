# Queue CCGP事件阶段协作式预算与配对写入回执：离线实现

2026-11-07（Asia/Shanghai）。起点1e2b496，既有代码4916d69，分支codex/p0-reliability-contracts；开始工作树干净，仅根代理，无相关在途工作。已读取最新指令、working-protocol/current-state/checkpoint/next-task、事件合同、区域R1及publish实现、行动雷达验收合同。前台15:50:56开始、16:10:56截止（UTC07:50:56–08:10:56）。

代码提交 **5d2fe858c5c478ebdcfbba53df1da9eadca1ed21**，只修改授权六个既有文件：collector_queue.py、collector_runtime.py、sync_ccgp_query.py及对应parity/orchestration/ccgp_events三个测试模块；另更新文档与新增artifact。SDK、硬取消/严格时限、原子提交和崩溃持久回执强保证保持CLOSED NO-GO；apply_allowed=false、migration_usable=false。

## 实际实现

- Queue仅event1–event6创建CliBudget总270/工作180，同一monotonic原点含payload/epoch/owner预检及stage准入，不接收payload deadline，不在runner重置。原区域/CLI/增量/publish预算与路由不变，ccgp发现阶段仍不接预算。
- scan_events可选接budget，向原搜索/详情helper传cap30、工作余量−1的timeout；不足原sleep间隔就拒绝，不缩短4秒，不新增HTTP重试。专门预算异常只在有budget时函数内延迟导入，避免与区域脚本的顶层导入形成环；无budget路径保留原CLI行为。
- 请求返回包含同步read/decode完成之后的检查，搜索/事件解析、None、普通异常返回、追加事件、每项目返回和merge均检查工作截止。预算先于generic catch重抛；迟到结果不成为新事件或discovery-only fallback。当前片全部项目/查询/详情完整、无失败且merge在180前完成才进入保存，不新增逐项目checkpoint。
- event1–5仍只写周期staging；event6要求原records为list（合法空允许）、所有前序COMPLETED及原pending检查，再单键写records/events配对状态。watch超过六片容量30时请求前拒绝；不裁剪范围后称完整。候选字典复制后更新events，不原地修改读取对象，保留前序已核验兄弟staging。
- 单批数据保存局部截止min(save_started+30,t0+210)，读取原records、pending验证及写前逐步检查。CliBudget原语snapshot显示finalize_reserve_seconds=90，实际是批次保存30+尾部60；没有改原语或把90误报成全部尾部60。
- 写前失败走EVENT固定预算错误及原FAILED/503、retryable=True。区分STAGING/COMMITTED_PAIR目标、write_attempted、write_call_returned、mutation_possible及NOT_ATTEMPTED/UNKNOWN/CALL_RETURNED_UNVERIFIED。缓存调用正常返回不等于真实持久化确认；返回迟到仅标save_window_overrun/total_overrun，沿原完成/状态/健康/Queue尾部，不改称写前拒绝或回滚。
- stage/健康保存失败保留数据写回执并标EVENT_FINALIZATION_RESULT_UNKNOWN；失败状态本身不能保存为EVENT_FAILURE_STATE_RESULT_UNKNOWN。Queue保留原异常类型与重试/终局/owner顺序，只给事件异常附带回执及工作流可能变化信息；不因预算新增尾部短路。原publish尾部逻辑保持。

代码函数与版本定位见[source-references.json](validation/ccgp-event-stage-budget-implementation-2026-11-07/source-references.json)。receipt只进入workflow结果/异常诊断，没有进入staging/committed配对数据或公开snapshot，不改健康schema、pending、版本、Queue/lease或配对提交协议。parent.work_complete只是扫描/merge完成，不是数据或公开提交证明。

## 实际验证

新增 **24项行为测试**：事件helper7、runtime12、Queue5；最终定向 **139项**及完整 **1181项Python**全部通过，0失败/错误/跳过；冻结模板 **10/10**、原bootstrap CLI **3/3**通过。原1157为新增数量基线；3/3仍隔离空事件watch，不是完整事件业务验收。Node/JS未变未重跑。

| 边界 | 离线观察 |
| --- | --- |
| Queue预检175秒、伪payload deadline | 原点仍0，HTTP timeout为4；不重置180工作窗 |
| stage准入/读取watch或staging时耗尽 | 零业务请求；旧committed、前序staging与成功时钟保持 |
| search/detail正常、异常、None及解析返回超期 | 立即停止后续请求，不记新事件、不走迟到fallback |
| sleep不足/醒来超期、五项目慢响应 | 不缩短间隔；整片拒绝，不保存当前片部分事件 |
| event1–6五项目快响应、合法空/无新事件 | 各片使用同一parent；前五片仅staging，最终片单键配对；成功时钟仍需七阶段完成 |
| 31项目、旧pending、原records缺失/损坏、保存准入或pending检查超期 | 写前拒绝，旧配对、兄弟staging及独立源pending保留 |
| 写前抛错/写后抛错 | 均UNKNOWN、mutation_possible=true，实际内存可不变或已变，不声称零写/回滚 |
| 数据写正常返回时保存或总窗口已到期 | CALL_RETURNED_UNVERIFIED与overrun保留，原COMPLETED/收尾路径保持 |
| stage/健康/失败状态/Queue heartbeat或enqueue错误 | 数据回执与尾部未知分开；保留原异常/尝试限额，不冒称可靠完成 |
| 首次/第二次失败、重复COMPLETED投递、foreign/owner替换 | 首次真实重试、第二次降级推进，无第三次扫描；已完成投递复用原结果，owner拒绝后不推进 |

[cases.json](validation/ccgp-event-stage-budget-implementation-2026-11-07/cases.json)直接复用本轮unittest helper记录35组源阶段、13组HTTP/helper及4组Queue尾部观察，不另建模拟层。使用既有MemoryCache、事件样本、假时钟与临时目录，外部连接/DNS及真实SDK导入被阻断；导入顺序子进程也有独立阻断器。已有loopback安全测试仅本机测试桩，prewarm/generated为既有替身，没有项目模型调用。

初轮定向发现CollectorStageBlocked默认diagnostics=None，合并回执时需按空字典处理；已修复后通过。最后复核还修正了Queue尾部测试的原点：必须由0推进到280，而不是从280开始，最终1181与139均在该最终测试版本通过。旧“非区域不注预算”用例改为覆盖tjmugh/ccgp，事件新预算由专门正反例验证；未删旧测试方法或放宽其他门禁。

**556份起点data/fixture/旧artifact字节不变，449份其他web/workflow文件不变**。静态AST确认runtime除事件函数/run_stage、query除scan_events、Queue除process函数外均保持；Queue原尾部语句序列完整保留，只在外围附加事件诊断。CliBudget、共享HTTP helper、_cache_set、pending/健康/版本/Node/SQL/依赖/计划均未改。[验收摘要](validation/ccgp-event-stage-budget-implementation-2026-11-07/validation-summary.json)、[证据清单](validation/ccgp-event-stage-budget-implementation-2026-11-07/manifest.json)。

## 未完成与下一步

仅离线调用者协作式子项完成；不能保证同步HTTP/缓存取消、满五项目或默认30 watch按时完成、严格270/300秒退出、原子owner/配对提交、在途零写或崩溃后回执持久化。正常缓存调用返回仍可能不足以证明真实持久化。事件共享host拒绝止损/跨进程冷却/Retry-After未实现，本轮没有将其混同预算完成。

真实部署、来源恢复/覆盖、公开发布、实际延迟和客户交付未核实。剩余8个deep阶段（ccgp及七个医院/早期源）和7个其他增量源未新增本轮预算。无外网、真实SDK/项目模型、凭据/实际环境值/运行日志、云端/业务/真实缓存/数据库/函数/Queue访问，无部署/推送/workflow触发、新环境/路由或计划/变量/权限变更，无运行数据、原始历史数据或公开快照写入。

唯一下一优先项：仅离线制定**CCGP发现/事实阶段预算与staging/watch保存合同**。它是六个事件阶段的前置输入，仍未接预算；先审查其完整发现/详情及双键准备边界，不照搬180/210秒，不直接实现或扩文件。[完整下一任务](next-task.md)。当前界面无法生成该按钮；提供完整可复制提示词。推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
