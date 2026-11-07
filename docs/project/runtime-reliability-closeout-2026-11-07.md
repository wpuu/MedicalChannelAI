# F1/F2/F3 工程收口审查与唯一下一优先项

2026-11-07（Asia/Shanghai）。本轮只做离线静态审查及文档。起点 **05cbcabcff0f75a2225d6319430b46cbed806848**，既有代码 **a352b7a8dcb0dba3112c3dde9fd91db14b9603d4**，现有分支 `codex/p0-reliability-contracts`；开始时工作树干净，无相关在途代理工作。前台开始05:47:21Z，截止06:07:21Z。读取最新用户指令、持续推进约定、状态/checkpoint/next-task、publish合同及实现、增量/区域实现、共享入口审查与行动雷达验收合同。早期回补/dry-run提示仅作历史上下文，不再执行其已完成任务。

**结论：F3区域CLI完整性门禁关闭；F1/F2按实际子项收口，不宣称全项目完成。唯一下一优先项为R1：离线复现并最小修复区域runtime详情阶段的同次调用明确拒绝止损。** 当前轮未授权代码修改，以下两文件方案待用户下一轮明确选择；不在本轮执行。

## 版本与证据边界

- 1145项Python、10项冻结模板、3项原CLI是代码a352b7a的**已有离线通过结果**，本轮不重跑。读取对应JSON验收结果、校验源文件哈希与提交祖先关系；不读取regression.log内容，不执行历史verify/reproduce脚本、测试或应用。
- 源码引用均绑定本轮起点05cbcab及实际文件SHA256，详见[逐行引用](validation/runtime-reliability-closeout-2026-11-07/source-references.json)。既有每轮证据及数据/fixture保持字节不变；[静态证据清单](validation/runtime-reliability-closeout-2026-11-07/manifest.json)记录检查数量及结果。
- 本地mock、正确权威ACK、bucket完成分别只能证明对应本地路径、该次响应所承认的提交、桶状态。不能替代当前来源完整采集、当前部署SHA、真实持久化、公开读回或客户交付验收。
- checkpoint中的82cc43f部署来源、795ef5e应用候选等是**历史记录，非本轮当前云端观察**。本轮没有查询或更新云端状态；不能由本地HEAD推出部署版本。
- `apply_allowed=false`、`migration_usable=false`；SDK、跨进程硬取消/严格时限、原子提交/自动回滚、崩溃后持久回执强保证维持 **CLOSED NO-GO**，不是下一轮候选。

## 实际覆盖矩阵

| 范围 | 实现及历史版本证据 | 本轮静态依据 | 完成边界与状态 |
| --- | --- | --- | --- |
| CLI F3完整性 | 7b29933；已有复核关闭 | [失败退出](../../web/pipeline/scripts/sync_regional_ccgp.py#L384)、[完整性](../../web/pipeline/scripts/sync_regional_ccgp.py#L738)、[report别名保护](../../web/pipeline/scripts/sync_regional_ccgp.py#L402) | 已实现且本地验证：部分发现/fallback/详情失败不提交新records，合法完整空可成功；不等于历史回补迁移完成 |
| CLI F1明确拒绝止损 | 01ccaa9，最终测试b97bc09 | [同调用host表](../../web/pipeline/scripts/sync_regional_ccgp.py#L420)、[warmup回调](../../web/pipeline/scripts/sync_regional_ccgp.py#L442)、[详情准入](../../web/pipeline/scripts/sync_regional_ccgp.py#L630)、[marker](../../web/pipeline/scripts/sync_regional_ccgp.py#L648)、[拒绝登记](../../web/pipeline/scripts/sync_regional_ccgp.py#L662) | 已实现且本地验证：按实际host区分搜索/详情；普通超时不推断全host拒绝。不是共享进程冷却/Retry-After调度 |
| CLI F2协作式预算 | 58e7e6b，bba3716参数化保持默认 | [CliBudget](../../web/pipeline/scripts/sync_regional_ccgp.py#L68)、[输出准备/提交](../../web/pipeline/scripts/sync_regional_ccgp.py#L323)、[CLI原点](../../web/pipeline/scripts/sync_regional_ccgp.py#L390) | 已实现且本地验证：逻辑900/工作840/收尾60；提交前拒绝、提交后迟到/未知分开；无硬取消/跨文件事务保证 |
| 区域CI离线门禁 | 6d4eb1b；当时8模块94项本地通过 | [paths](../../.github/workflows/regional-medical-refresh.yml#L29)、[set-e](../../.github/workflows/regional-medical-refresh.yml#L59)、[CLI模块](../../.github/workflows/regional-medical-refresh.yml#L63) | 已接线；当时94不是当前模块组合重跑结果，远端runner与workflow执行未核实 |
| 区域Queue主/备用F2 | bba3716，后续a352b7a回归保留 | [Queue入口原点](../../web/collector_queue.py#L429)、[限定注入](../../web/collector_queue.py#L494)、[传递至详情](../../web/collector_runtime.py#L1542) | 已实现且本地验证：270/210/60含预检，CLI默认不变；超期新事实拒绝；不保证密集fallback完整且按时。发现拒绝止损已有，详情止损仍有R1 |
| tjzyefy增量F2/pending | b584bcf，a352b7a发布桥接 | [仅tjzyefy注入](../../web/collector_queue.py#L441)、[runner拒绝扩大](../../web/collector_incremental_runtime.py#L529)、[单URL保存截止](../../web/collector_incremental_runtime.py#L716)、[publish桥接](../../web/collector_incremental_runtime.py#L515) | 已实现且本地验证：270/180/URL30/最终化60；12详情数量预算、carryover、兄弟staging与未解决pending保持。数量deferred/bucket完成且snapshot_refreshed=false不等于来源完整成功 |
| deep及tjzyefy publish调用者 | a352b7a；24新增，累计1145/10/3 | [发布210截止](../../web/collector_runtime.py#L1614)、[PUT调用者](../../web/collector_runtime.py#L1642)、[严格ACK](../../web/collector_runtime.py#L1705)、[先验ACK后判迟到](../../web/collector_runtime.py#L1718)、[publish](../../web/collector_runtime.py#L1729) | 已实现且本地验证：deep270/210/60；增量沿原parent，不误用180代替发布210；NOT_ATTEMPTED/UNKNOWN/CONFIRMED及Node/Python副本分别保存。确认不因迟到降级成未提交，无崩溃持久回执保证 |
| 其他deep阶段及增量源 | 原路径保留，未实施本轮预算 | [stage白名单](../../web/collector_runtime.py#L1902)、[原调用](../../web/collector_runtime.py#L1922)、[其余增量原调用](../../web/collector_queue.py#L446) | 未覆盖F2：25个deep stage中11个接预算、14个未接；8个增量源中仅tjzyefy接预算。未覆盖不等于实际超时，见R2 |
| 共享host冷却/Retry-After | 验收合同后续要求，非已有实现 | [合同](action-radar-acceptance-contract.md)、[CLI本地host表](../../web/pipeline/scripts/sync_regional_ccgp.py#L420)、[详情HTTP封装](../../web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1448) | 设计要求/尚未实现：现有外部host状态不跨进程共享；当前调用链未消费Retry-After。属于R1更广边界，本次唯一后续先做小范围止损，不另开共享协调器 |
| 真实Preview与产品验收 | 旧版本运行证据仅历史记录 | [当前合同](action-radar-acceptance-contract.md)、[本轮版本/状态](checkpoint.json) | 运行事实未核实，见R3；不由mock/ACK/桶终态推出当前覆盖、持久化或客户交付 |

## 调用链及不能放宽的边界

- 区域CLI：main → 已有session/warmup → scoped/fallback discovery → 同host详情准入/核验 → 完整性判断 → 同文件系统候选准备 → replace → report。Queue区域：入口原点/epoch/owner预检 → 主/备用run_stage → 请求/解析预算 → 原canonical提交 → 状态/健康 → Queue重试或推进；CLI本地host表不会自动传播到这条路径。
- tjzyefy增量：Queue同原点/lease → discovery/12详情及carryover → [staging先保存](../../web/collector_incremental_runtime.py#L720) → [本URL barrier](../../web/collector_incremental_runtime.py#L728) → ledger/finally → canonical/健康 → publish → bucket/lease。保留[未解决pending检查](../../web/collector_runtime.py#L318)和已核验兄弟staging；不把未执行URL标VERIFIED或清屏障。
- deep发布及增量桥接 → canonical完整性/pending → 构造/JSON/digest → LATEST写入/读回 → 权威PUT → ACK版本与整数pool数量 → Node/Python副本 → 原stage/bucket/heartbeat/tick/owner/lease回执。[Node先确认持久写再返回ACK](../../web/api/public-snapshot.js#L127)、[缓存副本失败RETRY_REQUIRED](../../web/api/public-snapshot.js#L138)、[ACK字段](../../web/api/public-snapshot.js#L144)和[微秒版本helper](../../web/api/_snapshotRevision.js#L3)均保持原实现；只读源码不证明真实持久化。来源canonical提交、权威ACK确认、副本待重试、尾部结果未知是不同状态；snapshot_refreshed=false不是零写证明。

## 仅三项剩余缺口

### R1 · P1 · 区域runtime详情明确拒绝后仍可继续同host请求（唯一下一优先项）

**证据及影响：** 区域发现阶段在[scoped异常](../../web/collector_runtime.py#L1448)及[fallback异常](../../web/collector_runtime.py#L1477)已对明确限流/401/403/429中断，不能重复报修。详情[遍历selected](../../web/collector_runtime.py#L1536)后，[通用异常分支](../../web/collector_runtime.py#L1558)只追加failure_row，没有host封禁或break/raise；下一详情仍可进入请求。HTTP helper[保留HTTP原因链](../../web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1448)，现有[access_block_reason](../../web/pipeline/scripts/sync_regional_ccgp.py#L309)可复用。另[session创建](../../web/collector_runtime.py#L1378)未传warmup拒绝回调，未把已知www入口拒绝反馈给详情准入；详情路径未检测既有RATE_LIMIT_MARKERS。

本轮用AST/源码证明可达继续路径，**未执行行为复现，不声称当前线上被拒绝**。影响是拒绝后的额外请求和预算消耗；[原fail-closed](../../web/collector_runtime.py#L1565)仍阻止部分新canonical提交，此处不是数据完整性缺陷重新出现。已有[发现止损测试](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L679)覆盖搜索，已有[详情部分失败测试](../../web/pipeline/tests/test_runtime_source_parity_behavior.py#L637)覆盖不写canonical，二者不证明详情同host后续请求为0。

**唯一最小后续：** 下一轮先离线复现，再只改 `web/collector_runtime.py`、`web/pipeline/tests/test_runtime_source_parity_behavior.py`。复用既有分类器、marker和session回调，维护单次stage调用内按实际URL hostname区分的拒绝集合；同host后续业务请求为0，未执行部分仍为不完整。www.ccgp.gov.cn、search.ccgp.gov.cn、裸ccgp.gov.cn不得按父域合并。预算、failed/重试/降级、诊断边界、canonical/pending/健康协议不改。普通网络超时/503/解析失败不得误判为host全面拒绝。其他实际host可继续独立核验，但不完整stage仍不提交。

**行为验收：** 主/备用、至少两个同host详情、HTTP401/403/429及包装cause、限流HTML、warmup拒绝反馈；搜索与详情host分离、另一合法host及普通超时反例；完整成功/合法空保持；旧canonical/pending/成功时钟与F2超期/最终失败边界保持。明确拒绝后同host后续请求0；必要回归及10/3按实际代码变化运行。既有桩/冻结样本/假时钟/临时目录，阻断网络和真实SDK。无法在两文件内安全完成则NO-GO，不扩大。

**所需授权：** 当前轮无代码授权；完整下一轮提示词明确仅两文件本地离线复现/修复。无需云端访问、新权限或新环境。跨进程共享冷却、Retry-After调度、其他stage不在该授权内。

### R2 · P2 · F2覆盖仍局部，医院/事件及其余增量缺乏阶段时间预算

**证据及影响：** [STAGE_ORDER](../../web/collector_runtime.py#L183)与[Queue预算分支](../../web/collector_queue.py#L494)显示14个deep阶段没有新预算，包括ccgp、event1–6和七个医院/早期信号阶段；[其他stage主动清预算](../../web/collector_runtime.py#L1903)。[增量支持集](../../web/collector_incremental_runtime.py#L25)共8源，tjzyefy外的tjmugh/tjnothop/teda/tjfch/tjfch_test/tjzyefy_intent/tjzxfc不接parent预算。事件[调用入口](../../web/collector_runtime.py#L780)及[scan_events](../../web/pipeline/scripts/sync_ccgp_query.py#L85)仍有逐查询/详情sleep和固定请求上限，没有累计阶段monotonic接口。

这是**覆盖与设计缺口**，不是已复现耗时故障，也不是Queue重试/租约/独立来源功能缺失。名义HTTP timeout或maxDuration不能替代安全提交预算。事件又与同源事实的提交保护关联，不能机械照搬区域210秒值。

**最小后续及验收：** R1关闭后才选一个明确stage/来源，先做一次文档合同，静态列请求/睡眠/保存链与安全截止、数量deferred/失败/恢复，再决定是否有授权的最小代码方案；不全项目铺预算。测试须涵盖返回/解析后超期、保留pending/兄弟staging/成功时钟、事件事实配对与其他来源继续执行。当前没有足以确定唯一代码文件清单或预算数字的来源级合同，不能冒称已可实施。需另行限定单源文档授权；后续代码/云端仍须分别明确授权。

### R3 · P1发布放行阻断 · 新代码真实部署、来源和端到端交付未核实

**证据及影响：** a352b7a的[本地验收](publish-budget-implementation-2026-11-07.md)及冻结artifact不包含本版真实Preview运行；当前授权禁止查询云端/业务/缓存/数据库。本轮不能判断现有部署、来源恢复、实际持久化及延迟。权威ACK正确也不能证明该来源扫描完整、公开读已一致、bucket/lease结果已知或崩溃后回执可恢复；更不能推出相关性、资格或商业效果。

**最小后续及验收：** R1及必要离线回归关闭后，另行请求一次范围明确的现有d周期Preview放行包：部署/生产者/消费者来源SHA和epoch绑定，受控来源采集范围、canonical/pending/健康时钟，权威快照版本及数量/内容读回、Node/Python副本与stage/bucket/lease分别验收，迟到/未知按真实证据报告。真实调用前须给具体项目/部署/请求上限、退出条件、可读数据/副作用清单与恢复边界；不足则NO-GO。当前不提出新的SDK路径，不绕过既有CLOSED NO-GO。

**所需授权：** 额外云端只读核实、构建/部署、真实业务触发、读回各自需明确授权；本轮均无。本条是放行门槛，不作为当前代码缺陷；不自动推送、部署、改计划/凭据/权限或访问Production。

## 决策及本轮验证

优先R1，因为它是最新源码可定位的F1剩余路径，有已验证分类器可复用，只需两个现有文件离线复现与修复；先消除拒绝后的请求再考虑真实来源验收。R2尚需单源合同，直接铺预算有破坏提交保护风险；R3需要额外外部授权与真实运行证据。本轮不因审查结论扩权或开始下一轮代码。

已完成：版本绑定覆盖矩阵、三项缺口和唯一后续两文件方案；标准库静态核对源码行号/哈希、AST调用分支、祖先关系、历史JSON门禁、既有数据和冻结证据字节、仅文档差异。未导入执行应用/SDK/测试；未重跑未变1145/10/3，未新增模拟层。检查数量和完成时间以[验收摘要](validation/runtime-reliability-closeout-2026-11-07/validation-summary.json)及completion.json为准。

未完成：R1行为复现/修复、R2其余阶段合同与预算、共享冷却/Retry-After、R3真实Preview及客户交付；关闭的强保证分支不再推进。没有网络、实际环境值/日志/凭据、云端或运行数据访问，没有部署/推送/workflow触发/计划权限变更。

[下一轮完整任务](next-task.md)基于本轮报告与最新HEAD，不沿用早期dry-run或SDK任务。当前界面无法生成该按钮，不能用问答弹窗或链接代替；提供可复制完整提示词。推荐 **GPT-6.1 Sol xhigh（超高）**，实际运行设置**未核实**。
