# PR75 发布前只读核验与审批范围

结论：**门禁未通过，当前不可发布。** 本轮仅做只读核验及文档保存，没有合并、部署、Preview、启停调度/消费者、收取或确认消息、清队列、采集、模型调用或付费升级。没有重跑879项测试或定向矩阵。

## 提交与证据

- 用户冻结提交及开始时实际PR HEAD均为 `8b4b749bf057ed3f5a9b830fdef84ecc04bb1bd2`，PR75为draft/open/unmerged；main为 `62299590dd3898e040ccc9db5fda1298d4509d51`。
- 沿用 [Verify37117043888](https://github.com/wpuu/MedicalChannelAI/actions/runs/37117043888) 的成功结果和此前879项记录；本轮读回该HEAD、成功构建/排名步骤和live探测skipped，未触发新运行。当前CLI/连接读取历史日志未返回测试正文，不声称本轮重新提取879项日志。已有独立审查的5份产品/测试文件哈希与冻结提交相符。
- 本轮保存文档会产生新的PR HEAD；最终审批须绑定PR75最终读回的精确HEAD，不沿用8b4b749或更早提交的审批。文档提交的所有非文档blob须与8b4b749相同；879项CI属于该产品祖先。本轮文档提交使用`[skip ci]`遵守不重跑的要求：仅有paths-ignore并不能保证包含既有代码差异的PR synchronize不触发验证。没有修改workflow或分支保护；不为文档再次运行历史矩阵。如果仓库规则仍要求新HEAD的检查，此要求须由现有规则下解决，不能把祖先检查说成新HEAD检查。
- 新线上证据在 [online-readback.json](evidence/release-preflight-20261003/online-readback.json)，官方条款及响应hash在同目录。此前911/441重建、98项定向及终点竞态审查均为已有证据，本轮未重跑。

## 逐项门禁

| 门禁 | 本轮实际读取 | 结果与未满足条件 |
| --- | --- | --- |
| GitHub合并规则 | rulesets列表读取为空，main分支保护接口403 `Resource not accessible by integration` | **未通过**：没有读取branch protection的权限；空rulesets不证明旧保护不存在。不得绕过检查、修改保护或将祖先CI当新HEADCI |
| 精确候选及既有验证 | 初始PR8b4b749；成功CI元数据、独立审查冻结哈希 | 产品证据通过；最终文档HEAD必须重新读回，审批不能使用旧HEAD |
| 实际生产 | Vercel生产别名：READY `dpl_DW5wrMzvVXS7TLmbqUL1vSfcyuh1`，精确commit62299590…；当天部署列表为空 | 已确认仍旧生产，无候选部署 |
| 套餐 | 团队及项目列表成功，但未返回billing plan；项目详情工具报INVALID_ARGUMENT | **未通过**：实际Hobby/其他套餐未知；不是账号权限被拒绝的证据 |
| 实际Cron配置及启停 | 支持的连接没有返回Cron控制面。生产源码声明单条`20 0 * * *`无period，候选源码声明两个每日任务 | **未通过**：源码不证明线上任务列表或enabled状态；须读回实际列表及项目级暂停机制 |
| 消费者及串行配置 | 候选源码topic=`medicalchannelai-refresh-v2`、group=`api/collector-queue.py`、region预期iad1，cap1、lease/retry360、函数300 | **未通过**：真实部署分区、consumer身份、有效cap/lease、是否存在其他订阅者均未知；源码不是生效证据 |
| 在途、积压和延迟重试 | collector状态active/null、stages空、旧增量ledger/staging计数0；24h collector日志查询无记录 | **未通过**：缓存计数不是Queue清单；无法证明无投递、已暂停或队列为空，必须按deployment/group读真实ready/in-flight/delayed/expiry |
| 数据可读及历史公开事实 | 13:02Z status为DATABASE、STALE/degraded，版本`2026-10-02T14:19:15.713282+08:00`；13:03Z公开pool441，ID唯一、rank连续、6地区字段及排序与生产发布文件一致，4条intent均在 | 只读事实核对通过；不是新采集、完整运行态恢复或候选上线证明 |
| canonical完整恢复 | Git生产live备份911唯一记录；公开441的ID均在历史备份中。collector-status不暴露canonical/watch/events/history/baseline内容 | **未通过**：真实缓存库存、完整性、后续未发布状态及暂停期间新增缺口未知；不能用public投影反造canonical或自动回填旧备份 |
| 早午互不破坏 | 8b4b749终点hook不再get/delete ACTIVE；同周期terminal重投不执行stage/清staging，已有确定性交错及冻结hash可复用 | 已有代码证据通过，未做线上交错。RuntimeCache无CAS；恢复仍须排除旧部署/旧在途，不能手工删ACTIVE/META来强行重开周期 |
| 失败停止与回退 | 官方Queues说明别名/rollback不停止旧部署消费，停止投递方式为删除该部署 | **未通过**：未确认非破坏性停投递入口或旧分区完全静默；必须明确停投递机制及本次失败部署的删除授权边界 |

现有Vercel连接的团队/项目列表/部署/日志/公开GET正常。`get_project(projectId,teamId)`的公开schema与后端要求`idOrName`冲突，本轮只调用一次并记录具体错误；未重复相同调用，也未把错误泛化为连接失效。现有工具没有billing/Cron/Queue inventory/RuntimeCache inventory入口。环境观测revision11为current，未绑定secret、runtime变量或outbound identity；没有Vercel CLI或现成CLI认证文件。本轮不索要令牌、不登录新账户、不生成保护绕过链接、不调用Queue receive/poll来“查看消息”。剩余需要**现有账户控制面受支持的只读字段或人工读回**，尚不能判断Vercel账号本身是否缺权限。GitHub唯一实际权限拒绝是main branch-protection读取403；其他PR/CI/rulesets读取正常，需要同一已有账号人工核对保护要求，不修改保护设置。

## 套餐与两个每日任务

[当前官方条款](https://vercel.com/docs/cron-jobs/usage-and-pricing)实际返回：各套餐每项目最多100条；Hobby每条每天一次、小时级精度（表中±59min，例子1:00任务可能1:00–1:59触发）。技能的旧“最多2条”数字不使用。此条款不是实际套餐证明。

候选只配置以下两个独立每日任务，不使用一天两次的合并表达式、不升级：

| 路径 | UTC表达式 | 北京时间名义时段 |
| --- | --- | --- |
| `/api/collector-run?period=morning` | `20 0 * * *` | 08:20，小时级抖动 |
| `/api/collector-run?period=noon` | `20 4 * * *` | 12:20，小时级抖动 |

入口接受08:00–10:00、12:00–14:00（右端不含），这只是容差，不是准时保证；cycle ID按中国日期/period，首次真实触发时钟冻结。第一受控周期只能在实际匹配窗口开始。错过窗口等待下一个真实窗口，不伪造时间、不补跑旧周期。

## Queue隔离：纠正旧发布清单的假设

[官方概念页](https://vercel.com/docs/queues/concepts)明确：push消息默认按deployment ID分区，发到发布它的部署。新部署不会自动接管旧分区。切换production别名或rollback也不会停止旧部署投递和重试。官方“Stopping deliveries to a deployment”给出的停止方法是**删除该部署**；不是只改别名。证据见 [queue-stop-delivery.json](evidence/release-preflight-20261003/queue-stop-delivery.json)。

因此本轮不能把“旧积压只由新handler确认”或“暂停consumer”当作已证实可执行的控制面能力。候选旧payload门禁仍保留，适用于实际到达候选handler的消息；不强制搬运旧分区、不新建poll消费者、不receive/ack历史消息、不清队列。候选发送retention为24h，但官方平台支持更长retention；旧分区最长到期时间必须来自真实消息/控制面，不能猜24h后必然清空。

发布前的隔离必须满足其一，并记录实际控制面证据：

1. 已有账户存在经过核验的非破坏性停投递机制，能覆盖所有旧部署/组和在途重试，且不会在deploy/rollback时失效；目前没有证据证明此能力。
2. 停止所有实际生产入口后，旧分区的ready、in-flight、delayed均为0，最晚到期/最后投递已核对，在函数最大时限＋缓冲后复读仍静默。注册旧consumer本身不等于被禁用；只能据实际静默证据允许保留它作为回退目标，不允许再触发旧代码。

若上述均不成立，**不合并/发布**。不得为满足方案删除当前旧生产/回退部署，或把自然retention到期称为人工清队列。删除已有部署、强制迁移/补采都不在本次拟审批范围。

## canonical恢复门禁

在停止旧写入、确认在途结束后，由已有只读库存入口逐项核对：

- v2的ccgp、tjmugh、tjnothop、teda、tjfch记录；BJ/HE/LN/JL/HL区域分片；ccgp notice events及watch；尚未完成的ledger/staging/barrier状态，不能把空status当作它们不存在。
- 三个独立历史key：`medicalchannelai:collector-tjzxfc-records:v2`、`medicalchannelai:collector-tjzyefy-records:v2`、`medicalchannelai:collector-tjzyefy-intent-records:v2`。分别记录真实来源、count、ID集合、record/schema校验、hash和observed_at；不塞入别的来源分片。此前备份对应0、4、4只是历史计数，不能冒充当前运行态。
- `medicalchannelai:verified-snapshot:published:v2`完整baseline与实际durable版本、pool count/内容hash一致；latest reader cache及META/ACTIVE时钟与当前生命周期相符。没有完整baseline或canonical时继续阻断。公开GET的DATABASE源不能证明该RuntimeCache key已存在。
- 核对暂停区间及来源lookback/候选上限是否覆盖缺口。911条Git历史只是备份候选，不证明暂停期间不存在新增、所有缓存状态可恢复或最后未发布事实均已保存。没有完整可验证备份时，不自动用Git/seed/bundled或公开卡片恢复；需要另行明确的恢复/重建决策，不含在一次发布审批中。

真实恢复若另行获准，历史key按stable published约定无主动TTL保存，并读回相同hash；不推进事实observed_at。逐出后阻断，不能手造空数组续跑。候选投影/天津事件隔离已通过既有独立审查，本轮未重复构建；实际公开地区/rank本轮一致，但新生产仍须再验收。

三个旧来源仅保留历史；候选必须保持`collection_coverage.complete=false`及旧真实`last_complete_as_of`/null、history-only列表，页面明确部分覆盖。现有刷新stage仍全部成功才可发布；AI partial与版本绑定门禁保持，验收不请求模型。

## 一次发布与受控验收顺序（仅供未来明确批准）

1. **先补齐门禁，后执行批准。** 再读最终PR HEAD/main/生产提交；产品blob若变化，原方案和祖先CI不能自动沿用，停止并重新审查。记录旧READY回退目标、配置、durable版本/内容hash及所有分区快照。确认已有账户可执行Cron停用、隔离和明确的失败停投递操作。当前所有缺项补齐前，批准也不代表可以直接发布。
2. 按批准范围停止实际Cron及其他生产入口，GitHub两条refresh保持disabled；按上节既有机制隔离所有旧消费者/分区，等待并读回in-flight结束。禁止手工删ACTIVE/META、解锁旧周期或清staging。读回canonical完整性；如需要未获准的数据修复，停止。
3. 只合并一次最终精确PR HEAD到main，合并提交使用明确的发布标题/正文，不继承文档`[skip ci]`标记；读取并满足实际分支保护，不绕过检查。使用已有Git集成产生**一次Production部署**；不Preview、不另行手动deploy、不因超时重复推送。立即记录实际merge SHA、部署ID、artifact及alias归属。若Git集成未触发，停止，不自行另建部署。项目级Cron停用及旧分区隔离须在新部署后再读回；不能假设deploy会保持未知暂停状态。
4. 核对新生产commit、旧数据仍可读、partial范围、Today/Pool/Detail的版本与地区/rank，AI仅检查cache-only/版本绑定。读取实际新分区consumer身份 `(deploymentId,region,topic,group)`、cap1、lease/retry360、maxDuration300及其他组列表。新分区在首次真实启动前应无意外消息；注册trigger可能自动启用投递，不能假设可以事后再暂停。任何异常先执行下节失败流程。
5. 仅让该新分区的串行consumer处理**一个匹配时段的当前真实周期**。只调用现有入口一次，202/入队回执不是验收通过；已有同周期Queue重投继续受幂等/上限约束，不另造重复测试消息。检查全部配置stage、真实时钟、partial及AI限制、canonical保留、durable接受/revision/hash、cache readback及页面版本一致。结束marker保留，不以删lease强行启动下一周期。
6. 第一个周期验收通过后，按同次明确批准范围启用上述**两条各每天一次Cron**，GitHubfallback继续关闭。观察另一个时段自然触发的独立cycle，不额外手动补采。其stage、partial、版本及旧早间消息无副作用也验收通过，才可称“每天两次配置来源搜索已恢复”；不称三个历史来源已恢复新监控。小时级窗口结束仍未自然触发或任一门禁失败，进入停止/回退，不伪造成功。

## 失败停止、数据保护和回退

| 失败位置 | 操作顺序与证据 |
| --- | --- |
| 合并前套餐、Cron、旧分区或canonical不明确 | 不合并、不部署、不触发周期；保存缺项清单。若未来批准后已停止入口，保持停止，不以恢复旧15分钟链绕过 |
| 部署未READY或commit/consumer/config不符 | 停两条Cron及入口，禁止首周期；记录实际新部署ID、错误和队列分区。未创建可回退新部署时不删除旧目标；使用下述实际停投递路径 |
| 周期失败、旧写入/并发、数据缺失或durable/cache分歧 | 先停Cron/入口；使用已验证停投递机制，读回在途结束。记录cycle、durable_accepted、最后真实版本/revision/hash及Queue计数，保留canonical/队列/较新durable事实，不回写旧snapshot或自动重新执行周期 |
| 停投递机制只能删除本次失败部署 | 这是需要明确批准的**条件性删除**：只允许删除此次发布创建的失败候选deployment ID。先保护并恢复已冻结旧READY的生产alias（旧分区必须已隔离/静默），再删除失败新部署以停止它的后续push投递；等待至少实际函数上限＋缓冲且读回in-flight为0。在这两步之间不启动旧或新采集。删除不是“回退即停队列”；既有投递可能仍需等待结束 |
| 回退后验收 | 旧目标为 `dpl_DW5wrMzvVXS7TLmbqUL1vSfcyuh1`、commit `62299590dd3898e040ccc9db5fda1298d4509d51`，执行前重新核实。仅回退代码/alias，不重建旧版本数据库。读回实际alias/commit、最后已接受事实仍可读、partial/时钟及AI绑定；所有Cron、旧15分钟链继续停用，失败新部署不再投递、旧分区保持静默。停止机制/兼容性/读恢复任何项不可验证，则回退不能标成功 |

不得删除旧回退目标、清队列或删除较新已接受事实。如果用户不批准条件性删除、且没有已核验的其他停投递能力，**失败停止门禁仍不成立，不能批准为可执行发布**；需要另行确认受支持的停止方案。本轮没有新增产品代码或开关，也没有新发现产品缺陷的复现测试；这里修正的是被官方部署分区/停投递语义否定的操作假设。

## 集中审批对象

本轮交付为**BLOCKED的发布前核验**。需要的人工输入集中为：main既有分支保护/文档HEAD检查要求、实际plan、Cron列表/enabled/暂停持久性；每个deployment/group的真实identity/cap/ready/in-flight/delayed/expiry和有效停投递方式；完整canonical/cache库存及恢复依据；确认是否接受“仅在本次失败时删除本次新部署”作为停止方式。均使用已有账户，不要求新token。

全部门禁补齐后，集中批准绑定PR75**最终精确HEAD**的一次合并、一次Production发布、一个当前周期受控验收、通过后启用两条每日Cron并观察另一时段自然周期，以及上述失败停止/代码alias回退和条件性删除本次失败部署。审批不包含付费升级、Preview、删除现有/旧生产部署、清队列、跨部署消费/补跑历史、未另行授权canonical重建或模型调用。此前HEAD批准不自动适用。
