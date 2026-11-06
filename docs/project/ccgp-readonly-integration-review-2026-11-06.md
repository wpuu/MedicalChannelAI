# d周期真实只读接入方案与阻断项审查（离线）

2026-11-06，起点43a900775039d5eb04c3102330cb8fd1a362f25e；工作树干净，仅根代理运行，无附着终端任务。开始13:20:34Z，前台截止13:40:34Z。已读取最新用户指令、工作约定、current-state、checkpoint、next-task及上一轮报告。本轮仅审查并产出方案，没有接入或调用真实缓存。

**结论：离线内核限定观察GO；真实只读接入NO-GO；迁移/纠错应用NO-GO。** 本轮未复现需要改动现有内核的缺陷，不改应用/内核及测试文件；只新增方案、状态和本地验收artifact，不新增校验引擎。下一轮只补下文最小接入守卫的离线实现；真实身份和权限仍未核实，不通过重复模拟推定已具备云端执行条件。

## 1. 最新代码事实与go/no-go

| 门槛 | 结论 | 代码依据与缺口 |
|---|---|---|
| 限定范围离线观察 | GO，限定语义 | [内核:194](../../web/collector_readonly_export.py#L194)先拒绝scope不符；[内核:212](../../web/collector_readonly_export.py#L212)双遍读取。冻结验证器本轮通过，原1007/10/3为代码绑定的历史日志，未重跑全套 |
| 58键计划与d物理键 | GO，离线一致 | [内核:47](../../web/collector_readonly_export.py#L47)、[namespace:9](../../web/collector_namespace.py#L9)、[区域键:417](../../web/collector_runtime.py#L417)、[增量键:40](../../web/collector_incremental_runtime.py#L40)一致；本轮机器清单与冻结116次轨迹逐项一致 |
| get-only适配方案 | 设计可行，尚未实现 | [接口:30](../../web/collector_readonly_export.py#L30)只调用get；[守卫:204](../../web/collector_readonly_export.py#L204)拒绝写能力接口。facade限制应用可调用方法，不等于提供商授予了只读IAM权限 |
| 真实scope/后端证明 | NO-GO，未核实 | [内核:251](../../web/collector_readonly_export.py#L251)明确scope_provenance_verified=false；字符串相等、数据库名相等及客户端自述不能证明缓存项目、Preview、租户/区域/后端命名空间 |
| 真实执行通道 | NO-GO，未核实 | 历史部署来源82cc43f，不包含9781921内核；[status:253](../../web/api/collector-status.py#L253)只返回状态/健康/增量摘要，不返回完整分片。没有已核实的无部署内部执行通道，不复用采集/Queue入口 |
| SDK与有界调用 | NO-GO，未核实 | [工厂:44](../../web/collector_epoch.py#L44)会构造真实客户端；[依赖:5](../../web/pyproject.toml#L5)只声明vercel、未锁版本。本地distribution检查vercel/vercel-functions均未安装；实际部署SDK版本、超时/重试/取消/响应大小能力未核实 |
| 真实观察执行回执 | NO-GO，待约定 | [封套:250](../../web/collector_readonly_export.py#L250)仍是OFFLINE_READONLY_CACHE_OBSERVATION；不能仅调用同一函数就声称获得已认证真实导出。未来需独立执行回执绑定来源/版本/范围，本轮不变原格式或dry-run输入种类 |
| 足以迁移/纠错 | NO-GO，独立阻断 | [内核:257](../../web/collector_readonly_export.py#L257)语义覆盖不全；统一revision/fence、事件与pending关系、可信当前版本、真实提交与回滚机制均缺。即使真实观察完成，migration_usable/apply_allowed仍false |

## 2. 接入位置和最小只读边界

采用“受控执行上下文 → 经独立验证的后端绑定 → 未加epoch的原生读取器 → get-only物理键白名单facade → 现有observe_d_canonical”的单一路径。未来适配器可以在既有受信上下文中拿到原生客户端的get能力，但**本轮及下一轮离线工作均不构造该客户端**。

内核已经在[214行](../../web/collector_readonly_export.py#L214)调用epoch_key；[现有_EpochCache.get:29](../../web/collector_epoch.py#L29)会再加一次epoch。因此不能把_EpochCache藏进只有get方法的facade后直接交给内核；直接交原生客户端也会因其写能力被内核拒绝。正确facade仅向未包装的原生get转发**原封不动的物理键**，在转发前验证键属于固定58键集合，不剥除前缀、不从调用者接收任意键、不切换后端、不追加epoch。只读能力不通过暴露底层对象供业务调用扩散。

本轮用本地空列表/None桩复现双前缀风险：正确原生get看到单个d前缀并返回显式空；错误的隐藏_EpochCache会产生两个d前缀并返回未初始化。这个错误甚至可能两遍稳定，不能靠“无异常/哈希一致”识别。它是接入方案的反例，不是当前离线内核已发生线上漏读。见[key与前缀证据](validation/ccgp-readonly-integration-review-2026-11-06/prefix-proof.json)。

scope必须在客户端构造与第一次get之前完成来源验证。预期仍是现有project_id、preview、mcai-p0-20261106-d、mcai_p0_epoch_20261106d，外加真实执行绑定所需的部署、租户及区域/缓存命名空间证据；具体提供商字段/claims不凭空假定。对照受信平台上下文和独立锁定的预期配置，验证失败或证据不足即停止。用户输入、环境变量字符串、自行decode未验证OIDC、缓存内容、数据库只读角色都不能单独替代后端绑定证明。[OIDC帮助函数:9](../../web/collector_oidc.py#L9)只取得token，不执行缓存身份认证；[数据库检查:31](../../web/api/_previewEpoch.js#L31)只核数据库路径，不核Runtime Cache。不得调用这些函数读取凭据来补本轮缺口。

尤其是[preview_epoch:9](../../web/collector_epoch.py#L9)在非Preview或缺epoch时返回None，工厂随后仍能构造未包装客户端；这是兼容既有环境的行为，不能拿“RuntimeCache构造成功”当作d身份验证。真实接入必须在构造前拒绝这些上下文，不能尝试get来猜后端是否正确。

最低所需能力：核对该现有项目/Preview/确切部署身份的只读元数据，及只对选定后端58个d物理键的get。是否存在这种提供商权限粒度、既有凭据是否满足、能否无部署执行，**全部未核实**。不申请/创建角色、凭据、环境，不改定时或保护，不把现有SQL只读权限当缓存授权。当前没有可执行真实通道；后续若必须部署、增加内部调用入口或扩大权限，须另列具体改动并取得用户明确授权，不能夹带进一次只读验收。

## 3. 58键/116次get的覆盖核查

所有逻辑键只经epoch_key一次，物理前缀固定`medicalchannelai:preview:mcai-p0-20261106-d:`。完整逐键列表、来源和哈希见[key-plan.json](validation/ccgp-readonly-integration-review-2026-11-06/key-plan.json)。

| 类别 | 键数 | 实际语义/缺失处理 |
|---|---:|---|
| canonical物理分片 | 13 | 8天津/医院分片＋BJ/HE/LN/JL/HL 5地区；覆盖14来源，tjfch/tjfch_test共享1键，不虚构两个副本 |
| CCGP events/watch/committed/staging | 4 | 分别保留，不将staging当已提交状态；[publish:1625](../../web/collector_runtime.py#L1625)优先使用committed中的records和events，两者同取该对象 |
| meta、deep owner、incremental owner/chain、source health | 5 | 原值/时钟保留，缺失不补默认成功、默认owner清空或“无pending” |
| ledger/bucket/pending/barrier | 36 | 9策略来源×4键；[实际增量来源:24](../../web/collector_incremental_runtime.py#L24)只有8医院，ccgp为策略声明/可缺失状态，不能要求4个ccgp键都存在；无区域增量或非CCGP事件键定义，不编造补齐 |
| 合计 | 58 | 正常两遍116次get；失败早停允许少于116，绝不重试、补读旧c/Production/其他区域或读公开快照 |

健康时钟来自[record_source_scan:235](../../web/collector_runtime.py#L235)：last_attempt_at、last_successful_scan_at、failure_reason、stale_after_seconds为来源维度。导出不能调用[snapshot_source_health:258](../../web/collector_runtime.py#L258)来填默认项。owner含cycle_id/activated_at/wall_heartbeat_at，增量含scan_id/bucket/source/observed_at；[心跳:125](../../web/collector_queue.py#L125)和[租约:228](../../web/collector_queue.py#L228)不是统一版本号。owner/meta全值有变化就拒绝；两遍不变或owner缺失也不能证明全局静止。

ledger保留entries和updated_at原值，bucket保留bucket_id/completed_at/result，pending保留记录列表，barrier保留URL字符串列表。[normalize_ledger:127](../../web/collector_incremental.py#L127)会忽略/归一化缺失字段，[_load_pending_records:85](../../web/collector_incremental_runtime.py#L85)将None归一成空，因此不用于导出。已有[跨分片校验:146](../../web/collector_readonly_export.py#L146)比publisher的[merge:1684](../../web/collector_runtime.py#L1684)更严格：遇到重复身份将拒绝，不在导出时静默归并。未知字段仍保留为不透明观察，不推定语义已覆盖。

committed中的records/events整体优先不是全局事务。canonical写入后才清barrier/pending，见[_cache_set:294](../../web/collector_runtime.py#L294)；新观察可能正处于这些分步写入之间。内核missing_canonical_or_event_keys列的是**原始键缺失**；committed有效时raw CCGP两个键缺失，不等价于publish的有效CCGP数据缺失，不能误当运行bug或用旧快照修复。

## 4. 单次调用与失败预算（拟定，尚未实现/实测）

未来一次受控观察限一个选定后端、一个d范围、一个批次，不在失败后自动重试：

- max_get_calls=116；严格按清单两遍顺序调用。只记录键/哈希/安全错误码，不打印凭据或原始异常文本。116是应用get次数，不是已证实的提供商HTTP次数；SDK隐式重试/额外请求必须能禁止或单独审计，否则不能宣称网络预算满足。
- 使用monotonic绝对截止：从单次执行启动计总计120秒，读阶段在110秒截止；单次get最多min(2秒,读阶段剩余预算)，到110秒不再读取且超期返回拒绝，最后10秒用于校验/封套生成，交付超过总截止时整份丢弃。内核只比较哈希，不负责抢占同步get；真实transport须支持可取消超时，且单次执行须有120秒进程/平台硬截止。仅在线程future上设置timeout不能证明底层调用已停止。SDK能力和执行载体未核实前真实接入仍NO-GO；这些数字是保守执行上限，不是完成率或延迟SLA。
- 保持现有4,000,000字节/值、16,000,000字节/双遍总量、10,000记录副本、500,000节点/值、32层。它们在get返回并编码后检查，不保证已限制网络响应或SDK解码内存；真实transport的响应流上限及取消方式仍需核实。不得提高阈值、截断列表、拆批后声称一个完整导出。
- None保持未初始化/不可用；显式空保持空。TTL无剩余寿命接口，无法区分驱逐、过期、未初始化；两遍变化则拒绝，稳定缺失可作为有限观察返回，但coverage/migration均false。任一必需读取异常/类型错误/超限停止，无partial success；失败不得自动触发采集、bootstrap、reconcile、owner恢复或调度。

TTL只反映写入策略，不能推算剩余寿命：[canonical默认14天](../../web/collector_runtime.py#L129)，health45天，ledger45天、bucket7天、pending/barrier3天，deep owner/chain2天、incremental owner15分钟。采集时钟、写入时钟、TTL与单调执行预算分别记录，不拿cycle_as_of充当活跃心跳或一致性版本。

## 5. 后续一次性真实验收清单（当前禁止执行）

1. 用户明确授权**现有d范围的一次只读身份核实及观察**后，先只核对项目/Preview/确切部署/后端上下文、可用执行通道及SDK版本/取消能力；不用旧部署状态当本次证明，不读取或回显凭据。不能满足则停止，不临时安装、部署或新增路由来绕过。
2. 构造前独立核对scope与后端证明；确认只暴露get、白名单为本轮58键、无epoch包装器、底层重试关闭、deadline可终止。任何项未验证均不开始116次读取。
3. 仅运行一批，记录身份引用、代码/SDK版本、后端选取、起止时钟、调用次数、字节量、每键状态/SHA及覆盖缺口；失败终止后不自动重新触发。只写受控本地验收artifact，无服务端数据写入。
4. 将真正的执行回执与内核观察摘要分开。真实输入的来源标签需在明确版本契约中审定，不能改名/拷贝现有合成artifact冒充真实数据，也不能把它喂给仅接受冻结仓库输入的原dry-run。即使全部读取成功，也继续apply_allowed=false、migration_usable=false。

迁移/产品纠错另需：可信完整canonical与有效committed事件、真实健康/覆盖水位和pending/barrier一致关系、统一原子revision/fence或等价已验证事务边界、before版本并发保护、后续事件/事实保护及真实回滚方案、独立写入授权。单个sha、两遍相等、读回执、owner lease或公开16条均不能替代。这些项不阻止有限只读观察，但阻止迁移。

## 6. 本轮验证与交接

现有[冻结验证器](validation/ccgp-readonly-export-2026-11-06/verify.py)执行通过，复核原23项行为/1007总测试日志、10/3门禁及正常/空封套重放；本轮未重跑1007/10/3，未修改应用/内核代码和测试文件，未部署或生成真实运行数据；新增的本地验收脚本只重放该接入反例。新证据记录58键清单、双前缀本地反例、源文件/行号及起点297份冻结文件完整性。所有限制保持：不改环境/计划/变量/凭据/权限，不访问云端、不推送、不采集或调用项目模型，不写数据库、运行缓存、原始数据、公开快照。

下一轮[next-task.md](next-task.md)只实现物理键/次数/deadline的最小get-only接入守卫，复用当前内核，不重复生成dry-run、模拟器或完整性引擎。它仍使用合成本地transport，不能解决真实后端认证，也不能声称实现抢占任意同步SDK调用。真实接入阻断保持NO-GO，避免把离线进展重复包装成真实导出。推荐GPT-6.1 Sol高（high）；实际运行设置未核实。当前界面无法生成该按钮。
