# R1 区域 runtime 详情单次调用明确拒绝止损：离线实现

2026-11-07（Asia/Shanghai）。起点7dac58bb44eb9654bb9927c900ce50b806e9ec8b，原代码a352b7a；现有分支codex/p0-reliability-contracts，初始工作树干净，仅根代理在途。读取最新用户指令、working-protocol/current-state/checkpoint/next-task、收口审查、CLI F1、区域F2、publish实现及行动雷达验收合同。前台15:19:34开始、15:39:34截止（UTC07:19:34–07:39:34）。

代码提交 **4916d69de3568e8bd22fc8d659da34833596c852**，恰好修改授权的 `web/collector_runtime.py` 和 `web/pipeline/tests/test_runtime_source_parity_behavior.py`；其余改动仅文档和新增验收artifact。`apply_allowed=false`、`migration_usable=false`；SDK及硬取消/原子提交/崩溃持久回执强保证分支保持CLOSED NO-GO。

## 先复现，再最小修复

使用实际run_stage入口、既有MemoryCache、冻结河北官方HTML及原parser，注入本地transport、假时钟。session不构造真实opener，通过object.__new__注入本地_read边界，实际执行既有warmup方法；不是新模拟引擎或真实SDK客户端。运行进程使用空的实际环境配置及固定本地PATH，网络与真实SDK导入阻断，测试文件输出只准临时目录。

在应用源码未修改时运行新增回归：1个unittest方法、主/备用×401/403/429共6个子例全部失败。每例首次拒绝后仍发出第二次同www host详情请求，期望1次、实际2次。见[修复前记录](validation/runtime-regional-access-stop-2026-11-07/before.json)及before.log。该次失败在请求次数断言处结束，未记录修复前canonical状态，不据此编造旧数据行为证据。

修复复用CLI现有 `access_block_reason`、`RATE_LIMIT_MARKERS` 和session的 `on_access_blocked` 回调：

最新代码定位：[区域函数](../../web/collector_runtime.py#L1323)、[集合/回调](../../web/collector_runtime.py#L1381)、[同host准入](../../web/collector_runtime.py#L1544)、[限流页识别](../../web/collector_runtime.py#L1555)、[复用拒绝分类](../../web/collector_runtime.py#L1572)、[新增回归](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L725)。引用绑定4916d69及文件SHA256，见source-references.json。

- 拒绝集合只存在一次区域stage函数调用内，按显式目标URL hostname判断。warmup的www明确拒绝会阻止后续www详情，搜索仍可通过独立host完成；www、裸ccgp.gov.cn、search.ccgp.gov.cn不按父域合并。
- 详情在请求前跳过已拒绝host，记录既有固定原因和该候选哈希；跳过也算未完成，原失败/503与fail-closed保持，不将跳过视作VERIFIED或合法空。
- HTTP401/403/429及已有包装码/显式cause复用现有分类器。限流HTML在adapter前识别；普通TimeoutError、URLError、NETWORK_ERROR、503和解析失败不登记host拒绝，继续独立候选核验。
- 既有发现阶段止损不变；270/210/60预算、请求timeout/sleep、提交边界、默认无预算调用、首次重试/最终降级、owner/lease、pending与健康协议均保持。成功核验的另一host不使不完整stage提交部分新canonical。
- 诊断仅原phase/reason计数及最多5个候选哈希，不保存host集合、URL、异常正文或秘密。包装异常的明确拒绝原因也保持固定分类码。

此处的host是显式请求URL，不增加urllib重定向链逐跳拦截，不是跨进程/跨部署冷却、Retry-After调度或硬取消。跳过详情可减少后续业务请求，不能撤销已经发出的请求或写入。

## 实际验证

新增 **12项行为测试**，目标runtime模块 **62项通过**；最终 **1157项Python、冻结模板10/10、原bootstrap CLI3/3全部通过**，0失败/错误/跳过。1157是本轮代码实际运行结果，原1145仅作新增数量基线。原CLI3/3继续隔离空事件watch，不能冒称完整事件验收。Node/JS未改未重跑。

| 行为 | 观察结果 |
| --- | --- |
| 主/备用首次401/403/429 | 总详情1次，同host后续0；FAILED/503、旧canonical及最后成功时钟保留 |
| 包装拒绝/显式cause/限流HTML | 同host后续0，marker页不调用adapter，固定原因诊断保留 |
| warmup明确拒绝或marker | www详情0；实际warmup一次，独立搜索继续；存在未核详情时503 |
| www与裸域交错 | 被拒绝host后续0；另一个合法host仍核验；整体不完整不提交 |
| 普通超时/网络/503/解析错误 | 同host后续候选继续，整体失败仍保护旧canonical |
| 主/备用完整成功、合法空 | 原COMPLETED、记录/空结果及fallback语义保持 |
| 下一次调用与无预算调用 | 拒绝集合不跨调用；原无预算入口同样获得止损 |

[20组回放](validation/runtime-regional-access-stop-2026-11-07/after-cases.json)直接调用新增unittest helper，记录请求host序列、解析次数、stage状态、旧canonical/其他源pending与ledger/成功时钟保护；不另建运行引擎。其余包装/诊断与预算/owner反例见实际测试源码和本轮测试输出。

完整回归覆盖既有F2超期/写前写后未知、pending/硬停、独立来源、foreign/owner拒绝、首次真实重试、第二次降级推进与publish ACK保护。外部连接/DNS及真实vercel SDK导入被阻断，既有loopback安全测试只连接本机测试桩；prewarm/generated输出来自既有本地替身，没有项目模型调用。所有回归输出先存临时目录，再归档为本轮本地artifact。

**528份起点data/fixture/历史artifact字节不变**，其余 **453份web/workflow文件不变**，包括CLI/helper、Queue、增量、publish实现（区域函数之外）、Node/SQL/版本、依赖与计划配置。仅runtime文件的区域函数及必要导入变化；源码、测试方法计数、变更范围和证据哈希由[静态验证器](validation/runtime-regional-access-stop-2026-11-07/verify.py)检查，不重复运行应用或测试。[证据清单](validation/runtime-regional-access-stop-2026-11-07/manifest.json)、[验收摘要](validation/runtime-regional-access-stop-2026-11-07/validation-summary.json)。

## 收口与下一优先项

**R1区域runtime单次调用子项已复现、修复并完成离线验收。** 不是全项目F1关闭；共享host冷却/Retry-After及其他阶段止损仍不在该实现内。R2其余14个deep阶段与7个增量源的时间预算、R3真实Preview版本/来源/公开发布/交付证据仍未完成。

唯一下一优先项：**仅离线文档，制定CCGP event1–event6共用事件阶段的时间预算与事实/事件配对提交合同**。六阶段复用同一helper且与CCGP canonical配对提交有关，适合先厘清准入、累计请求/sleep和恢复边界；不机械复制区域210秒，不直接写代码。真实Preview放行需额外明确授权，当前不启动；SDK和强保证分支不重开。

没有外网、凭据/实际环境值/运行日志查询、真实云端/业务接口/缓存/数据库/函数/Queue/模型访问，没有新环境/路由、计划/变量/权限/保护变更、部署/推送/workflow触发或运行数据/历史数据/公开快照写入。真实部署、来源恢复、持久化、延迟与客户交付均未核实。

[完整下一轮任务](next-task.md)读取本报告和最新HEAD，只做事件阶段合同文档。当前界面无法生成该按钮；提供可复制完整提示词。推荐GPT-6.1 Sol xhigh（超高），实际运行设置未核实。
