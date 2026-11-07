# Queue ccgp发现/事实协作式预算与双键准备：离线实现

2026-11-07（Asia/Shanghai）。起点6270b50，原代码5d2fe85，现有隔离分支codex/p0-reliability-contracts；初始工作树干净，仅根代理，无相关在途工作。读取最新指令、协议/状态/checkpoint/next-task、发现合同、事件实现及行动雷达合同。前台16:38:17开始、16:58:17截止（UTC08:38:17–08:58:17）。

代码提交 **fea6fc70350b17366f20a86eac9ec02396a36fa9**，恰好修改授权五文件：collector_queue.py、collector_runtime.py、sync_ccgp_query.py及既有parity/orchestration测试；其余为文档和新增验收artifact。apply_allowed=false、migration_usable=false；SDK、硬取消/严格时限、跨键原子性、自动回滚与崩溃持久回执强保证CLOSED NO-GO。

## 实际行为

- 仅Queue stage==ccgp沿入口原点注入总270/工作150/共同双键准备读回60/尾部60，包含预检与stage准入，不接payload deadline、不重置。原语snapshot reserve120是准备60+尾部60；事件/区域/CLI/增量/publish原预算保留。
- discover_candidates可选budget并在函数内延迟取得现有异常类；scan_events、CliBudget、HTTP helper均未改。搜索/详情cap30按剩余工作−1收紧，原sleep不足则拒绝，不压短、不增加重试。请求/普通异常/None、解析、去重/排序、详情append、merge/watch及每份候选digest返回均检查，迟到结果不成为新事实。
- 新Queue路径发现数超max_candidates时详情前整批拒绝；watch同时受计划上限和六片容量约束，不裁剪后称完整。无budget默认路径及CLI保持；committed对仍优先于raw基线，损坏committed拒绝，不回填公开snapshot。
- _cached_list/_cache_set不改；记录records/events初始化的调用开始/返回及可能写入旧seed。冷初始化晚到/返回未知仍可能已写raw旧版本，不能称全系统零写。旧committed、未解决pending、其他源兄弟staging及成功时钟保护有内存行为证据。
- 复用_digest，候选保持原staging字典和watch list；在min(prepare_started+60,t0+210)内严格按STAGING写→读回匹配→WATCH写→读回匹配。任一前后检查、I/O、摘要/类型/cycle/旧值/None失败或迟到，准备INCOMPLETE、FAILED/503，不推进event1，不补后键或回滚已发出写。
- 逐键写入NOT_ATTEMPTED/UNKNOWN/CALL_RETURNED_UNVERIFIED、readback NOT_ATTEMPTED/UNKNOWN/MISMATCH/LATE/MATCHED与mutation_possible分开；只有两键按时匹配才PREPARED_LOCAL_READBACK。source_transaction_committed始终false，准备匹配不是CCGP配对或公开提交，更不是持久化保证。
- receipt仅workflow结果/异常诊断，不进入staging/watch/公开snapshot。准备完成后的状态/健康/Queue异常保留准备回执并单独标未知；原首次重试、第二次降级、owner、独立来源和尾部顺序保持，不因预算跳过。

函数/行号与代码哈希见[source-references.json](validation/ccgp-discovery-stage-budget-implementation-2026-11-07/source-references.json)。配对提交、pending/健康/版本/Queue/lease协议未改；ccgp成功仍只表示准备，原EVENT_VERIFICATION_PENDING及七阶段最终成功时钟保持，不调用publish或提前写COMMITTED_STATE_KEY。

## 实际验证

新增 **21项行为测试**：parity中事实阶段12、发现helper3，Queue6。最终 **1202项Python、145项定向、冻结模板10/10、原CLI3/3全部通过**，0失败/错误/跳过。原1181仅作基线；原CLI3/3仍隔离空事件watch，不是完整事件验收。Node/JS未改未重跑。

| 验收边界 | 观察 |
| --- | --- |
| Queue预检145秒及伪payload deadline | 原点仍0、搜索timeout4，不重置150工作窗；stage准入耗尽零请求 |
| search正常/异常/None/解析/排序/sleep超期 | 停止后续类型请求，不返回发现集合；普通及时错误及无budget保留原有界行为 |
| 事实查询/详情/解析/merge/watch/digest超期 | 无新双键准备，保留旧committed、前序staging/watch、pending和成功时钟 |
| 合法空、12/13候选、计划watch上限100而发现31 | 完整空和12项可准备；13项详情前拒绝；31项仍受六片容量拒绝 |
| committed与raw不同、committed损坏 | 使用committed；损坏时零查询，不以raw或公开数据回填 |
| cold旧seed写入后晚到或抛错 | 源业务零请求，receipt披露可能已写，旧committed/pending保留 |
| 每键写前/写后抛错或写返回迟到 | 保留UNKNOWN或CALL_RETURNED_UNVERIFIED及可能变化；首键未确认则不发第二键 |
| 每键读回错误/None/旧watch/错cycle/摘要晚到 | 源准备503、逐键真实状态；不以写调用返回替代读回 |
| 两键匹配后的stage/健康/Queue尾部失败或迟到 | 保留PREPARED_LOCAL_READBACK与尾部未知/overrun，不撤销数据、不声称可靠完成 |
| 首次/最终失败、重复COMPLETED、foreign/owner | 原尝试限额与降级推进保持，已完成消息不重复准备，身份拒绝不执行阶段 |

[cases.json](validation/ccgp-discovery-stage-budget-implementation-2026-11-07/cases.json)直接复用本轮unittest helper归档44源阶段、10发现helper、4Queue尾部回放；没有新模拟引擎。使用既有MemoryCache、冻结天津大口屯官方HTML/manifest、已有搜索fixture、假时钟与临时目录；12/13扇出身份为测试合成查询参数，不冒充12/13个不同官方项目。

外网连接/DNS与真实SDK导入被阻断，进程使用空实际配置、-B禁止Python运行缓存写入，测试输出只准临时目录；既有loopback安全测试仅连接本机桩。prewarm/generated来自原有替身，没有项目模型调用。初轮5个迟到子例的测试注入把61误当绝对时刻，未跨过工作结束后才开始的准备窗口；已改为增加61秒，最终全部验证通过。最后补足committed优先和放宽计划后的六片容量反例后，重跑最终1202/145；没有删除既有测试方法。原不注预算用例以tjnothop替代新接入的ccgp，并由ccgp专门正反例覆盖其新语义。

**581份起点data/fixture/历史artifact及450份其他web/workflow文件字节不变**；静态AST确认runtime除_run_ccgp/run_stage、query除discover_candidates、Queue除process外均保持，原Queue尾部主体顺序保留。_cached_list、_cache_set、scan_events、CliBudget、HTTP/pending/健康/版本/配对helper、Node/SQL/依赖/计划均未改。[摘要](validation/ccgp-discovery-stage-budget-implementation-2026-11-07/validation-summary.json)、[证据清单](validation/ccgp-discovery-stage-budget-implementation-2026-11-07/manifest.json)。

## 未完成与唯一下一步

仅离线协作式调用者子项完成；默认336/744秒名义串行满范围按时、硬取消、严格270/300秒退出、跨键原子性、在途零写及崩溃后持久回执不保证。本地读回匹配不能阻止随后并发变化，真实SDK/部署/来源恢复/完整召回、真实持久化及客户交付未核实。

剩余7个医院/早期deep阶段与7个其他增量源未新增预算，共享host冷却/Retry-After及CCGP其他明确拒绝路径未在本轮实现。没有云端/凭据/实际环境值/运行日志或真实业务/缓存/数据库/函数/Queue/模型访问，无新环境/路由、计划/变量/权限/保护变化、部署/推送/workflow触发或运行数据/原始历史数据/公开快照写入。

唯一下一轮：仅文档复核**CCGP主链F1/F2/F3收口、剩余缺口与唯一优先项**，以本次及事件/区域/增量/publish最新实现绑定证据更新覆盖矩阵，最多三项实际剩余问题；不机械铺其余来源预算，不重复闭合项或重跑未变1202/10/3，不重开SDK/强保证分支。详见[next-task.md](next-task.md)。当前界面无法生成该按钮；提供完整可复制提示词。推荐GPT-6.1 Sol xhigh，实际设置未核实。
