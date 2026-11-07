# publish调用者侧协作式预算与ACK保真：离线实现

2026-11-07（Asia/Shanghai）。起点9e61edb，既有代码b584bcf；分支codex/p0-reliability-contracts，初始工作树干净、仅根代理，无相关在途工作。复用用户选定并已就绪的现有环境，没有新建环境。前台开始2026-11-07T05:30:20Z，截止05:50:20Z；已读取最新指令/协议/状态/checkpoint/next-task、publish合同、增量/区域实现及行动雷达合同。

代码提交 **a352b7a8dcb0dba3112c3dde9fd91db14b9603d4**。只修改授权七文件：三个调用文件与四个既有测试模块，另加文档和验收artifact。SDK保持CLOSED NO-GO，apply_allowed=false、migration_usable=false。没有Node/SQL/版本/数据库helper、CliBudget、JS、依赖、workflow或平台配置变化。

## 实际行为

代码定位：[_new_publish_receipt](../../web/collector_runtime.py#L1608)、[_persist_verified_snapshot_durably](../../web/collector_runtime.py#L1642)、[_run_publish](../../web/collector_runtime.py#L1729)、[run_stage](../../web/collector_runtime.py#L1902)、[process_collector_payload](../../web/collector_queue.py#L429)、[_publish_snapshot_if_ready](../../web/collector_incremental_runtime.py#L515)。

- Queue仅新增deep publish预算注入，与区域一样使用入口原点total270/work210/final60，预检/owner/heartbeat耗时不重置，payload deadline忽略。其他stage/来源原预算与调用边界保留。原attempt、终局publish失败释放owner及独立tick逻辑不变。
- _run_publish/_persist_verified_snapshot_durably接可选budget，用同一clock检查读取、merge/构造、健康投影、digest/JSON、LATEST和PUT准入/返回。tjzyefy传原parent budget，publish_work_deadline=min(parent.started+210,parent.started+total−60)，不误用parent180，不改原270/180/30/60。
- PUT cap30，timeout=min(30,publish_work_deadline−clock−1)，余量<=1零PUT，零本地HTTP重试。同步调用仍不可强制取消。读取/构造超期不发送新候选；LATEST已写入时保留其可能变化标记，不称全系统零写。
- ACK严格校验HTTP200、ok is True、durable_committed is True、非空精确snapshot_as_of及type(count) is int并匹配。坏JSON、缺/false/非布尔提交标记、错版本/数量、网络/非200为UNKNOWN；从未调用urlopen才NOT_ATTEMPTED。**先验证ACK，再观察迟到**；合法迟到ACK始终CONFIRMED。
- Node cache_status与Python副本独立记录；Node RETRY_REQUIRED/UNKNOWN不被Python READY覆盖。确认后总预算不足可跳过可选Python副本；写入/读回迟到或失败为RETRY_REQUIRED，不能倒推权威失败。异常副本状态（含对象/缺失字段）也不抹掉合法durable ACK。
- receipt仅在workflow结果/异常diagnostics，绝不放入snapshot，wire/latest/published内容保持同一份候选，source_health和snapshot_as_of不被预算字段修改；candidate_digest_local只是本地digest，不是未返回的数据库hash。parent.work_complete不作为公开提交证明。

## 故障与回执

| 本地观察 | 实际结果 |
|---|---|
| 读取/merge/build/health/digest/JSON/LATEST/PUT前超期 | 停止后续PUT，NOT_ATTEMPTED；LATEST可能已写。原FAILED/503和重试限额保持，不能说所有元数据零写 |
| PUT发出后错误、坏ACK或未获确认 | UNKNOWN，不排除Node已经提交。workflow FAILED不是权威回滚证明；不新增HTTP重试或换时间戳绕过冲突 |
| 合法ACK返回210/270之后 | CONFIRMED+ack_after_work_deadline/overrun观察，deep工作完成才记true；不抛写前预算错，不把已提交降为未提交 |
| Node副本未确认、Python副本正常 | 保留Node原状态、Python READY，聚合仍RETRY_REQUIRED；不假设真实物理绑定或宣称已修复Node副本 |
| Python副本无余量/写读失败或迟到 | SKIPPED_BUDGET或UNKNOWN，聚合RETRY_REQUIRED；authority仍CONFIRMED。已发出写可能完成，不回滚 |
| stage完成状态保存失败 | PUBLISH_FINALIZATION_RESULT_UNKNOWN，保留CONFIRMED与workflow_state_mutation_possible，不另写FAILED公开状态、不保证COMPLETED持久化 |
| 失败状态本身保存失败 | PUBLISH_FAILURE_STATE_RESULT_UNKNOWN，保留原发布回执、原错误与保存错误类型，不假称FAILED已可靠保存 |
| Queue heartbeat/reconcile/tick/owner释放I/O失败 | PUBLISH_QUEUE_FINALIZATION_RESULT_UNKNOWN，保留已确认/未知发布及真实错误类型；原顺序保持，不因budget添加中途收尾异常 |
| owner已替换 | 原heartbeat/身份拒绝保持，不清理新owner；本次已确认公开快照不被撤销 |
| tjzyefy helper/后续bucket/lease | 同一parent传递；helper错误diagnostics决定NOT_ATTEMPTED或UNKNOWN，已确认后bucket失败仍保留snapshot_refreshed=true；lease既有scan_result携带新receipt |

无budget调用同样消费现有durable_committed ACK字段；无budget的PUT错误回执合并会保留外层已写LATEST标记，不被内层默认false覆盖。原缺canonical拒绝、合法完整空、CCGP committed records/events对优先、未解决pending和最后成功源健康时钟均保持。旧NO_REFRESH语义保留，不将bucket或parent工作完成等同公开发布确认。

已确认之后的stage/bucket/heartbeat/pending按证据reconcile/tick/owner/lease收尾保持原顺序，270之后仍可能发生原有收尾/在途I/O。实际I/O失败会按原顺序中断后续步骤，不能声称之后的tick/释放必已完成；预算本身不新增收尾短路。回执仅本次调用观察，不是跨崩溃持久回执。

## 验证

新增**24项行为测试**：发布环境/ACK模块7项、runtime source行为7项、Queue编排6项、增量deferred模块4项。最终**1145项Python回归全部通过（22.913秒）、冻结模板10/10、原CLI3/3通过**。原CLI3/3仍隔离空事件watch，只证明候选/发现门禁，不是完整事件验收。Node/JS门禁未执行，只核对源码和版本未变。

[21组publisher回放](validation/publish-budget-implementation-2026-11-07/publisher-cases.json)、[17组PUT/ACK回放](validation/publish-budget-implementation-2026-11-07/put-cases.json)、[6组Queue尾部回放](validation/publish-budget-implementation-2026-11-07/queue-tail-cases.json)复用现有unittest helper/MemoryCache/HTTP桩、假时钟与临时目录，无新引擎。覆盖各阶段超期、parent195秒时timeout14、坏/迟到ACK、双副本、候选wire不含receipt、缺canonical/合法空/committed对、其他源pending/健康、确认后状态/尾部失败、owner替换和非预算调用标记合并。

完整回归曾发现既有TEDA/TJFCH源码门禁要求保留显式cache.get语句；已保留真实读取，在前后增加检查，没有修改这些测试或放宽保护。最终1145包含既有区域、CLI、pending/硬停、终局/租约及版本保护回归。回归中的prewarm/generated输出为本地替身；外网与真实vercel SDK导入被阻断，已有loopback安全测试只连接本机桩，无项目模型调用。

503份9e61edb已有data/fixture/历史artifact逐一SHA256不变；代码差异恰好为授权七文件。Node/SQL/版本/CliBudget/JS/workflow/依赖配置静态未变。证据见[manifest](validation/publish-budget-implementation-2026-11-07/manifest.json)与[摘要](validation/publish-budget-implementation-2026-11-07/validation-summary.json)；静态verify.py只核对源码/提交哈希、计数、回放回执与保护输入，不重复执行应用或测试。

## 边界与未完成

无外部联网、真实SDK安装/执行、凭据/实际环境值/运行日志查询、真实云端/业务接口/缓存/数据库/函数/Queue/模型调用；无环境/路由/计划/变量/权限变化、部署/推送/workflow触发或运行数据/历史数据/公开快照写入。仅测试桩中的合成环境配置，未查询真实配置；旧日志类artifact仅字节哈希，不解析日志。

真实部署、源恢复/覆盖、真实持久化及端到端延迟均未核实。硬取消/严格时限/在途写零变化、原子owner/跨key提交/回滚、崩溃后可靠回执和UNKNOWN自动对账继续CLOSED NO-GO；不重开SDK审计、不追加模拟补证。其他医院/事件/增量来源未新增预算，不能把本局部实现称为全runtime F2完成或Production准入。

下一轮仅文档做F1/F2/F3工程收口审查，复用已完成结果建立覆盖矩阵，最多列三项仍有最新依据的缺口、给唯一下一优先项或暂停结论；不继续机械扩预算、不重跑未变1145/10/3。详见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。
