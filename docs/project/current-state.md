# MedicalChannelAI current state

Updated: 2026-11-07（Asia/Shanghai）

## 当前Queue区域runtime F2协作式预算（离线实现）

- 起点83b434c，代码bba3716，只修改授权6文件。复用CliBudget参数化，CLI默认900/840/60保持；Queue注册区域主/备用阶段采用270/210/60，monotonic原点包括预检，不从payload读deadline，不重置。不接入增量/事件/publish。[报告](runtime-f2-implementation-2026-11-07.md)、[证据](validation/runtime-f2-implementation-2026-11-07/manifest.json)。
- 写前耗尽走CollectorStageBlocked retryable=True与原FAILED/503路径，旧canonical、成功时钟和其他源pending/ledger保留。首个失败重试、普通第二次失败立即降级推进及终局重复消息不抓取保持。已提交后迟到只加overrun观察，不当写前失败；写入/状态/健康异常明确结果未知，不声称零写入/回滚或新健康终态。
- 新增19项行为测试，最终1098项Python及10/3通过；21组区域状态/哈希与6组Queue断言已冻结，460份起点data/fixture/旧证据字节不变。没有改Queue配置、lease、健康/pending协议、API、共享HTTP helper、workflow、锁或计划。
- 无外网/真实SDK/云端/运行数据访问、部署/推送/触发、新环境/路由/变量/权限变化，apply_allowed/migration_usable=false，SDK仍CLOSED NO-GO。仅协作式区域子项，硬取消/严格时限/原子提交/真实持久化、密集fallback按时完整及其余runtime阶段预算仍未完成/不放行。
- [下一轮](next-task.md)仅文档制定增量tjzyefy时间预算与pending恢复合同，不改代码或重跑未变测试。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

## 上轮runtime F2阶段预算合同（历史方案，区域协作式子项已实现）

- 起点62c039e，完成[唯一最小方案](runtime-f2-stage-budget-contract-2026-11-07.md)：先只给Queue已注册区域主/备用阶段接协作式270秒逻辑总预算/210秒工作/60秒收尾，保留现有重试、owner、pending和健康合同。复用既有CliBudget参数化，CLI默认900/840/60不变；不同时接入增量/事件/publish。[证据](validation/runtime-f2-contract-2026-11-07/manifest.json)。
- 已追踪Queue入口/身份检查/heartbeat→run_stage准入→区域请求/解析→canonical→状态/健康→重试/推进；普通业务attempt上限2不同于provider投递3，消息lease300不同于owner活性900和owner缓存TTL2天。最后失败立即降级/推进、区域限流止损与partial fail-closed已有实现，未重复报修。
- 增量既有先staging后VERIFIED ledger、逐URL屏障解除、finally ledger保存及pending分支保持；bootstrap无discovered时返回DISCOVERY_REQUIRED，不执行官方请求，不能误报双发现。区域预算不等于增量已获时间预算，旧pending/成功时钟和独立来源必须保留。
- 静态区域primary满详情固定等待81秒/名义参数串行1311秒；密集fallback201/3231秒，只剩210−201=9秒工作余量给41请求与解析，不保证完整完成。默认密集fallback、全runtime部署、硬取消、原子owner/时间/提交均NO-GO；缓存/SDK真实写入完成与时延未核实，SDK仍CLOSED NO-GO。
- 本轮冻结145处源码引用，450份起点data/fixture/历史证据SHA256不变，应用/测试/workflow/锁/计划未改；94及1079/10/3仅历史结果，未重跑，未导入执行应用/SDK或新增模拟层。无网络/云端/运行数据访问、部署/推送/触发或环境/权限变化；apply_allowed/migration_usable=false。
- [下一轮](next-task.md)需明确离线代码授权后，只改列明6个既有文件实现区域协作式子项；若需要改Queue/租约/健康协议才能满足就明确NO-GO，不扩大。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。

## 上轮区域CI CLI离线门禁（仅本地配置与模块组合验证）

- 起点8b3eba8，workflow提交6d4eb1b：只在既有paths新增CLI测试文件、在既有unittest清单新增tests.test_regional_cli_completeness，恰好两行。原7个模块/set-e、schedule/分支/concurrency/权限/timeout/采集/发布/预热/凭据引用全部保留。[报告](regional-ci-cli-gate-2026-11-07.md)、[证据](validation/regional-ci-cli-gate-2026-11-07/manifest.json)。
- 现有PyYAML解析与字节对照通过，修改后的8模块组合本地94项通过、0失败/错误/跳过；socket连接/DNS与真实SDK导入阻断。应用及测试源码仍58e7e6b未变；本轮未重跑1079/10/3，也未执行/触发workflow，不能冒称远端runner或来源验收通过。
- 441份起点data/fixture/旧证据SHA256不变，无外网/云端/运行数据访问、部署/推送、新环境/路由/计划/变量/权限变更，apply_allowed/migration_usable=false，SDK仍CLOSED NO-GO。
- 未完成runtime F2、硬取消/严格墙钟保证、共享冷却/Retry-After与真实来源/Preview验收。[下一轮](next-task.md)仅文档制定runtime阶段预算合同，不先改代码或执行函数；推荐GPT-6.1 Sol xhigh（超高），实际设置未核实。当前界面无法生成该按钮。

## 上轮F2区域CLI协作式预算（离线实现，非硬时限）

- 起点2826b30，代码58e7e6b，按已冻结合同实现900秒逻辑总预算/840秒工作/60秒收尾。monotonic/sleep可注入，timeout按原30/90/30上限与剩余预算减1取小；warmup预算异常不吞，超期返回/解析不进入可提交新事实，后续业务请求/sleep全局停止。[报告](regional-cli-f2-implementation-2026-11-07.md)、[证据](validation/regional-cli-f2-implementation-2026-11-07/manifest.json)。
- CLI内同文件系统临时候选准备＋提交前deadline/完整性检查，提交前失败exit2并保留原records。replace结果未知exit3/records_written=null；提交后迟到exit3/COMMITTED，report失败exit3/COMMITTED_REPORTING_INCOMPLETE并有stderr回执，不声称零写入/自动回滚。F1/F3与合法完整空保持；不是跨文件事务或原子时间CAS。
- 新增20项行为测试，CLI共48项，最终1079项Python、模板10/10、原CLI3/3通过；429份起点data/fixture/旧证据字节不变。首轮既有源码形态检查不兼容已用真实绑定timeout调用修正后重跑全套，未改获授权范围外的测试。
- 仅改sync_regional_ccgp.py与test_regional_cli_completeness.py及文档/新增artifact；runtime/shared helper/分类器/workflow/锁/计划未改。无外网/真实SDK/云端/运行数据访问、部署/推送、新环境/路由/变量/权限变更，apply_allowed/migration_usable=false，SDK保持CLOSED NO-GO。
- 未完成：900秒硬退出、同步HTTP/磁盘取消、默认五地区/25分钟job按时完成保证、runtime F2和共享冷却/Retry-After。假时钟不证明真实时延或来源恢复。下一轮建议明确授权后仅补[区域CI](next-task.md)的CLI离线测试模块与路径清单，不改定时/权限/业务步骤；本轮未改workflow。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮F2区域CLI预算合同（历史方案，现已离线实现协作式子项）

- 起点98f5503，49处最新源码引用已冻结。[唯一方案](regional-cli-f2-budget-contract-2026-11-07.md)：CLI专用协作式monotonic总900秒、工作840秒、收尾60秒；保留warmup30/search90/detail30上限，timeout按剩余预算缩小，原4秒间隔不足则拒绝而不缩短后发请求。只建议下一轮修改CLI脚本及既有CLI测试两个文件，不改共享helper/runtime/workflow/计划。
- 静态默认负载：无fallback满详情101请求/401秒固定等待；满fallback131请求/561秒固定等待；完整空61请求/241秒等待。名义timeout参数相加为6431/9291/5671秒，不是实测或墙钟上界。900秒内默认完整成功及25分钟job完成均无证据；不能把workflow1500、后置预热480、runtime300或本轮前台1200当成CLI已获预算。
- 待实现合同明确warmup预算异常不能被吞、所有请求/sleep/解析前后复查，预算未完成沿F3整批exit2/保留records。CLI内临时文件准备＋提交前检查防止超期序列化先截断原文件，但时钟检查/replace非原子，多文件不具事务；提交后迟到/报告失败必须明示已提交或未知，不冒称零写入/自动回滚。硬900秒退出/同步I/O强制取消NO-GO，runtime和共享冷却仍未覆盖。
- 本轮只做静态算术、引用/完整性检查，420份起点data/fixture/旧证据字节不变，web/.github未变；1059/10/3仍为b97bc09已有通过结果，未重跑，也未执行CLI/应用/SDK或新模拟器。[证据](validation/regional-cli-f2-contract-2026-11-07/manifest.json)。无联网/云端/运行数据访问、部署/推送、环境/计划/权限变更；apply_allowed/migration_usable=false，SDK仍CLOSED NO-GO。
- [下一轮完整任务](next-task.md)需明确本地代码授权后才实现这一个协作式子项，不把文档完成称为F2完成。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮F1区域CLI单次调用止损（离线完成，完整F1未完成）

- 起点1352739；实现01ccaa9、最终测试b97bc09。真实CLI离线复现scoped/fallback/详情明确拒绝后仍继续请求；现复用collector_diagnostics固定分类，按显式host停止该次调用的后续请求。搜索与详情/裸域分开，普通超时/503不误停，下一次调用不继承停止状态。[报告](regional-cli-f1-stop-2026-11-07.md)、[证据](validation/regional-cli-f1-stop-2026-11-07/manifest.json)。
- CLI专属warmup反馈覆盖www主页限流/拒绝，阻止同host后续详情；runtime默认不注入，入口及分类器源码未改。report明确blocked_hosts、scoped/详情跳过数和fallback阻断，不把未执行范围说成完整。F3失败非零退出/records字节保留及路径别名保护保持通过。
- 新增13项行为测试，CLI共28项；最终1059项Python、冻结10/10、原CLI3/3通过。408份起点数据/fixture/历史证据SHA256不变；原F3冻结验证器通过。最终增加默认双公告类型覆盖后重跑全套，不用中间1058结果冒充最终版本。
- 仅现有分支离线代码/测试/文档/新增artifact，无外网/真实SDK/云端/运行数据访问、部署/推送、环境/路由/锁/计划/变量/权限变更。apply_allowed/migration_usable=false，SDK保持CLOSED NO-GO。只有单次CLI显式目标host止损，不是跨进程共享冷却、全路径F1、重定向逐跳拦截或F2墙钟预算。
- [下一轮](next-task.md)仅文档确定区域CLI的F2预算合同和唯一最小实现边界，明确数字、失败收尾、timeout局限和验收标准，不先改代码或计划。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮F3区域CLI完整性门禁（已修复并复核关闭）

- 最新重复F3请求已核对：实际起点5f47041（不是旧2911c92），代码/测试/工作流与7b29933验收版本一致，既有验证器通过、395份输入哈希不变，按“已修则给证据关闭”处理；本轮未重跑1046/10/3、未改应用、未推进F1/F2。[本轮复核证据](validation/regional-cli-f3-recheck-2026-11-07.json)。
- 起点2911c92，代码7b29933；真实argparse/main＋冻结官方详情复现4种失败仍exit0/改写records，现统一失败exit2且不写records，完整成功/合法空/fallback成功仍exit0。report与输入/records的同路径、符号链接、硬链接冲突在客户端建立前拒绝。[报告](regional-cli-f3-fix-2026-11-07.md)、[证据](validation/regional-cli-f3-2026-11-07/manifest.json)。
- 15项新增行为测试、全部1046项Python及冻结10/10、原CLI3/3通过；395份起点data/fixture/旧证据字节不变。F3测试阻断所有socket/真实opener，完整回归禁止外部网络/真实SDK导入，仅保留既有loopback重定向测试。
- 仅配置内有界扫描整批门禁，不是全历史召回、每市场独立提交/覆盖水位、文件系统事务或真实CAS。report候选计数不代表已写入，records_written=false明确失败批次未发布新事实。SDK工作流仍CLOSED NO-GO，apply_allowed/migration_usable=false。
- 无云端访问、部署/推送、计划/权限/变量/锁/环境变更或运行数据/原始历史数据/公开快照写入。F1限流后请求止损/共享冷却及F2墙钟预算仍未完成；不把旧403/健康状态当当前事实。下方旧审查及云端记录均保留其历史版本边界。
- [下一轮完整任务](next-task.md)为F1区域CLI单次调用明确限流止损子项，需该子项本地代码授权，不重开SDK或扩大到跨进程/F2。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮共享入口限流/重试预算离线审查（历史静态结论，F3已由上文关闭）

- 起点d9882a0，完成[调用链与缺口审查](shared-entry-budget-review-2026-11-07.md)：F1路径间限流止损/入口冷却不一致，F2剩余墙钟预算未传至请求/sleep，F3区域CLI存在部分失败仍写records/退出0的静态路径。全部没有本轮新行为/线上复现，不当作已确认线上故障。
- 建议先离线复现F3再最小修复；现有合同要求单源fail-closed，CLI与runtime不能混同。保守整批阻断可作为第一步，不冒称每市场独立提交/覆盖已完成。F1/F2分立后续，不借机重开SDK工作流。
- 已有runtime区域发现限流止损/部分失败拒绝、终局失败立即推进、依赖DEGRADED跳过及详情数量/pending保护均有实现和既有测试覆盖，本轮只读测试不重跑。GitHub同branch并发组已存在；不将它说成跨epoch/CI/Vercel入口全局协调。
- 计划/默认参数只支持静态耗时分析，不是延迟测量；不把历史7/14、8/14或旧403/限流当当前。未新增mock/测试引擎、未执行应用/SDK/测试、未联网或调用云端/业务/运行数据，没有代码/锁/工作流/计划/权限/部署/推送变化；apply_allowed/migration_usable=false。[证据](validation/shared-entry-budget-review-2026-11-07/manifest.json)。
- 起点387份data/fixture/旧证据字节不变；引用与源码hash已核对，1031/10/3保持历史门禁。[下一轮](next-task.md)需明确本地代码/测试修改授权后，仅复现/修复F3，不扩大云端权限。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮真实SDK接入一次性决策（历史NO-GO，工作流关闭）

- 2026-11-07按精确冻结源码完成[一次性决策包](ccgp-runtime-integration-decision-2026-11-07.md)：唯一推荐暂停当前真实接入。默认SDK、strict/遥测关闭/future、异步切换、私有客户端修改、内部端点直连及业务/Queue复用均不能在现有证据下同时满足原合同，不批准任何应用/依赖/路由/配置/权限变更。
- 公开候选vercel0.12.2/cache0.7.7不是可上线版本承诺，更不是部署实际版本。2秒/读110秒/总120秒、无fallback/额外POST、响应限额及可信d后端不放宽；供应商版本能力缺口与运行事实未核实分别标明。新增入口/更大maxDuration不能单独解决这些阻断。
- 文档列明准确文件处理（运行文件全部不改）、执行载体/身份/权限的未决门槛、供应商公开遥测开关的配置授权要求、未来一次性验收及重启条件。当前不请求新权限、不安排重复模拟/探测；只有实质新证据与对应授权才能重新打开分支。apply_allowed/migration_usable=false。
- 本轮复核SDK冻结验证器通过（6个wheel、5份官方源码、签名/324旧输入）；19处引用核对，起点380份data/fixture/旧证据字节不变，源码/测试/锁文件未改。1031/10/3仍为历史门禁，未重跑。[新证据](validation/ccgp-runtime-integration-decision-2026-11-07/manifest.json)。没有联网、SDK执行、云端/业务/运行数据访问、部署/推送或任何配置变更。
- 此SDK接入分支已关闭，项目整体继续。[下一轮](next-task.md)返回已登记共享官方入口限流/重试预算的离线审查，仅文档、最多3项有证据的建议，不依赖canonical导出，不把旧健康状态当当前。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮官方公开Python SDK静态审计（历史候选已冻结，直接接入NO-GO）

- 以官方文档、vercel/vercel-py仓库和PyPI冻结vercel0.12.2、vercel-cache0.7.7、telemetry0.8.2、httpx2 2.16.0等审计切片；5份关键wheel源码与官方仓库commit5b25d1d5f3c42a838e0af34164b84e027a1fdcab字节一致，完整URL/哈希见[审计报告](ccgp-python-sdk-audit-2026-11-06.md)和[证据](validation/ccgp-python-sdk-audit-2026-11-06/manifest.json)。公开候选不等于部署实际版本，完整依赖闭包未审。
- 已证实原生get无timeout参数、默认底层30秒、默认错误转None和内存fallback；strict不能保证全部context/remembered路径严格。缺少响应流上限、可能遥测POST，内存get可能删除过期项；不能用现有合成守卫宣称真实路径已满足2秒/零额外写。
- SDK默认32bit key hash/可选namespace须与写入器一致；58原文键白名单在SDK输入层，非最终后端hash。官方文档Hobby团队共享、Pro/Enterprise按项目，实际team计划未知；此前一概按项目隔离的概括不充分。官方2MB存储限制不同于本地4MB观察阈值。
- 真实后端身份、安装版本、d运行绑定、执行通道和硬取消仍未核实，直接接入及迁移NO-GO；apply_allowed/migration_usable=false。源码中的变量名不代表读取实际凭据或环境值。
- 本轮仅公开GET与文档/artifact，没有安装/导入/执行SDK、项目元数据/业务/缓存/数据库/模型访问、部署/推送或配置变化；应用、依赖锁、守卫、内核和测试未改，324份旧数据/fixture/证据字节不变。1031/10/3保持历史代码门禁，本轮未重跑。
- 下一轮按[next-task.md](next-task.md)只准备精确SDK证据驱动的一次性最小接入变更决策包，不再造模拟层；不支持就NO-GO结束此分支。已获公开静态读取授权保留，不重复申请。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮d关联Preview非敏感云端元数据核实（历史部分事实已核实，真实接入NO-GO）

- 起点1238596，指定team/project/分支/SHA/Preview/创建时间过滤命中dpl_8Jhc4imHEd6ndBUoth5xBVTrAyL1；北京时间22:09:25–26返回READY、声明来源82cc43f、分支codex/p0-reliability-contracts、wpuu/MedicalChannelAI，provider target原值null。只确认该指定记录，不声称项目最新部署或d运行绑定已核实。
- 本次受控批次4次云端只读：3次相同过滤摘要（前2次本地多层响应提取失败，不当空结果），1次同部署源目录查询返回not_found。目录没有证据后停止，不转用日志、凭据、CLI fallback或业务接口。保存的均为白名单非敏感字段。
- 指定team/project查询上下文一致，但记录未独立返回所有权ID，不能替代Runtime Cache认证。实际epoch/数据库绑定、已安装SDK版本、执行通道和超时/取消能力仍未核实；真实接入/迁移NO-GO，scope_provenance_verified、apply_allowed、migration_usable=false。
- 云端声明来源82cc43f的本地Git树没有605ebad守卫/9781921内核，Python依赖vercel未锁版本；实际部署bundle未读取，不能拿本地1031通过当已部署能力。[报告](ccgp-cloud-metadata-2026-11-06.md)、[证据](validation/ccgp-cloud-metadata-2026-11-06/manifest.json)。
- 仅文档/artifact变化，应用与测试未改；314份起点原始数据/fixture/旧证据字节不变。1031/10/3为历史代码门禁，本轮未重跑。缓存/数据库读写0，业务接口/函数/Queue/模型调用0；没有环境值/凭据/原始构建日志读取、部署/推送或任何配置变更。
- 下一步按[next-task.md](next-task.md)，获得明确公开来源访问授权后静态审计官方Python SDK精确候选版本/源码，不安装、不运行，不再增加模拟层，也不将公开候选冒称部署实际版本。已有d非敏感元数据授权保留，不重复申请。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮最小get-only接入守卫（历史离线阶段完成，真实接入仍NO-GO）

- 守卫代码605ebad99041a3057189a1315adae6cc2a773055，复用9781921内核，保留原封套及输入种类。仅接受SYNTHETIC_LOCAL_STUB及准确d范围声明；58物理键原样转发，固定双遍顺序、最多116次get、零重试。非法/双前缀/旧c/Production/跨范围在转发前拒绝，首次失败永久关闭。
- 注入monotonic计算读阶段110秒、总120秒、单次最多2秒及剩余读预算；调用返回和交付前复查时间，整份拒绝超期结果。24项假时钟测试覆盖各阶段、余量、次数、声明变化及失败后续读；不是实际强制取消或性能SLA，不能抢占卡死同步transport。
- 本轮全部1031项Python、冻结10/10、原CLI3/3通过，原只读内核冻结验证器也通过。正常/未初始化封套SHA与原冻结结果一致，305份旧数据/fixture/证据字节不变；原内核、解析器、生成器和模拟器未改。[报告](ccgp-readonly-guard-2026-11-06.md)、[证据](validation/ccgp-readonly-guard-2026-11-06/manifest.json)。
- 标记和scope只是本地测试对象声明，不认证真实后端；apply_allowed、migration_usable及scope_provenance_verified均false。真实SDK/后端身份/执行通道/取消及执行回执仍未核实；真实观察、迁移、CAS和真实回滚未完成。
- 没有云端访问/推送/部署、新环境、计划/变量/凭据/权限变化、采集/项目模型或运行数据写入。离线守卫阶段已结束，不再叠加模拟层；[下一轮](next-task.md)仅在取得明确新增授权后核实既有d云端非敏感元数据，当前“不访问云端”边界未扩大。
- 当前界面无法生成该按钮，提供完整下一轮授权提示词；推荐GPT-6.1 Sol高（high），实际设置未核实。仅说“继续”不扩大云端权限。

## 上轮最小真实只读接入审查（历史离线完成，真实接入NO-GO）

- 基于起点43a9007和内核9781921核查实际键、epoch包装、owner/时钟、committed优先级及pending/barrier分步写入，形成引用代码行号的[接入方案及go/no-go表](ccgp-readonly-integration-review-2026-11-06.md)。58键/116次get与冻结轨迹一致，297份原始数据/样本/既有证据字节不变。
- 发现并本地复现接入风险：隐藏_EpochCache的get-only facade会二次加前缀，并可能稳定返回未初始化；现有core接收物理键，必须原样转发未包装原生get。该反例不是当前内核线上缺陷，未改应用/内核代码或测试文件，也未另建审查引擎。
- 离线限定观察GO；真实只读接入NO-GO：可信后端绑定、既有执行通道、已核实SDK与取消/大小控制、真实执行回执尚缺。本地vercel SDK未安装，历史82cc部署不含内核；没有读取凭据或访问服务来补缺口。
- 拟定单次预算120秒、最多116 get、每次最多2秒、110秒后不新开get、零重试；只是方案，未实现/实测。双遍相等、owner lease、单个CCGP committed均非全局原子revision；迁移/纠错独立NO-GO，apply_allowed/migration_usable始终false。
- 本轮复核冻结验证器通过；原1007项Python及10/3为代码绑定历史日志，未重跑全套。没有云端访问/推送/部署、环境/计划/变量/凭据/权限变化、采集/项目模型或任何运行数据写入。[本轮证据](validation/ccgp-readonly-integration-review-2026-11-06/manifest.json)。
- 下一轮按[next-task.md](next-task.md)只补物理键/次数/deadline的最小本地接入守卫，复用内核，不再扩建dry-run或模拟器。真实接入仍待明确新增授权及可信身份/SDK/通道证据。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮d周期canonical只读观察内核（历史离线通过，真实导出未执行）

- 内核代码97819215530454da55e0d5052b7bfbcd7f9ff694，仅注入get-only本地桩，无HTTP/CLI或真实客户端；复用实际namespace/epoch/来源策略，以现有键函数校验。58键/116次get覆盖canonical、CCGP事件/committed/staging、健康时钟、owner/meta及增量pending/barrier/ledger/bucket。
- 缺标识、跨项目/Production/旧c/数据库或写能力接口在读取前拒绝；两遍任意哈希变化、读取失败、大小/数量/结构超限整份拒绝。None保留未初始化/不可用，显式空保留空，不读快照或仓库来回填。
- 新增23项行为测试，全部1007项Python、冻结10/10、原CLI3/3通过。重复本地观察完全一致，285份原始数据/fixture/旧证据字节不变，上一轮内存模拟验证器仍通过。测试桩使用两条冻结记录与明确合成的缓存/owner/时钟外壳，不代表运行数据。
- 双遍相等不排除ABA/跨键竞争，生产者没有统一原子revision/fence；未知字段路径与辅助语义明确未覆盖。read_plan_complete仅表示限定读取完成，coverage.complete、migration_usable、apply_allowed和atomic_snapshot_guaranteed始终false。真实导出、迁移、CAS、真实回滚未实施。
- 无云端访问/推送/部署、新环境、计划/变量/凭据/权限修改、采集/项目模型或数据库/缓存/历史数据/快照写入；原Preview历史绑定未重新验证，production_ready=false。[报告](ccgp-readonly-export-2026-11-06.md)、[证据](validation/ccgp-readonly-export-2026-11-06/manifest.json)。
- 下一轮按[next-task.md](next-task.md)离线审查最小真实只读接入方案、身份/一致性阻断项与单次验收预算，仍不连接云端，不另建重复引擎。当前界面无法生成该按钮，给完整可复制任务；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮整批校验与内存回滚模拟（历史离线通过，禁止真实应用）

- 薄层代码8f8b5cc50e77087197f05b70b7fb2fee3857b57d，复用既有生成器/请求锁/白名单/canonical校验；9f6生成器与change_id未改。先核完整清单、scope、原状态版本及所有候选，再建立内存副本；混合before/after、任一无效或并发变化整批拒绝。
- 新增18项行为测试，全部984项Python、冻结10/10及原CLI3/3通过。两条候选内存overlay后回滚，892条完整状态及哈希精确恢复，890条未选择记录不变；重复overlay/回滚均0修改。两次CLI报告字节一致，网络阻断下往返通过。
- 回执锁定批次、scope和完整before/after状态；新事实/事件/pending会阻断回滚并保留新数据。始终apply_allowed=false；Python对象检查不是真实CAS/事务/锁，不是canonical导出、迁移、实际应用或真实回滚。
- 没有云端访问/部署、新环境、计划/权限修改、采集/项目模型或原始数据/数据库/缓存写入；本轮不复核旧线上状态，production_ready=false。[报告](ccgp-memory-simulation-2026-11-06.md)、[证据](validation/ccgp-memory-simulation-2026-11-06/manifest.json)。
- 下一轮按[next-task.md](next-task.md)实现现有d命名空间的只读导出内核，仍仅离线桩，不新增HTTP路由或读取真实缓存。当前无真实底部提示词按钮接口，给完整可复制任务；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮产品纠错 dry-run（历史离线清单，禁止应用）

- 工具代码9f6ac310fee4b0c68e92a6233e23bdc03cfa9ce3，复用原audit入口增加锁定请求＋显式1–5条选择，补齐产品字段证据、before/after及原记录/原文/解析器/生成器哈希。候选为河北扫描仪4套、吉林血液透析机5台/套，均apply_allowed=false。
- 新增21项行为测试，全部966项Python、冻结模板10/10及原CLI3/3通过。两次CLI输出字节及变更ID一致，阻断网络后核心输出一致；请求、基线和全部原始fixture字节不变。身份/版本/范围冲突、别名项目、超量和覆盖输入均拒绝。
- 使用仓库892条冻结输入，不是云端canonical导出或迁移。没有新环境、云端访问/部署、计划/权限变化、采集、项目模型请求或数据库/缓存/历史原始数据写入。原Preview/Production仅保留历史绑定，本轮未重新查询；production_ready=false。
- [本轮报告](ccgp-product-dry-run-2026-11-06.md)、[证据](validation/ccgp-product-dry-run-2026-11-06/manifest.json)。下一轮按[next-task.md](next-task.md)复用清单增加整批前置校验、内存overlay与回滚模拟；真实导出/CAS/迁移/应用/回滚仍未实施。当前无真实底部提示词按钮接口，提供完整可复制任务；推荐GPT-6.1 Sol高（high），实际设置未核实。

## 上轮 CCGP 修复 Preview 部署（历史定向只读验收）

- 最新部署来源 `82cc43f06c774969eab0fe44f0afc012f37cadac`，应用代码 `795ef5efa30b61dd47352c4fb888b02488f16855`；[Preview](https://medicalchannelai-b5vc26me3-rerisse7-1717s-projects.vercel.app) `dpl_8Jhc4imHEd6ndBUoth5xBVTrAyL1` READY，构建56.306秒。复用现有d周期/数据库/受限角色，未新建环境、改变量或定时计划。
- API/status准确返回82cc/d/DATABASE；部署前后Neon、fresh/普通GET及浏览器完整数据SHA仍 `85a1768f1705a3f4bd403ec0b70f80292ac24948806546d4c9be1d690576fead`，SQL微秒时钟不变，16条公开facts及来源时钟均未写入。collector无active cycle/增量链、完成阶段0，未触发Queue或回补。
- 页面6项定向检查完成，ALL15/15与真实截止一致：tjzyefy_20261104_030202660今天16:00报名结束且无后续投标窗口，退出当前行动池；数据库仍16条。初次固定16/16脚本超时不是产品漏显，未改事实/应用凑数。目标10项产品可见，390px无横溢，无页面异常；合计3次自动cache_only被阻断，模型实际请求0。
- [本轮报告](ccgp-preview-readback-2026-11-06.md)、[冻结证据](validation/ccgp-preview-readback-2026-11-06/manifest.json)。上轮945/完整构建和冻结10/3仍按代码绑定保留；本轮不是新解析器原生采集、完整Queue、canonical迁移或来源恢复验收。Production/SSO于北京时间19:31只读确认未变，临时访问撤销、私有文件清理，production_ready=false。
- 下一轮读取[完整任务](next-task.md)并复用已有审查工具补齐最多5条dry-run变更清单。按[用户最新工作约定](working-protocol.md)，当前界面没有真正的底部提示词提交按钮接口，不再用问答弹窗冒充；给完整可复制提示词。普通工程推荐GPT-6.1 Sol高（high），实际运行模型/等级未核实。

## 上轮 CCGP 四类问题修复（历史本地验收，现已部署）

- 最新候选代码 `795ef5efa30b61dd47352c4fb888b02488f16855`：HTML表格限定采购需求章节并保留多合同包；识别分段产品名称表头；保留数量表头单位，冲突/未知明确单位拒绝；回补要求全部查询/详情及事件覆盖完成，单次事件查询失败即阻断。
- 冻结官方8份＋衍生负例2份原样重放10/10；原CLI正反例从1/3到3/3。新增13项解析＋10项CLI行为测试，全部945项Python、JS合约、TypeScript、Vite通过，主JS gzip116.17kB。完整空集可通过，部分失败/cap不能通过；2条历史差异提案仍apply_allowed=false。
- 本轮未部署Preview、未触发Queue、未做新浏览器或云端完整周期验收，未写数据库/快照/canonical/扫描时钟；原Preview仍保留eabd的历史版本绑定，不能用旧6/6替代新代码验证。Production/SSO于北京时间19:14只读复核未变，production_ready=false。
- [修复报告](ccgp-parser-gates-fix-2026-11-06.md)、[冻结证据](validation/ccgp-parser-gates-fix-2026-11-06/manifest.json)。下一步可仅部署Preview并定向读回，不触发全量Queue、不批量回补；canonical导出、迁移/并发提交/回滚及5条试回补仍未实施。

## 上轮 CCGP 模板扩查与历史回补方案（历史审查，当时门禁未过）

- 基于最新分支fdfeb11及应用eabd76f审查；新增离线工具/样本提交443b5cd，应用解析器和在线Preview未改。8份官方原始HTML全部200并冻结，另2份明确标记为衍生负例，不冒充官方原文。
- 模板门禁10例6通过/4失败：真实吉林血液透析机5台/套漏项、北京乳腺机1套丢单位；两种衍生资格表能覆盖正确采购需求。附件未知保持空、数量未知保持null及后勤服务排除正常。样本不是统计benchmark。
- 现有bootstrap实际CLI离线复现：全成功正对照通过，但部分详情或发现查询失败仍acceptance_ready=true/退出0，两个负例均失败。该CLI只产候选，不据此声称Production发生不完整发布。
- 新工具仅离线生成带版本/官方字节哈希的提案，任何情形都不自动应用。仓库历史892条仅作审查基线，不等于当前运行canonical；458空列表、17含null数量、59含纯数字数量均需审查，不能直接当bug数。生成河北4套扫描仪1条差异提案，因门禁未过而阻断。
- 6项工具安全测试及全部922项Python回归通过；模板/回补业务门禁仍未通过，不以测试数代替放行。没有新构建/部署、Queue、数据库/运行缓存写入、历史批量回补或模型请求。Production/SSO于北京时间16:59只读确认未变，production_ready=false。
- [本轮方案与问题清单](ccgp-template-audit-backfill-plan-2026-11-06.md)、[冻结证据](validation/ccgp-template-audit-2026-11-06/manifest.json)。下一步先修4类问题，再验10例及回补负例；之后才评估明确epoch、原子提交、并发保护和回滚的5条Preview试回补。

## 上轮采购产品项边界修复（历史 Preview 定向验收，当前仍服务eabd76f）

- 最新应用代码 `eabd76f4d35a62983c24e652d1ada45a7daf8e17`；[新隔离Preview](https://medicalchannelai-mbstj6o1a-rerisse7-1717s-projects.vercel.app) `dpl_Fk33cZFtMo6vwd5cFbSh57J8fZH8` READY，独立d库/受限角色，旧c消费者不能覆盖本次修正。
- 先冻结官方原始HTML，再修复CCGP全文包件正则跨入资格章节的问题。大口屯项目4条资格/优惠误项→10项真实设备；空气消毒器2台，其余各1台，身份/预算/窗口不变。11项新增边界回归，全部916个Python、JS合约、TypeScript、Vite通过。
- 没有触发Queue：在d更正一条真实记录并承接c最后已核验16条快照；其余15条facts和全部来源扫描时钟不变，按现有pipeline重算公开分/排序，目标仍51分。不是qa_fixture，也不是原生全量周期或canonical运行缓存/水位迁移。
- 修正时间 `2026-11-06T07:00:46.604901+00:00`；修复payload、Neon完整JSON、authority和普通浏览器SHA均为 `85a1768f1705a3f4bd403ec0b70f80292ac24948806546d4c9be1d690576fead`，SQL微秒精确；池16/Today5，页面6/6，包括ALL16/16、10产品可见且无资格误项、390px无横向溢出。来源健康8/14承接旧真实时钟，不代表本轮恢复。
- [本轮报告](product-items-correction-2026-11-06.md)、[冻结清单](validation/product-items-2026-11-06/manifest.json)。首次保护层307和两次UI脚本偏差独立保留，不计产品故障或验收通过；最终UI07:07:17Z完成，比20分钟边界超约2分20秒，后续须统一绝对截止时间，不再延长前台观察。
- 任务临时访问撤销、凭据文件清理；Production/SSO于07:06Z只读确认未变，原工作树/main干净；未合并、提升或改域名/DNS/EdgeOne。`production_ready=false`。其他CCGP模板/历史canonical回补、入口共享预算、每源独立提交与覆盖水位仍待推进。

## 上轮事件诊断与重试收尾修复（历史完整验收，来源降级）

- 采集代码 `662bd23cc572e16a13d093bd427fa322cc5166ac`；UI `77433ffffb3db1fd2c939dbbfbb08a8ee1fad955`，[Preview](https://medicalchannelai-34wdnmggn-rerisse7-1717s-projects.vercel.app) `dpl_EkAghRurnmMcJniNEQv4W29GQu4o` READY；c周期和独立c库/受限角色。905个Python、JS合约、TypeScript、Vite通过，5项源码位置断言替换为真实恢复行为测试。
- 唯一一次真实Queue完成25阶段：14完成、11降级，来源健康8/14，运行锁释放；从触发响应至发布2207.330秒。
- 8项目非空watch已实际执行，事件首次失败安全记录 `event_search / NETWORK_TIMEOUT`；完整事务通过，首次超时经第二次重试恢复。本次实际新增更正/终止事件0条；不把非空watch写成云端非空事件产物成功。
- 预算耗尽的地区实际失败后0.029–0.034秒即终局，上轮各地区约302秒；首次正常重试保留，fallback依赖降级直接跳过。重复投递、推进发送失败恢复、owner变更及发布失败不冒充成功有行为回归。
- canonical935、池16、Today5、事件0；深度Queue/SQL/authority SHA `e3e868c0b5b40cf656f178ee048ca4614f6e5904dfd385d2d77051b8446d2c73`；14:30自然tick后，当前SQL/authority/UI浏览器SHA `baf3d2ffe89223e6001e763e88845d310b5ed5cf22ddab5a3bfa75bc45eecb13`，SQL保留完整微秒；浏览器6/6通过。
- 当前依据：[完整报告](event-diagnostics-retry-2026-11-06.md)、[冻结清单](validation/event-diagnostics-retry-2026-11-06/manifest.json)。按入口统一限流退避、每源独立提交/覆盖回补、旧实时数据迁移及持续tick尚未验收；旧环境继续保留运行。
- 准备脚本曾回显未使用b部署的测试凭据；b临时访问已撤销、库仍0表，改用全新c库/角色和凭据，b角色不能读写c快照。原始错误/凭据不进入证据；当前UI临时访问已撤销，原采集链接只读复核401失效，临时凭据文件已清理。
- Production和SSO只读复核未变，原工作树干净；未合并、提升或改域名/DNS/EdgeOne，`production_ready=false`。

## 上轮 Preview 隔离周期（c858379，历史完整发布验收）

- 可执行代码 `2cc47ce5cae29f8eed57b411e647ccc356372719`，[Preview](https://medicalchannelai-p1uolbsrn-rerisse7-1717s-projects.vercel.app) `dpl_8oRuWziEBXmq1wKfVxZTSUosErYG` READY；标识 `mcai-p0-20261106-a`，独立数据库/受限角色 `mcai_p0_epoch_20261106a`。
- 真实新版Queue于北京时间12:11触发一次，13:18发布并释放owner；25阶段8完成、17降级，对应7/14源健康。TEDA403、五地区限流、非空事件核验失败尚未恢复。
- canonical923、池8、Today5、事件0；durable/cache通过。Queue、Neon完整JSON、权威及普通浏览器SHA均为 `95c7d41525212f3758e50579550fadc8b2034b78a16443d89390b09b35de9361`，SQL与payload精确到微秒；当前浏览器6/6通过。
- 889个Python、全部JS合约、TypeScript、Vite通过；补强真实完整消息负例后全部889个Python再次通过。本轮收尾仅改测试/文档/证据，不改变已部署应用代码。
- 新旧缓存键/标签、消息/幂等键、数据库和Preview凭据分离。旧库13:15仍46条且旧精度；新库12:11逻辑版本独立成功。旧消费者保留运行；8条是新验收集，未迁移旧最新数据，不宣称覆盖对齐。
- 当前依据：[完整报告](preview-epoch-cycle-2026-11-06.md)、[冻结证据](validation/preview-epoch-2026-11-06/manifest.json)。下一步优先补非空事件安全诊断、消除重试耗尽后的额外约302秒等待，再做入口共享冷却和每源独立发布/覆盖回补方案。
- 本任务临时分享链接均撤销；Production和SSO只读复核未变，原工作树干净；`production_ready=false`，不合并、不提升Production，不改域名/DNS/EdgeOne。

## 上轮来源故障处理与精度修复（e48990c，历史记录）

- 该轮可执行代码：`be87e5f34e088b7d39c381d5855030694b27d568`；[Preview](https://medicalchannelai-ix8zm70ut-rerisse7-1717s-projects.vercel.app) `dpl_F9c2jc8uJuiPELzoHY8rxGZc7aRH` READY，精确版本已读回。工作树/分支不变，原工作树干净。
- [本轮修复与验收报告](source-recovery-precision-2026-11-06.md)及[冻结证据](validation/source-recovery-2026-11-06/manifest.json)是本轮依据；下方47条/878测试/34浏览器项属于上一阶段，保留历史绑定。
- 完整构建884个Python测试、全部JS合约、TypeScript、Vite通过；本轮浏览器6项通过，4次自动AI缓存读取被测试护栏阻断，未发AI请求。
- 已修区域安全诊断、限流后查询止损、依赖终局降级后的fallback无效重试、明确拒绝访问的一次降级、数据库/缓存微秒版本比较和旧行相同payload重放修复。
- 云端对真实46条快照做相同内容重放，SQL时间与JSON微秒精确相等；早1微秒回退和同刻冲突均409拒绝，权威/普通GET/浏览器/冻结payload同SHA `45709c27420c7e856b69fd8b168237b12f3a71664bf982c68f8e825db1ef0488`。没有构造新测试版本或改事实/健康时钟，未批量迁移历史行。
- TEDA正常访问仍403；辽宁本轮真实本地请求限流，最终代码1次查询即止。程序侧修复不表示外部来源恢复，也不能解释昨天未保存明细的失败。
- 北京时间11:30旧部署a3f94bd自动tick及发布已实际观察；47→46是吉林一条项目当日09:30投标截止后退出池。持续调度未验收，新版完整Queue周期未触发；旧部署消息仍按旧代码处理，需后续处理旧消费者和版本隔离。
- `production_ready=false`。Production于2026-11-06T03:46:56.710Z只读复核仍`3216fd9`/`dpl_4LPKoTdusrvbExXuzbMKtnyiT86C` READY，SSO不变；本轮临时访问已撤销。未合并、提升Production或改域名/DNS/EdgeOne。

## 上轮真实采集与发布验收（6a1ec6c，历史记录）

- 工作树 `/workspace/MedicalChannelAI-p0`，分支 `codex/p0-reliability-contracts`；原工作树保持干净。
- 最新可执行/UI代码 `4575fa4e7721a234d74dd87e35163631019ec2c9`，对应 [UI Preview](https://medicalchannelai-j4ktac1cu-rerisse7-1717s-projects.vercel.app)，`dpl_7QNPqMxE5oehX52mEoZgjYzua2Vm`；READY；当前部署浏览器34/34通过，保持部署保护。
- 完整采集发布由 `a3f94bdd45ec1442c2031b46f640e8ca7a52be03` / `dpl_CCdUVJdpao3rse7QbczHVxvLsx8y` 实际执行；新 UI 未重新采集或手工发布。后续文档提交不改变这两个代码/部署绑定。
- 阶段：**LIVE_PUBLICATION_VERIFIED_WITH_DEGRADED_SOURCES**。`production_ready=false`；12/14来源成功，不能称全部来源恢复或持续调度通过。
- 当前依据：[验收合同](action-radar-acceptance-contract.md)、[本轮真实采集及发布报告](live-source-publication-acceptance-2026-11-06.md)、[冻结证据清单](validation/live-source-2026-11-06/manifest.json)。[此前受控验收](preview-acceptance-2026-11-06.md)保留079fa2e版本的45项HTTP及18/9/5项浏览器记录，不充当本轮新版本实测。
- 用户授权继续 Preview 三源与完整发布验收；未合并、部署/提升 Production，未改域名、DNS、EdgeOne、生产凭据或生产数据。

本轮真实页面及运行又修复：官方入口空壳检查、GB2312无损解码、妇产泛调研及正文用途解析、独立现场调研时间和跨端窗口关闭、未完成详情的 staging/barrier、硬停恢复事实丢失、二附院实际药品检验服务模板、增量失败安全诊断、原生 Queue 最大投递3次，以及市县地区造成11条记录漏显。之前的P0权威写入/读回、AI30小时门禁、账户隔离及固定可信代理继续通过回归。

| 验证 | 结果与边界 |
|---|---|
| 最新完整构建 | PASS；878个Python测试、全部JS合约/Prebuild、TypeScript、Vite；主JS gzip116.00kB |
| 三源真实deep | 调研8条事实；意向2条事实+1条不支持；妇产1条事实+4条设施类排除；三源deferred/staging/barrier均0，不等于净新增数 |
| 完整Queue周期 | 25阶段：22完成、3降级；3降级阶段对应TEDA/辽宁两个逻辑来源；触发响应至发布约44分44秒 |
| 权威发布 | canonical总数964、当前池47、Today5、事件0；durable确认、cache READY、active cycle释放、无人工qa_fixture |
| 数据一致性 | producer、Neon完整JSON、强制authority GET三SHA一致：`2ef3e305844ace80b056222993f4a6fc1fdc9cc5e5a1655eeda0088d8f146ee1` |
| 最终普通浏览器 | 普通GET首次CDN HIT/Age1，完整SHA一致；34/34检查、地区逐ID/依据链接、11条恢复、跟进刷新、390px四页通过；23次自动cache_only由测试护栏阻断，未发AI请求 |
| 首次普通浏览器 | 普通CDN GET相同SHA；发现真实11条漏显bug，已修复；首次脚本2处分母断言错误另记，不计产品故障 |
| 地区服务回归 | 原47条完整payload不变；ALL47/TJ8/BJ10/HL10/HE10/JL9/LN0；哈尔滨首卡保持HL；新UI浏览器34/34通过 |
| 真实降级 | TEDA官方403；辽宁详情核验聚合gate失败、原因明细缺失；辽宁fallback缺上游结果仍无效重试 |
| Production对照 | 仍为`dpl_4LPKoTdusrvbExXuzbMKtnyiT86C` / `3216fd9` / READY；SSO设置不变 |

唯一测试目标为独立Neon分支 `br-cold-tooth-a5clhljh` 的 `mcai_p0_acceptance_final`。权威逻辑时钟 `2026-11-06T01:43:03.095559+08:00`，实际发布 `2026-11-05T18:27:47.698032Z`。payload与哈希完整一致；SQL timestamptz列因Postgres.js/JavaScript Date截到毫秒，相差559微秒，不能称SQL列微秒精确相等。模型key为空，前一a3真实503仅验证降级提示；最终UI复验未再发AI请求。临时验收访问已撤销；Production与SSO于2026-11-05T18:46:26.401Z再次只读确认不变。

仍待推进：TEDA合法入口恢复、辽宁安全失败明细及依赖降级时跳过无效重试；版本时钟精度统一；来源分页/详情预算补齐和连续水位回补；非空事件链、持续自动tick、真实模型、国内P95及客户相关性/资格。已登记 `2026-11-06 11:30+08` 首个tick，尚未观察执行。CCGP仅扫描11月4日至6日；北京29候选只核验所选10条，其余是否医疗/有效未知。47条当前池不代表47条客户合格商机，964不代表本轮新增。

源级24/48小时、AI30小时阈值仍是工程初值；Gold Set15例仍是缺证规则冒烟稿。建议先修来源故障和依赖重试，再设计每源独立提交＋显式覆盖/水位，随后实施产品子项匹配与资格三态；不以单个健康标签或测试数代替产品/商业验收。

## 历史记录（截至 2026-09-04；以下不表示当前状态）

以下原文保留历史架构、CI 和源接入背景。历史分支、PR、runner、快照日期、部署状态及 PASS 只适用于其对应记录，未在本轮重新查询远端，不得解释为当前本地工作树或线上状态。旧 `checkpoint.json` 报告 #1457/558 测试，下方原文报告 #1472/581 测试；二者作为历史快照分别保留，不拿其中任何数字替代本轮验证。

## Product and safety boundary

MedicalChannelAI is a Tianjin-first medical-channel commercial intelligence / sales-assistant pilot for medical devices, IVD and consumables.

Fixed rules:

- public medical/procurement facts require traceable official evidence; unsupported critical facts fail closed;
- models may classify, match, explain and recommend actions, but may not invent hospitals, projects, budgets, dates, contacts, suppliers, brands, relationships or win probability;
- public intelligence and customer-private resources are separate layers;
- target hospitals are watch/focus objects only and never add relationship points;
- hospital relationships and product capabilities are used only after customer confirmation;
- private outcomes may support current-account review but never become public facts or automatically alter public ranking.

`production_ready=false`.

## Source-control and deployment boundary

- Active branch: `chatgpt/opportunity-ranking-v2-final`
- Draft PR: `#6` — `v0.4.1: opportunity ranking v2 final`
- Latest fully code-validated executable/runtime HEAD: `3663507b13dc57ca8d8179c51ae5b94303e936da`
- Latest successful full validation: GitHub Actions **Verify #1472 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` disables automatic Vercel deployments for this branch.
- User boundary remains: **no Preview generation, no Production changes/deployments, no merge** until explicitly changed.
- Latest observed Vercel deployment remains historical commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` / `dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre` (ERROR); no current source-expansion work is deployed.

## Latest executable validation

MedicalChannelAI remains private and uses repository-scoped GCP self-hosted runner `medicalchannelai-gcp-1` with labels `self-hosted`, `linux`, `x64`, `medicalchannelai-ci`.

Verify **#1472** completed successfully for `3663507b13dc57ca8d8179c51ae5b94303e936da` and executed:

- system Python **3.13.7** and Node **24.20.0**;
- `npm ci` and bundled snapshot refresh;
- **581 Python pipeline/contract tests — all PASS**;
- serverless entrypoint checks **11/12**;
- verified snapshot / medical scope / private profile / AI / runtime / collector boundaries;
- full prebuild;
- TypeScript `tsc --noEmit`;
- Vite production build;
- ranking summary.

Production build remains unchanged:

- `index.html`: **0.62 / gzip 0.38 kB**
- CSS: **41.30 / gzip 8.09 kB**
- main JS: **358.88 / gzip 115.27 kB**
- AI client: **5.43 / gzip 2.66 kB**
- OutreachDrawer: **12.16 / gzip 4.72 kB**
- Opportunity Pool: **18.45 / gzip 6.97 kB**
- Opportunity Detail: **50.45 / gzip 15.89 kB**
- Radar: **57.59 / gzip 17.29 kB**

The bundled ranking snapshot used by CI is still the historical verified snapshot dated `2026-09-03T13:31:21.991132+08:00` with 19 opportunities. The new procurement-intent source is code-validated, but CI does not perform its live network collection and therefore does not prove live intent data is already present in the snapshot.

This is code/build validation only. Preview is intentionally disabled, so no current-HEAD Vercel runtime acceptance or China TTFB/P95 claim is made.

## China-access / Today performance

Validated work remains:

- Today private profile and private-state reads are bounded/aggregated, reducing the main private data path from roughly ~7 DB round trips to ~2;
- schema bootstrap uses version fast paths;
- public history materialization is after-response side storage;
- detail initial reads are parallel and public history is on demand;
- follow-up mutations use bounded one-shot server-confirmed response reuse;
- Today runtime status/reminders are auxiliary and non-blocking;
- login/register uses a short one-shot in-memory auth handoff while refresh/new-tab remains server-authoritative;
- hashed assets and lazy secondary routes are restored;
- AI client and OutreachDrawer are on demand;
- normal `/api/today` omits full `opportunity_pool` while preserving Top-N and `opportunity_pool_count`;
- `/api/opportunity-pool/today` requests the full pool through the same private Function with `include_pool=1` and no extra Function slot.

The Today response split reduces response serialization/network bytes only. `_privateCore.js` still constructs/personalizes the full pool before projection, so no further DB/CPU reduction is claimed.

## Official early-signal source: 天津市中心妇产科医院 (`tjzxfc`)

Official source:

- domain: `www.tjzxfc.cn`
- index: `https://www.tjzxfc.cn/ywgk/zbgg/index.shtml`
- lifecycle: `MARKET_RESEARCH`

Validated behavior:

- broad official market-research discovery with strict detail medical-scope verification;
- hospital identity alone never makes a record relevant;
- non-medical facility/IT research is unsupported rather than published;
- title and official publication date must agree;
- exact deadline time is stored only when official text publishes it; otherwise date-only remains date-only;
- true verification/network failures fail closed;
- minimum detail interval 3 seconds;
- PR daily-deep wiring uses 30-day lookback / max 20 candidates / 3-second minimum delay;
- intentionally not in intraday scheduler.

Adapter Fast #1434 / Full #1435 passed; daily-deep integration Fast #1437 / Full #1438 passed.

## Official source: 天津中医药大学第二附属医院 (`tjzyefy`) — market research

Official source:

- domain: `www.tjzyefy.com`
- announcement index: `https://www.tjzyefy.com/xwgg/ggtz/`
- lifecycle: `MARKET_RESEARCH`

Validated behavior includes:

- research notice discovery excludes procurement-intent notices;
- shared medical-channel taxonomy is used rather than only a few generic title words;
- `液质联用` / `液相色谱` / `色谱` are supported medical-channel signals;
- strict official detail verification for hospital identity, title, publication date, product/service object and registration window;
- a generic `医疗设备` category is not invented for a specific LC-MS maintenance notice whose title does not state that category;
- date-only deadlines stay date-only;
- only transient network failures are retried;
- minimum detail interval 3 seconds;
- PR daily-deep wiring uses 30-day lookback / max 20 candidates / 3-second minimum delay;
- intentionally not in intraday scheduler.

Corrected adapter passed Fast #1449 / Full #1450; market-research daily-deep passed Fast #1451 / Full #1452 and was reconfirmed by later full validations.

## Official source: 天津中医药大学第二附属医院 — procurement intent

The same official announcement stream also contains medical `采购意向公告`. This is now represented by a separate validated lifecycle rather than being relabelled as market research.

### Lifecycle and ranking semantics

- canonical lifecycle: `PROCUREMENT_INTENT`
- public recommendation mode: `PRE_MARKET_SIGNAL`
- `INTERVENTION_STAGE`: **12/25**
- no published registration/bid deadline means `DEADLINE_URGENCY=0`
- `model_decision_status=AWAITING_MODEL`, allowing an explicit advance-layout analysis without implying a formal tender is open
- ordinary `MARKET_RESEARCH` keeps the existing `PUBLIC_OPPORTUNITY` / **25/25** intervention-stage contract

This prevents a supplier-consultation intent from being ranked as if registration or bidding were already open.

### Discovery and evidence boundary

Procurement-intent discovery is deliberately broad across official `采购意向公告` titles, because medically valid titles such as `脉动真空灭菌器等设备采购项目` may not contain the generic phrase `医疗设备`.

The detail layer then decides scope using the actual procurement object. It verifies:

- official hospital domain and same-host index/detail identity;
- hospital identity;
- title identity;
- official publication date;
- explicit `采购意向公告` semantics;
- supplier/service-provider consultation wording;
- specific product/service objects;
- medical-channel relevance independent of hospital identity.

Non-medical procurement intents are `unsupported`, not public opportunities and not source-fatal errors. True verification/network failures remain fail closed.

The shared medical scope was narrowly extended with `流式细胞仪` and `灭菌器`; generic words such as `干燥箱` were intentionally not added solely because a hospital published them.

### Timing and contact grounding

- no registration deadline/date is invented;
- no bid deadline is invented;
- official expected procurement wording such as a month or month range is **not converted to an exact date**;
- such month/range language is recorded only through `EXPECTED_PROCUREMENT_MONTH_WINDOW_UNSTRUCTURED` while the official source remains auditable;
- public contact is used only when the official page explicitly publishes it.

### Sync and daily-deep

The procurement-intent feed has a separate fail-closed sync path:

- default 30-day lookback;
- max 20 candidates;
- minimum 3-second detail delay;
- only transient network/408/425/429/5xx failures retry;
- non-medical intent = unsupported;
- unresolved supported/unknown detail failure blocks publish unless an older VERIFIED record covers the same opportunity;
- separate live records/report files;
- records feed the unified public snapshot;
- intentionally not in intraday scheduler.

The PR daily-deep definition includes this source on the existing self-hosted GCP runner.

Validation progression:

- procurement-intent actionability Fast #1461 passed;
- discovery/detail parser Fast #1467 passed;
- sync Fast #1469 passed;
- daily-deep integration Fast #1471 passed;
- **Full Verify #1472 passed with 581 tests**.

## Daily-deep runtime boundary

The PR version of `.github/workflows/tianjin-medical-refresh.yml` includes `tjzxfc`, `tjzyefy` market research and `tjzyefy` procurement intent, all on the self-hosted runner with a shared China-time refresh clock.

**Important:** PR #6 remains unmerged. GitHub scheduled workflows execute from the default branch, so these new daily-deep definitions are **code-validated but not active default-branch schedules**. No claim is made that the new sources are already being collected every day or that current Production contains them.

## Public intelligence / collector invariants

Existing guarantees remain:

- official-source discovery/detail verification and canonical VERIFIED facts;
- correction/termination reconciliation;
- public ranking without private relationship/product points;
- source-scoped incremental staging/barriers;
- bounded carryover and ledger retention;
- actual Queue delivery clock and stale cross-China-day rejection;
- deep/incremental serialization;
- one official discovery pass per runtime scan;
- unresolved verification barrier;
- once-daily legacy deep fallback definition;
- `tjzxfc`, `tjzyefy` market research and `tjzyefy` procurement intent are not silently added to intraday collection.

## Business-closure loop

Current pilot loop remains:

**discover opportunity/early signal → official evidence → confirmed private resource match → grounded outreach → explicit contact record → optional concrete next action → due-action queue → terminal result → private outcome review**.

Key private-state guarantees remain:

- copying outreach / tapping phone / tapping email never auto-writes `CONTACTED`;
- only explicit `已联系，记入跟进` records contact;
- reminders are independent from sales stage and require a concrete next action;
- reminder acknowledgement clears reminder only;
- WON / LOST / NOT_FIT / ARCHIVED require explicit reopen confirmation;
- ARCHIVED is workflow-terminal but excluded from outcome statistics;
- WON/LOST terminal transitions require controlled private review server-side;
- private outcome statistics remain current-account-only and do not alter public facts/ranking.

## Remaining acceptance gates

While no-Preview remains active, continue only code/test/data-boundary/business-closure work without making Vercel runtime claims.

When the user explicitly allows Preview again:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively from China and record TTFB/P95, response sizes and perceived loading;
3. verify normal Today omits the full pool while Opportunity Pool receives all current opportunities from the same Function;
4. verify `PRE_MARKET_SIGNAL` UI clearly communicates “采购意向/提前布局” rather than formal open tender;
5. run protected CONTACTED → optional next-action → reminder acknowledgement flow;
6. verify private WON/LOST/NOT_FIT review persistence/export and no public leakage;
7. verify collector Queue / daily-deep / intraday runtime behavior and snapshot freshness;
8. verify `tjzxfc` / `tjzyefy` real network parsing on an allowed runtime before claiming those sources operational;
9. run one same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
10. inspect custom-domain/Production promotion separately before any Production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
