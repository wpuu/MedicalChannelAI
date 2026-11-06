# 真实canonical只读接入：一次性变更决策

2026-11-07（北京时间），00:29:44开始，前台截止00:49:44。起点75c02dccb8b82c62ce74b03fe1e67501ad04f7f2，工作树干净，仅根代理运行，无附着终端任务。读取用户最新指令、工作约定、状态/checkpoint、next-task及SDK审计/接入/守卫报告。所有判断基于既有冻结资料，本轮没有联网补证。

**唯一推荐：暂停当前真实SDK接入分支，结论NO-GO；本轮只批准文档归档，不批准任何运行变更。** 当前精确候选的公开API没有已证实同时满足全部验收条件的路径，不能用新增入口或额外模拟层填补。这个结论只针对冻结候选和当前证据，不断言所有未来SDK版本或平台能力永久不可用。此分支到此结束，不安排重复模拟、定时探测或重复元数据查询。

这里关闭的是SDK接入工作流；既有Git隔离分支与工作树保留，不删除或合并。

## 1. 决策依据：不降低原验收合同

冻结候选是vercel **0.12.2**、vercel-cache **0.7.7**、telemetry **0.8.2**、httpx2 **2.16.0**，另有OIDC/core辅助切片。全部版本/包SHA256沿用[原审计清单](validation/ccgp-python-sdk-audit-2026-11-06/audit-summary.json)，5份关键源码与官方commit5b25d1d5f3c42a838e0af34164b84e027a1fdcab一致。它们是审计候选，**不是项目现有安装版本、完整依赖锁或推荐上线版本**。

| 必须满足的条件 | 已有实现/公开证据 | 缺口类别与裁决 |
|---|---|---|
| 58个d输入键、最多116次get、失败不部分成功 | [守卫:104](../../web/collector_readonly_guard.py#L104)和[finish:126](../../web/collector_readonly_guard.py#L126)已在合成本地transport实现 | 已有离线实现，不能当真实SDK验证；保持原合同 |
| 单次min(2秒,剩余读预算)、读110秒、总120秒 | [原生构造/get:22](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L22)无公开timeout；[BuildCache:39](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/cache_build.py#L39)固定30秒 | 当前候选API不提供所需注入能力，NO-GO。不能传timeout_seconds给原生get，也不能私改_client冒称公共接口 |
| 读取失败必须拒绝，不伪装合法空 | [BuildCache:41](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/cache_build.py#L41)默认将异常转None；[resolver:230](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L230)直接返回context cache | 已证实默认失败语义不满足；strict只覆盖部分路径，不能独立放行 |
| 缺上下文不回退到其他状态 | [resolver:138](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L138)可能内存fallback；155行remembered对象优先于strict缺配置检查 | 已证实默认fallback风险；平台实际注入对象语义未覆盖，NO-GO |
| 无额外写请求/遥测 | [telemetry:13](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/internal/telemetry/client.py#L13)有公开环境开关、33行atexit；[145行](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/internal/telemetry/client.py#L145)发送POST | 关闭遥测有源码支持的开关VERCEL_TELEMETRY_DISABLED=1，但需要独立配置授权且须在模块读取配置前生效；本轮不设变量。单独关闭也不解决其他阻断 |
| 响应/解码前有界，不靠返回后截断 | [BuildCache:57](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/cache_build.py#L57)r.json；[httpx2:985](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/httpx2/_client.py#L985)普通调用先read完整响应 | 所审公开cache API未提供响应流大小上限；4MB/16MB是返回后观察器阈值，不能替代；NO-GO |
| 零自动重试、网络次数可证明 | [HTTPTransport:132](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/httpx2/_transports/default.py#L132)默认retries=0；cache get无显式重试循环 | 仅这些层已证实；httpcore2、context对象及完整依赖闭包未审，不能承诺完整链路；遥测还会增加请求 |
| 可信项目/Preview/d/后端/区域身份，匹配写入器键变换 | [resolver:146](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L146)读取endpoint/headers，[utils:6](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/utils.py#L6)执行默认hash | 真实绑定/配置和实际SDK版本未核实，不是已证实不支持。不能从字典、元数据查询或32位hash推导授权；不能改变写入器hash |

官方[环境/计划范围:196](validation/ccgp-python-sdk-audit-2026-11-06/official-reference.md#L196)说明Hobby同团队共享、Pro/Enterprise每项目独立，实际计划未知；[单项容量:205](validation/ccgp-python-sdk-audit-2026-11-06/official-reference.md#L205)为2MB。本地4MB观察阈值不代表可写4MB，不调整任何现有阈值以凑放行。

## 2. 已排除的替代路线

| 路线 | 为什么不能选作本轮最小可行方案 |
|---|---|
| 直接把RuntimeCache.get接在现有守卫后 | 原生签名不接受预算，可能吞错、fallback和telemetry；守卫返回后检查不能阻止前面的长时间阻塞或超量解码 |
| strict=True＋关闭遥测＋外层future timeout | strict不保证注入/remembered对象严格，缺响应流上限；future停止等待不等于停止底层调用。即使配置得到授权仍不满足全部合同 |
| 切到AsyncRuntimeCache | [异步构造/get:58](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L58)无strict/timeout参数；异步任务取消与实际请求清理/硬截止未验证。不能因为awaitable就宣称满足2秒和整批失败语义 |
| 修改SDK私有_client、全局remember/context或内部BuildCache | 不属于已证实的公开可支持扩展面；绕过resolver、认证/缓存协议等需另行稳定契约，不作为支持方案 |
| 直接拼接RUNTIME_CACHE_ENDPOINT/HEADERS，自己实现HTTP GET | 公开源码暴露实现不等于公开稳定服务契约；身份验证/重试/限额/协议支持均未成立，不能用它绕过本次NO-GO |
| 新建HTTP维护路由/借Queue执行 | 路由本身不能修复SDK；[vercel.json:15](../../web/vercel.json#L15)collector-run/status为60秒，[queue:18](../../web/vercel.json#L18)300秒且有重投递配置，均非已验证的单次只读120秒载体。不能复用业务/调度入口或把maxDuration当精确强制取消证明 |

没有选择私有接口补丁或新模拟transport作为“下一条可行路线”，也不继续寻找未经用户批准的环境、凭据或执行侧门。

## 3. 本轮可批准/拒绝的准确变更清单

**批准项是暂停与文档归档；应用变更数为0、运行依赖版本变更数为0、路由数为0、权限/变量/定时变更数为0。**

| 文件/对象 | 本轮处理 | 若有新证据重启时的边界 |
|---|---|---|
| docs/project/ccgp-runtime-integration-decision-2026-11-07.md | 新增本决策包 | 作为关闭和重启门槛基线 |
| docs/project/current-state.md、checkpoint.json、next-task.md | 更新真实状态和后续主线任务 | 不覆盖历史验收或把未知写成已完成 |
| docs/project/validation/ccgp-runtime-integration-decision-2026-11-07/ | 新增证据索引、决策矩阵、完整性和时间记录 | 不另建模拟器 |
| web/pyproject.toml及依赖锁 | 不修改，不将0.12.2/0.7.7锁成上线版本 | 待出现满足合同的精确公开版本和完整依赖hash后，单独审定；目前无可填写的合格升级版本 |
| web/collector_epoch.py、collector_readonly_export.py、collector_readonly_guard.py | 不修改，不启用真实模式 | 仅在后端身份与受支持transport全满足后，另审最小差异；不删除声明为合成的边界 |
| web/vercel.json、web/api下文件、现有执行入口 | 不修改、不新增维护路由 | 是否必须新建HTTP入口仍未核实；需要的是被验证的受保护单次执行能力，不能预先批准一个虚构路径 |

## 4. 执行载体、身份、最小权限与重启条件

当前没有推荐可部署的执行载体，**也不请求新增权限来尝试运行**。强制终止载体、公共transport能力、可信后端身份缺一不可。已有只读项目元数据/公开资料权限保留，但不是缓存读取、凭据读取、配置、部署或写入授权。

只有在出现实质新证据后才重开：

1. 有正式文档/精确源码支持预算可注入、所有路径严格失败且无fallback、有限响应流/解码、可验证的无重试和无额外POST；或供应商给出等价稳定公开执行契约。必须逐项证据化，不仅是一个新版本号。
2. 有可核实的既有d项目/Preview后端身份和写入器键变换；实际运行版本、计划、区域/缓存命名空间可安全绑定，不读回/打印凭据。未获得这种证据就不构造真实客户端。
3. 有明确单次执行载体及2秒单次/110秒读取/120秒总预算的终止与清理证据，响应上限在解码前生效。被杀进程/平台停止是否留下后台请求、遥测或隐式重投递必须纳入验收，不能仅凭配置名推定。

若全部前置条件成立，未来一次最小授权应精确分开审批：已审定文件/依赖差异的本地实现；若需要则既有Preview精确提交的单次部署/维护入口与遥测配置；再单独授权只对项目prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM、mcai-p0-20261106-d选定后端58键的至多116次get和受控本地artifact。禁止其他项目/旧c/Production、缓存/数据库写入、owner恢复、采集、Queue、模型和计划更改。不存在实际可行路线之前，不让用户批准未知版本、未知路由或宽泛权限包。

## 5. 唯一一次真实验收流程（当前未执行、未授权）

条件全部满足并获对应授权后：先离线复核精确代码/依赖hash、凭据不落盘/日志策略和终止机制；再构造前核对可信d范围及后端绑定。先拒绝缺/跨标识，验证get-only能力与58个SDK输入键及相同writer变换，确认无fallback/telemetry/重试。然后仅运行一个受保护批次，最多116 get、单次<=min(2秒,剩余读预算)、读110秒/总120秒、单值4MB/双遍16MB及既有记录/结构上限不放宽。服务存储2MB限制另保留。

真实版本/owner变化、任何读取/解析/大小/截止失败整份拒绝，合法空必须来自已认证后端且保留缺失语义；输出仅受控本地摘要/hash及独立运行回执，不能沿用合成标签假称真实。失败就结束，不自动再触发采集或反复重试。即使观察完成，也继续apply_allowed=false、migration_usable=false；全局原子revision、事件/pending关系及真实CAS/回滚另有独立门槛。

本节只是未来验收清单，不能作为当前已具备载体、SDK能力、权限或完成真实导出的证明。

## 6. 本轮验证、关闭与下一步

复核既有SDK冻结验证器通过：6个wheel hash、5份官方源码匹配、get签名和旧324份输入保护；这是本轮执行的静态完整性校验，非重跑1031/10/3。起点全部既有data/fixtures/validation文件另行做hash保护，源码、应用、依赖锁、内核和守卫不变。没有联网、安装/执行SDK、项目元数据/凭据/环境值/日志或业务访问，没有部署/推送/路由/环境/计划/权限变化。apply_allowed=false、migration_usable=false。

**SDK真实接入分支以NO-GO关闭**。不把此暂停等同于取消MedicalChannelAI整体目标；下一轮[next-task.md](next-task.md)返回已登记的主线未完成项，离线审查共享官方入口的限流/重试预算，只形成最多3项有源码/既有测试依据的问题与优先级。它不依赖真实canonical导出，不重开SDK分支，也不把旧健康7/14或8/14当当前状态。推荐GPT-6.1 Sol高（high），实际运行设置未核实。当前界面无法生成该按钮。
