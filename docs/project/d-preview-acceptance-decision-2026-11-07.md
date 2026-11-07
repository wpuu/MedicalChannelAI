# 现有d Preview一次性验收变更与授权决策包

2026-11-07（Asia/Shanghai）。本轮仅离线文档，起点 **b710804**，应用 **3f88ff7211200e314dcb6bafa894ec127c1b29bf**。工作树`/workspace/MedicalChannelAI-p0`、分支codex/p0-reliability-contracts，初始干净，仅根代理，无相关在途工作；另一工作树3216fd9未改。前台09:58:46Z开始、10:18:46Z截止。读取最新用户指令、协议/状态/checkpoint/next-task、R1/主链收口、发现/事件/publish实现、历史元数据与Preview读回及行动雷达合同。

**唯一结论：当前真实验收NO-GO，暂停本分支。** 既有源码可以形成下述单份执行顺序、验收判据和授权清单，但目前缺少可信运行身份、准确部署依赖、可控CCGP执行范围、canonical证据通道及副作用授权，不能安全放行。不是再次否定R1本地修复；不重开SDK/强保证，不另造模拟器或分拆多轮补证。当前所有云端查询、部署、触发、业务读回与运行清理的批准数量均为 **0**。

## 1. 固定候选与历史起点

| 项目 | 本包绑定值及证据边界 |
| --- | --- |
| 唯一目标 | 项目prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM；团队team_jEy8Ex9vRDBdXj1cQPKF8sRd是历史查询上下文；仅既有Preview，不访问其他项目、Production或旧c |
| 期望隔离 | mcai-p0-20261106-d；数据库/受限角色历史名mcai_p0_epoch_20261106d。只是期望，实际注入/权限/后端地域未核实 |
| 拟部署来源 | 冻结本地来源 **b710804**，应用代码 **3f88ff7**，两者web树完全相同。最终未来若选择其他SHA须重新绑定证据，不把当时最新HEAD自动作为已批准来源 |
| 既有本地通过 | 3f88ff7的1213项Python、10模板、3原CLI，新增11项测试。R1已离线关闭；当前不重跑。原CLI隔离空事件watch，不是完整线上事件验收 |
| 历史部署起点 | dpl_8Jhc4imHEd6ndBUoth5xBVTrAyL1 / medicalchannelai-b5vc26me3-rerisse7-1717s-projects.vercel.app，历史声明来源82cc43f06c774969eab0fe44f0afc012f37cadac、应用795ef5e。2026-11-06元数据target原值null；不改写为本轮已确认Preview或项目最新部署 |
| 历史数据 | 当时d公开16条、页面ALL15条及微秒版本/哈希是旧时点证据；当前数量、窗口、canonical、owner/消息均未核实，不以旧分母验收新数据 |
| 依赖 | [pyproject](../../web/pyproject.toml#L6)仅未锁版本的vercel；仓库没有Python锁。实际SDK/完整依赖闭包未核实，不能把冻结公开候选或本地mock版本当实际部署版本。JS源码声明@vercel/functions 3.9.5及既有package-lock，不代表真实部署bundle已验证 |

[release-source.json](validation/d-preview-acceptance-decision-2026-11-07/release-source.json)保存完整SHA/web树、23个web/workflow差异路径及本地门禁JSON哈希。相对历史82cc43f包括runtime/Queue/增量、query/区域/tjzyefy脚本、离线工具与测试、区域CI两项接线；不是只有R1四文件的新部署。API/Node/SQL/版本/锁/vercel.json及原始data/public快照没有该段源码差异，不能因此推断运行配置一致。

## 2. 入口与副作用：不能按HTTP方法猜只读

| 入口/动作 | 最新源码行为 | 本包规则 |
| --- | --- | --- |
| 构建 | [package build](../../web/package.json#L11)经[prebuild](../../web/scripts/run-prebuild.mjs#L9)先运行refresh_bundled_snapshot，再Python/JS门禁、tsc和vite；[refresh写入](../../web/pipeline/scripts/refresh_bundled_snapshot.py#L149)public/data/today-actions.public.json | 当前不执行。未来构建须在现有工作区的临时构建输出范围隔离这些生成写，保留来源/输入/输出哈希；不在原始数据/公开快照上执行后假称纯读取。不绕过prebuild或删门禁。准确安全载体与依赖现存情况未核实，故未放行 |
| GET /api/collector-run | [认证](../../web/api/collector-run.py#L46)需既有CRON_SECRET；[deep启动](../../web/api/collector-run.py#L195)先ensure_intraday_chain、owner激活，再发ccgp消息；不带mode时为deep | 是写入/调度触发，绝不可列入只读冒烟或随重试重复GET。无source=ccgp单源/stop-after-event6接口，不猜造stage/deadline/limit参数 |
| GET /api/collector-run?mode=incremental&source=tjzyefy | [显式单源](../../web/api/collector-run.py#L243)一次入队，写尝试/租约等，runner可提交canonical及publish | 是可选择的单源增量，但不执行CCGP事件/R1，不能拿它代替本包CCGP真实验收。当前同样不批准触发；不使用auto选择扩大来源 |
| POST /api/collector-queue | [订阅配置](../../web/api/collector-queue.py#L14)、accept_and_handle和lease300；原生签名/版本绑定未核实 | 仅平台原生交付，不手工伪造签名或直接POST业务payload，不把它当维护执行通道 |
| GET /api/pipeline-health | [cache_roundtrip](../../web/api/pipeline-health.py#L38)写探针缓存并读回，[GET](../../web/api/pipeline-health.py#L158)总会调用；还GET自身status | 从本包只读集合排除，未来也为0；不能用健康探针写入当canonical/持久化证据 |
| GET /api/status、/api/public-snapshot及?fresh= | [共同loader](../../web/api/_verifiedSnapshot.js#L384)可经数据库读取；[schema ensure](../../web/api/_publicIntelligenceDb.js#L297)在schema版本不符时可能DDL/元数据写；无可用持久快照时[Runtime Cache fallback](../../web/api/_verifiedSnapshot.js#L325)可能seed写入 | GET也不保证零写。须先有可信d数据库/既有schema与读取模式证据及副作用授权；本轮不探测。不把?fresh=当“禁止所有写”或跳过fallback的参数 |
| GET /api/collector-status | [状态与计数读取](../../web/api/collector-status.py#L253)，Python RuntimeCache实例；load_status源码只读 | 不主动采集，但实例化真实SDK、后端/依赖及可能遥测未核实；摘要没有全canonical内容、完整pending身份或可靠持久回执，不替代canonical导出，也不能承诺全链路严格get-only |
| PUT/POST /api/public-snapshot | [先持久确认](../../web/api/public-snapshot.js#L128)后副本/ACK；schema初始化、SQL写入、Node副本均可能发生 | 仅在业务执行许可内由既有publisher发送；本包不额外手工重放PUT，不用新时间戳绕过冲突 |
| 浏览器/AI/预热、workflow | 页面可能有自动请求；现有workflow含采集、发布、Production URL及预热 | 全部排除，当前与本候选的最小观察计划均不触发；不把Git push或workflow当Preview部署手段 |

Python/Node仅在实际Preview epoch正确存在时套[命名空间](../../web/collector_epoch.py#L9)及[数据库名断言](../../web/api/_previewEpoch.js#L31)，缺配置不会自动证明d身份；实际值本轮未读取。运行namespace v2与epoch前缀由既有wrapper应用一次，不手拼物理键或借旧c/Production读回。发布URL由[部署host固定](../../web/collector_runtime.py#L1773)，仍需证明实际host属于这一个获准Preview。

## 3. 唯一执行顺序、数量与时间边界（当前不执行）

这是一个带阻断门禁的候选包，不是数轮试探：任何前置缺证据即整包NO-GO，不进入下一步，不因部分通过就放行。当前批准数量一律0；下列数字只用于未来完整授权的审查。

| 顺序 | 未来单包政策上限 | 必须先满足/退出条件 |
| --- | --- | --- |
| P1 身份/部署元数据 | 至多4次现有工具非敏感只读查询，零自动重试；白名单仅目标project/team/deployment/branch/SHA/状态、非敏感绑定证明 | 只查同项目既有d Preview；无法字段投影或provider返回null/缺归属时如实未核实，不读env值、凭据、原始日志，不自动申请权限。此项当前未授权；也不能单独解决后面的控制/数据证据缺口 |
| P2 构建与版本封存 | 1次完整构建，0依赖/配置修改，0workflow；仅临时生成输出 | 需准确现存依赖/可复用安全执行载体及原输入字节保护；预构建会写快照，不能在当前docs授权下执行。1213/10/3可复用，完整JS/类型/构建对新应用尚无本版证据；构建自身标准门禁如会重复测试须如实计数，不跳过。当前不安装任何SDK |
| P3 部署 | 最多1个新有效Preview部署，固定项目/分支和来源b710804；0Production、0变量/权限/保护/计划变更 | 部署/构建/既有消费者影响要明确授权；旧消息不会因新部署自动换代码，SDK与依赖bundle身份要独立确认。失败/返回未知不盲重试创建 |
| P4 基线/服务读回 | 顶层业务GET总政策上限10次，零HTTP重试；无browser/AI/health探针 | 建议旧部署基线status/public/collector-status各1；新部署触发前status/fresh-public/collector-status各1；终态一次status/fresh-public/普通public/collector-status，共10。不满足读副作用及数据授权时数量为0；自动重定向/内部DB/cache调用不在这10次的外层HTTP计数内，不能据此声称真实上游总请求有界 |
| P5 受控触发 | 目标为CCGP一个配置范围，手工触发≤1次；当前因无受控范围实现而批准0 | 既有deep入口实际25阶段，不能限定为ccgp+event1–6或仅一次publish；还会ensure日内链。不能把1个GET说成1个消息/单源。见下方数量核对；没有足够可执行上限，直接NO-GO，不改计划/Queue/代码来凑通过 |
| P6 终态与读回 | 只用P4预留的终态批次；手工补触发0、手工PUT0 | 最多20分钟前台绝对窗口，超时停止客户端观察、保存最后已知/未知，不把它说成取消在途调用。正常退避/完整周期可能超过窗口，不能承诺全周期完成；不自动后台轮询、重置任务或清owner |
| P7 清理 | 运行数据删除/回滚/清pending/改lease/取消消息全部0 | 保留旧canonical、未解决pending、兄弟staging和真实未知；仅对本任务明确授权且新创建的临时访问材料可按原授权撤销/删除。本轮没有创建。身份不明不得清他人owner或旧队列；需要额外变更才可安全收尾则NO-GO，不擅自扩权 |

**真实执行范围的阻断算术：** 当前plan有5关键词×2类型，ccgp每次最多10个搜索helper和12个详情helper顶层调用；这是逻辑调用数，不含重定向/SDK内部流量，不保证150秒完整完成。event每片最多5项目×2类型=10搜索helper，但每查询详情候选无显式数量上限，因此不能给整个CCGP链一个已证实的固定HTTP总上限。watch30/六片只约束项目数，不能替代详情请求上限。

[STAGE_ORDER](../../web/collector_runtime.py#L186)为25阶段，[_enqueue_stage](../../web/collector_queue.py#L168)自动推进；[tick链](../../web/collector_queue.py#L338)可继续日内调度，配置最多31个tick时隙/日，不是只由本次手工调用生成或保证恰好31条消息。原生配置maxDeliveries/max_attempts=3、retry150秒、函数/lease300秒仅是当前源码配置，实际消息绑定未核实，不是“25×3即全项目请求上限”的证明。

对照项只有既有tjzyefy单源增量：每次1次index、最多12次详情、每URL最多2次，名义26个顶层HTTP attempt槽；若实际使用3次投递则名义78槽，另有最多每投递1个publisher PUT。它仍不包含重定向、SDK流量、并发旧writer/独立tick，也不能验收CCGP R1，**本包不转用该路径冒充完成**。单消息3×300+2×150=1200秒只是配置名义串行值，尚未包含触发/读回，不能以20分钟前台承诺完整重试周期或硬取消。

## 4. 一次性验收判据

| 对象 | 必须成立的证据 | 失败/不足如何报告 |
| --- | --- | --- |
| 配置范围完整性/合法空 | 固定判断时钟、plan哈希、查询/候选/核验/失败/延后数量与官方证据；全部所选范围完成且无未解决失败才可完整成功 | 超量、跳过、拒绝、超期或deferred均不冒充完整；合法空不回填旧卡片；只有零新增事件可如实为0，不拿watch非空当新事件非空 |
| canonical与pending | 前后可信全内容/哈希/版本、同源pending URL解除依据、其他源/兄弟staging保护；d身份绑定 | collector-status计数/公开池不能替代canonical。当前真实导出通道未核实；不调用已关闭SDK导出分支，不用仓库seed或公开快照冒充迁移 |
| 发现双键与event配对 | PREPARED_LOCAL_READBACK只认两键按时匹配；event1–5只staging，event6前序/pending齐全后单键配对；观察写前/未知/迟到与目标 | 两键不是跨键事务，调用返回不等于真实持久化；未知时保留mutation_possible，不称零写/回滚/已恢复；未执行URL不得VERIFIED或清屏障 |
| 成功时钟/独立来源 | CCGP七阶段完整成功才刷新成功时钟；完整空可成功；其他来源保留旧已验证值且降级可见 | ccgp准备成功、bucket COMPLETED且snapshot_refreshed=false、整体新快照时间均不证明整源成功或其他源恢复 |
| 权威公开版本 | 严格ACK的200/ok/durable_committed、精确snapshot_as_of及整数pool数量；同版本完整规范化内容哈希与获准权威只读查询/服务fresh读回一致 | 当前Node ACK不含数据库hash，不能从本地digest推导实际DB hash；须有独立已授权证据。版本按六位微秒，不能截毫秒或换时钟绕冲突。旧精确版本只算旧证据 |
| Node/Python副本 | 两份分别UPDATED/READY或真实SKIPPED/UNKNOWN，公开来源模式及fresh/普通读取一致性 | 任一未确认保守RETRY_REQUIRED；合法迟到权威ACK仍CONFIRMED，不抹成未提交；客户端退出不证明无在途写 |
| stage/bucket/lease/owner | 分别有版本身份及尾部结果，原重试/独立调度/释放顺序保持，foreign消息无业务副作用 | 已确认公开提交与尾部未知可同时成立；不要求或声称崩溃持久回执、硬时限、跨键原子性；不得伪造错误身份真实投递来“测试” |
| 用户/商业效果 | 另有相关性、资格、动作及客户使用证据 | 本包不验收模型/客户交付/Production，不从工程成功推出商业可用 |

## 5. 完整阻断与go/no-go表

| 门槛 | 已有依据 | 当前结论/必须新增的完整证据 |
| --- | --- | --- |
| G0 本地R1/预算/完整性 | 版本3f88ff7、1213/10/3及冻结artifact | **GO仅限已有离线子项**；没有真实放行含义 |
| G1 当前目标/权限/隔离 | 历史项目过滤命中；target=null且非独立归属证据，实际epoch/db/受限角色/发布host和最小权限未核实 | **NO-GO**。需可信非秘密身份/授权证明，明确project/team/Preview/d/db/region及publisher/trigger分权；不读秘密去猜绑定 |
| G2 精确部署代码/依赖/构建 | 本地拟来源/web树已固定；Python依赖未锁，当前SDK/bundle及新完整构建未核实 | **NO-GO**。需本候选准确bundle/SHA/完整依赖与安全构建结果；不能把公开SDK候选当实际版本或修改锁后冒称原版本 |
| G3 消息生产者/消费者与旧writer | 现有d历史、epoch代码及原生配置；当前active owners/队列/消费者实际版本及与旧消息并发未知 | **NO-GO**。需当前同scope消息/owner/consumer版本与安全执行窗口证据，不读旧c/Production或自动删旧队列；只切部署不能证明停旧消息 |
| G4 可控CCGP触发/成本 | 既有deep会启动25阶段与日内链，事件详情无固定候选请求cap；单源增量不覆盖CCGP | **NO-GO静态执行范围缺口**，不是线上故障复现。须有与原完整性兼容、已获授权且可信的单包执行范围/真实请求边界；本轮不改调度/配置/协议或新建载体，不用超时future冒充停止 |
| G5 canonical/状态/权威读回 | status为摘要，真实canonical/owner版本及可靠只读通道未核实；既有SDK只读导出强合同已CLOSED NO-GO | **NO-GO**。需独立可信、明确授权且满足本次证据边界的既有渠道；不通过重复SDK审计/新模拟/新路由绕过，也不增加不属于本次的硬取消保证 |
| G6 读回及构建隐式写 | GET可DDL/探针/seed，prebuild写bundled snapshot；实际读取模式/schema/权限未知 | **NO-GO**。要么有可信证据排除相应分支，要么用户明确接受列出的副作用并有最小权限；“GET只读”或旧schema已好不充当当前证据。禁止的运行变更不能自动升权 |
| G7 授权与退出/恢复 | 本轮仅docs；无云端查询/部署/业务触发/数据读回/清理的新授权 | **NO-GO**。完整批准对象/次数/数据与副作用/停止及恢复边界必须逐项明确；20分钟退出只结束观察，无法据此保证全部消息终止。未知结果不自动补触发或回滚 |

所有门槛缺口一次列清。本轮只建议**暂停**，不建议先查一点元数据、先部署、先跑单源再说，也不安排未来自动轮询/模拟轮次。新外部证据若仍不能解决G4/G5等静态/渠道阻断，保持NO-GO；不是重新写一份相同报告的理由。

## 6. 权限分项及本轮验证

未来若重新考虑这同一包，非敏感元数据、离线构建输出、单次Preview部署、真实采集/Queue/权威发布、canonical/SQL/API读回、任务临时访问材料清理必须分别获得明确授权。授权不能只是“继续”旧docs任务，也不能相互替代；不自动更改计划、变量、凭据、角色、项目保护或已有数据。没有拟议应用/依赖/路由改动被本包批准；为解除阻断必须变更它们时先结束本分支，不能私自实施。

本轮静态核对 **101处源码引用、23个历史来源差异路径、629份既有data/fixture/artifact及455份web/workflow文件不变**，引用绑定b710804与文件SHA256。只执行标准库源码/AST/JSON/算术/哈希及git检查；没有应用/SDK/测试/模型/构建执行，没有联网或读取实际环境值、凭据、运行日志，未访问真实云端/业务/缓存/数据库/函数/Queue。未部署、推送、触发workflow、新建环境/路由或写运行数据/历史原文/公开快照。1213/10/3保持历史版本事实。

[证据清单](validation/d-preview-acceptance-decision-2026-11-07/manifest.json)、[静态摘要](validation/d-preview-acceptance-decision-2026-11-07/validation-summary.json)。apply_allowed=false、migration_usable=false；SDK及强保证分支不重开。本分支以NO-GO暂停，只有新增完整外部证据及逐项明确授权时才做一次性复核；否则不重复施工或生成补证轮次。下一轮条件任务见[next-task](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh，实际设置未核实。
