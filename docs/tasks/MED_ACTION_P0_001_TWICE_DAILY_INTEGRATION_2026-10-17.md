# MED-ACTION-P0-001：三源与单用户双时段的集成约束

日期：2026-10-17。状态：**DESIGN_ONLY / IMPLEMENTATION_PENDING / RELEASE_BLOCKED**。

> 实施进展：隔离分支已完成[三源离线准备/提交核心](../ops/source-parity-offline-20261017.md)，25项新增＋107项相关回归通过。本文保留原设计目标；真实transport/范围证据、三个stage正式注册及25stage发布契约仍未实现，当前产品仍22stage/history-only，不宣称设计已全部落地。

本轮只冻结设计、文件范围和验收条件，没有修改产品、运行测试或调用采集/模型。用户既有的单用户早午各一次要求优先于任务文件中的高频建议。没有发布、数据恢复或删除部署授权。

## 1. 唯一基线与证据关系

| 对象 | 精确版本与用途 |
| --- | --- |
| 实现起点 | PR75 `ca91df269636d8604814d2e744d12587b8fadc82`，分支 `fix/tjmugh-verification-20261002`；本轮GitHub读回仍draft/open/unmerged |
| 已验证产品祖先 | `8b4b749bf057ed3f5a9b830fdef84ecc04bb1bd2`；879项CI、98项定向及终点竞态独立审查均为既有证据，不重新计数 |
| 最新main | `3216fd940dabfa7714383b6436908f9b72ff8a9c`；相对共同祖先62299590…只新增4个任务/策略文档，不能据此宣称runtime已修复 |
| 生产 | 旧报告最后明确读回为62299590…/`dpl_DW5wrMzvVXS7TLmbqUL1vSfcyuh1`，时间2026-10-03；**本轮未重查Vercel，不称其为10月17日实际生产** |

10月7日的[原P0任务](https://github.com/wpuu/MedicalChannelAI/blob/3216fd940dabfa7714383b6436908f9b72ff8a9c/docs/tasks/MED_ACTION_P0_001_RUNTIME_SOURCE_PARITY_2026-10-07.md)、[差距审计](https://github.com/wpuu/MedicalChannelAI/blob/3216fd940dabfa7714383b6436908f9b72ff8a9c/docs/strategy/ACTION_RADAR_GAP_AUDIT_2026-10-07.md)及[gold set](https://github.com/wpuu/MedicalChannelAI/blob/3216fd940dabfa7714383b6436908f9b72ff8a9c/docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md)作为需求证据引用，不把旧main产品覆盖到PR75。PR76的北京预算组件只是离线原型，不直接合入或声称其已解决真实接续。PR74/77不混入本任务。

本轮后续文档提交会产生新HEAD；产品blob必须与8b4b749完全一致。新文档HEAD不冒充新CI产品验证，旧HEAD的审批不继承。下一实现分支从最终文档HEAD创建，先明确设置该**具体分支**的`deploymentEnabled=false`才允许推送；不靠分支命名推断Preview已禁用。

## 2. 统一后的调度与执行面

- 保留两条独立每日Cron：`20 0 * * *` morning、`20 4 * * *` noon，北京时间名义08:20、12:20。Hobby小时级触发，不依赖精确分钟；实际套餐与线上enabled仍需另读控制面。
- 沿用`twice-daily-v1`、中国日期/period周期ID、首次真实触发时钟，以及08:00–10:00/12:00–14:00右端不含的入口窗口。新增stage不改变payload结构或调度版本；无在途兼容迁移，实际旧部署分区仍必须隔离/静默。
- 三个源作为**每个周期内的三个独立Queue stage**，插在现有tjfch后、regional_bj前。`STAGE_ORDER`由22项变25项；三个stage加入`PUBLISH_REQUIRED_STAGES`，已有区域fallback的条件门禁不变。
- 每条消息只处理一个stage；共享现有topic/group、cycle fence、Queue幂等键和实际串行消费者门禁，不新增Cron、topic、订阅组或服务。
- 不把三源加入旧incremental allowlist，不启用15分钟tick、60/120分钟轮询或GitHub fallback。旧incremental payload继续被拒绝；终点保留ACTIVE marker，不恢复get/delete释放方式。

## 3. 来源、身份和既有缓存复用

| stage ID | canonical source前缀 | 既有独立v2 key |
| --- | --- | --- |
| `tjzyefy` | `tjzyefy:` | `medicalchannelai:collector-tjzyefy-records:v2` |
| `tjzyefy_intent` | `tjzyefy-intent:` | `medicalchannelai:collector-tjzyefy-intent-records:v2` |
| `tjzxfc` | `tjzxfc:` | `medicalchannelai:collector-tjzxfc-records:v2` |

stage的下划线与intent source/key的连字符必须显式映射。复用PR75的`PRESERVED_SOURCE_RECORDS_KEYS`，不迁移到新key、不把intent混入research、不把同一数组在发布时拼入两次。复用六个既有discovery/detail模块及各自stable ID；不复制parser，也不直接执行带文件输出/历史初始化的sync脚本main。

只接受真实运行态的完整数组：schema、source前缀、天津归属、ID身份均合法；保留旧canonical全部历史ID，新增核验成功后用既有`merge_canonical_records`合并。任一必需key缺失/损坏仍阻断；空数组必须来自可验证真实恢复，不能代码补`[]`。不从repo/live/seed/bundled/public cards自动bootstrap，不因本周期抓到少数新公告而宣称旧历史完整。

source内先在内存完成本次范围的discovery、verification、验证和merge，再提交该source。supported/unknown详情失败、范围未知或预算不足时，该source不提交半成品；其他已成功stage的canonical不自动回滚，但公开durable/cache版本保持最后已接受数据。所有写入保留当前cycle所有权检查；这不是CAS或任意并发原子保证，仍依赖实际消费者串行和排除旧写入。

历史key沿用无主动TTL的稳定保存约定；新写入不能误用`_cache_set`默认14天TTL。若需无TTL写法，必须保留同等cycle fence和写后读回，不绕过保护。逐出后继续阻断。

## 4. 范围完整性、成本与异常语义

候选起始参数为每源30日lookback、每stage最多3条详情、至少3秒详情间隔、每个请求最多2次总尝试，仅瞬态错误重试。这些是待测试工程上限，不是已验证的在线容量。

必须在截断前计算范围内全部候选，不能直接依赖`select_candidates_since(max_candidates=...)`的截断结果宣称范围完整。发现候选超过3条、索引页不能证明覆盖该时间窗、长暂停缺口超出可验证窗口，或响应结构不能证明是有效索引时，stage阻断并保留旧版本；不只处理前3条就标成功。来源分页/索引范围无法在现有adapter能力内核验时，报告具体最小扩展，不能猜URL或放宽范围。持久游标/跨Queue预算接续留作独立实现，不临时扩成新协议。

现有fetch的`urlopen(timeout=30)`是阻塞操作timeout，不是整次请求绝对deadline。仅按单次30秒、一个索引+12条详情+每条3秒间隔，名义预算已达426秒，超过函数配置300秒；加重试更高。因此不采用原任务12条默认值，不直接套用CLI的重试循环。

新stage工作预算拟为240秒，留60秒给状态/缓存及误差。测试须覆盖请求读取、重试、backoff及解析的累计时钟；如采用每请求20秒总时限，1个索引和3个详情各最多2次尝试、重试等待3秒、详情间隔3秒的名义网络预算是181秒，仍须验证额外开销和剩余预算。**现有fetch尚未提供这个绝对时限，181秒不是当前实现保证。** 不能仅用socket timeout或请求前剩余时间判断冒充总deadline；慢响应持续分块、重定向、DNS/TLS和预算后仍运行的请求均需说明边界。如果需修改现有fetch传输层，先报告限定文件/行为范围，不能顺便改解析、架构或线上配置。未解决前只可报告离线正确性，不称可发布。

非医疗是已确认non-fact，不是核验失败。允许在discovery层直接过滤；进入detail时只对已有明确unsupported代码作非事实处理。有效索引中真实零候选或全部为已确认non-fact，在范围完整且无未解决错误时可以完成stage；不能照搬“selected>0且verified=0即失败”的CLI门禁。HTTP/结构变化、标题日期不一致、未知parse error均阻断，不伪装成无项目。每条记录保留官方证据、真实核验时钟及原始日期精度；不推进未重新核验记录的observed_at。

## 5. 发布、覆盖与AI

- 保留完整published baseline、所有公开ID在原始canonical中的包含关系、天津/区域metadata与排序、事件隔离和重复ID冲突门禁；按既有组合流程构建快照。
- 三个新增stage必需且成功，既有必需stage/fallback条件也满足，才允许进入durable接受和cache读回。失败不能靠“partial”绕过stage门禁。
- 本实施批仍保持`collection_coverage.complete=false`，保留上次真实`last_complete_as_of`或null；不因接线或一次mock成功解除AI partial/版本绑定。长期暂停覆盖与完整恢复未核验前不升级全覆盖。
- 当前未实现候选继续把三源标为history-only。未来实现只能依据**同一实际周期的成功实扫及范围证据**，从`history_only_source_ids`移除相应来源；没有执行、超预算、只加载历史均不能移除。保持partial；每源扫描时钟/计数放stage result，`updated_source_ids`只记录canonical实际改变，并映射正确intent source ID。该覆盖语义必须有专门测试，不能把“无新内容”当“未扫描”，也不能把扫描当覆盖缺口已修复。
- canonical→durable→reader cache没有跨存储事务，保持既有accepted/revision/hash和失败读恢复门禁。较新durable已接受而cache失败时不自动回写旧数据库；不用模型调用验收。

## 6. 最小实现文件范围

| 文件 | 必要改动 |
| --- | --- |
| `web/collector_runtime.py` | 三stage、必需阶段/分派、既有三key的严格读写、薄adapter调用、预算/范围检查、source结果及coverage映射；保留既有发布组合和fence |
| `web/pipeline/tests/test_twice_daily_source_parity.py`（新增） | 三源接入、身份、non-fact、预算/覆盖、source提交与发布门禁 |
| `web/pipeline/tests/test_twice_daily_search.py` | 新阶段计数/coverage相关契约；保留历史保护及早午隔离断言，不能删断言换绿灯 |
| `web/pipeline/tests/test_collector_native_reliability.py`及必要stage-dispatch合约 | 仅更新新增stage会直接影响的完整性/分派期望 |
| `web/vercel.json` | 下一实现隔离分支的`deploymentEnabled=false`；两个Cron、函数/Queue配置不变 |
| `docs/project/current-state.md`、checkpoint及本任务 | 精确HEAD、验证结果、未完成线上门禁 |

Queue及collector-status已从runtime导入`STAGE_ORDER`，新增stage原则上不需要修改它们；status结果只暴露聚合计数/错误码/时钟，不泄露详情、凭据。先通过真实分派测试验证，不能仅查常量。`collector_namespace.py`无需新增一套别名，三key已经是v2。旧incremental policies/scheduler/bootstrap不改；不改UI、ranking、AI、私有数据、法律窗口、其他地区、域名、Secrets、数据库或安全设置。超出表中范围时说明具体必要性，不暗中混入其他PR。

## 7. 必须验证的行为（本轮未运行）

1. **调度与分派**：两条每日Cron、三stage分别收到同周期Queue消息、全部既有stage顺序/条件不弱化；旧tick/旧schedule payload无副作用；同周期重投不重复提交或发布。
2. **早午交错**：新增source的canonical写入、状态完成、publish及终点重投均不能覆盖/清除午间新周期；保留现有确定性交错反例。实际旧部署与在途排除仍是线上门禁，不把mock fence称CAS。
3. **真实parser调用**：测试证明调用既有discovery/detail/stable ID，而非复制输出；research与intent key/source前缀、天津market和生命周期不能混用。
4. **正反样本**：9/28康复设备调研的历史窗口内回放，断言MARKET_RESEARCH、2026-10-09 16:00 +08:00；9/30数据安全non-fact、妇产非医疗样本排除，不误伤源健康；intent无虚构报名deadline。
5. **时间与样本来源**：截至10/17，9/28样本已过期；分别测试历史开放窗口与当前过期状态，不能把它推成当前ACTION_NOW。当前tests/data搜索未找到030199113/030199248的已保存原始HTML，不声称已读取。最小构造HTML必须标为mock契约测试；若缺可追溯官方fixture，真实来源回归验收保持待补，不把任务文档里的标题/时间冒充原文。
6. **长暂停/完整性**：三个key分别缺失、schema/source/market错、baseline缺失/只有Top-N/坏count、公开ID遗漏、缺口超lookback、索引覆盖未知均阻断；不能调用bootstrap、生成空数组或覆盖旧durable/cache。来源全部non-fact/可信零候选与网络失败分别测试。
7. **预算**：最多3条不截断冒充完整；第4条存在即阻断；慢读、重试、backoff、解析累计、预算耗尽均不提交半source；请求未实际完成不能通过只改mock时钟声称已修复总deadline。
8. **保留与发布**：四条既有intent/全部公开历史ID保留、无主动TTL；一个新source失败整个公开版本不前进；25stage/区域fallback门禁、market/rank、durable接受后cache失败及AI版本绑定保持。
9. **覆盖语义**：历史加载仍history-only；完整新实扫的准确源级状态、无新内容与canonical变化分开；complete仍false，last_complete不伪造；不发模型请求。

下一实现只运行上述新增/受影响聚焦测试和六个既有adapter相关测试，先修实际失败；完成产品代码变更后才跑一次必要完整Verify，不循环重跑879旧矩阵。新产品HEAD需自己的验证及独立审查，不能继承文档HEAD或祖先绿灯。若历史基线失败，区分已有失败与新增回归，不修无关项。

## 8. 发布阻断与下一步

[现有发布前/回退方案](../ops/release-preflight-20261003.md)仍有效：实际套餐/Cron enabled、唯一串行consumer身份与cap、按部署的ready/in-flight/delayed/expiry、完整canonical/baseline/暂停缺口、有效停止方式仍未补齐。本轮没有新控制面读回。10月7日审计记录旧生产15分钟链仍运行，只是当时观测，不证明10月17日状态；PR75关闭链的代码更不代表生产已经停止。

别名切换/回滚不停止旧部署投递。若停止只能删除部署，须另获“仅本次新失败部署”的明确条件性授权；不得删除现有旧生产/回退目标，不清队列，不搬运/receive/ACK旧消息。没有安全隔离/静默证据或恢复依据，继续禁止合并/发布；不得用新三源代码绕过这些门禁。

**下一步**：从最终文档HEAD开隔离实现分支，先做三源parser/key/失败保护的离线最小切片及其回归，再完成真实请求预算和完整发布契约；遇到本文明确的传输/fixture/范围缺口报告准确证据。推荐 **GPT-6.1-sol · xhigh**（预算和周期/缓存边界），纯adapter映射与已明确断言的实现可用high。之后才进入独立审查和线上只读门禁；本设计不批准发布。
