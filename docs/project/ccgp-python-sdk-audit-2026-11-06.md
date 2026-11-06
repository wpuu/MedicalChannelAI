# 官方公开Python SDK静态审计

2026-11-06，北京时间22:24:56开始，前台截止22:44:56。起点315136a，工作树干净，仅根代理运行。已读取最新用户授权、协议、状态/checkpoint、next-task和前轮报告。本轮只GET公开文档、分发元数据和源码；没有安装、导入或执行SDK，没有查询项目云端元数据、运行数据、凭据或环境变量值。

## 归属、版本与可复核来源

官方[Python API文档](https://vercel.com/docs/functions/functions-api-reference/vercel-sdk-python)明确`pip install vercel`和`from vercel.functions import RuntimeCache`；[Vercel官方仓库](https://github.com/vercel/vercel-py)README也声明同一安装包。保存了官网直接返回的Markdown，第三方文档索引仅作发现线索。PyPI包METADATA声明Python SDK for Vercel。进一步将wheel中的functions导出、cache resolver、BuildCache、key transformer及telemetry client五份源码与官方仓库固定commit **5b25d1d5f3c42a838e0af34164b84e027a1fdcab**逐字节比较，5/5一致；见[provenance.json](validation/ccgp-python-sdk-audit-2026-11-06/provenance.json)。一次错误的顶层monorepo路径404已记录，按保存的官方目录修正，无安装/执行。

选择公开稳定候选 **vercel 0.12.2**（分发上传2026-11-03）。其缓存代码不在顶层wheel中，而来自独立依赖`vercel-cache>=0.7.7`，因此冻结以下审计切片，不将它伪称完整安装锁文件：

| 包/候选 | wheel SHA256 |
|---|---|
| vercel 0.12.2 | `0850bf130e208c8cc63898971d70caeaa165357f615db6d7588336b78e54b366` |
| vercel-cache 0.7.7 | `054f2ba61559c9e7865106def43681370849803c0310baf6b0da4ca3a9e3c266` |
| vercel-internal-telemetry 0.8.2 | `21ba7ea4908d2add1cdeed7d560432b0435e16d194872e13c8da030fe3718151` |
| httpx2 2.16.0 | `fd2c5d7909e8d86fe92d53020c310ca0e4e431b838c207c5754b9bbf0308d49a` |
| vercel-oidc 0.11.0（辅助边界） | `5a106197178807b5f30c71ccbc75e97a6a6e8428de31f37658f95456d8febe06` |
| vercel-internal-core 0.2.2（辅助元数据） | `581b02309ec8d6367134c3ecabba5d8169a902677458e228f544dc88dfa05a6b` |

URL、SHA、公开查询时间窗口见[download-ledger](validation/ccgp-python-sdk-audit-2026-11-06/download-ledger.json)和[audit-summary](validation/ccgp-python-sdk-audit-2026-11-06/audit-summary.json)。wheel仅作为ZIP读取并提取指定源码，未将其加入sys.path。公开候选和仓库commit**均不等于既有部署实际安装版本**，本轮未补齐该运行事实。

## 静态证据与go/no-go

以下均引用冻结wheel中的原始行号，不执行示例或源码：

| 审查项 | 源码证据 | 结论 |
|---|---|---|
| 同步/异步接口 | [runtime_cache.py:22](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L22)同步构造参数仅key_hash_function/namespace/namespace_separator/strict；get(self,key)在34行；异步get在68行 | 接口已证实。**不能给原生get添加timeout_seconds参数**；本地transport协议不是SDK原生签名 |
| key与namespace | [utils.py:6](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/utils.py#L6)默认djb2 xor 32bit十六进制hash，namespace存在时再加`namespace$hash`；runtime get调用_make_key | 58键白名单约束SDK输入层的d键字符串，不是后端最终存储key。必须与写入器相同变换，不能为“原样转发”擅自换成identity hash，也不再套项目_EpochCache |
| 后端选择/身份 | [runtime_cache.py:230](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L230)优先请求context.cache；146行起读RUNTIME_CACHE_ENDPOINT/HEADERS；[context.py:35](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/context.py#L35)是ContextVar快照 | 选择机制已证实；代码没有在这条get链自动核对本项目/d/Preview/数据库/区域或做OIDC签名校验。真实后端身份仍未核实，NO-GO |
| 缺上下文与错误 | [runtime_cache.py:138](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/runtime_cache.py#L138)禁用/缺运行配置时默认内存fallback；[cache_build.py:41](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/cache_build.py#L41)404和stale为None，其他异常默认也返回None | **不能把None当真实空canonical**。RuntimeCache(strict=True)存在，但context.cache和已remember的cache路径可直接返回原对象，strict并不保证这些路径都严格；异步公开构造没有strict参数。默认SDK不满足读取失败整批拒绝 |
| timeout与硬取消 | [cache_build.py:39](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/cache_build.py#L39)创建固定30秒httpx2 timeout；异步174行同样30秒，无公开get timeout参数 | 不满足单次2秒/剩余预算注入。网络timeout不是总墙钟硬截止。源码未提供原生get抢占取消契约，守卫不能把阻塞的SDK调用强制中断；NO-GO |
| 重试/网络次数 | cache get无显式重试循环；[httpx2 default transport:132](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/httpx2/_transports/default.py#L132)默认retries=0并传给httpcore2 | 仅证实这些层。httpcore2实现、注入context、完整依赖闭包未审，不能保证整个运行路径零重试或116个get就只有116次HTTP请求 |
| 响应大小 | [cache_build.py:43](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/cache_build.py#L43)普通GET后r.json；[httpx2 send:948](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/httpx2/_client.py#L948)stream=False时987行response.read | 本读取路径没有应用级响应体字节/JSON节点上限。现有4MB/16MB检查发生在get返回之后，不限制SDK的下载/反序列化内存；NO-GO |
| get路径写副作用 | BuildCache.get不调用canonical set/delete，但会track；[telemetry client:13](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/internal/telemetry/client.py#L13)默认开启、33行注册atexit、145行POST；[in_memory:13](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/cache/cache_in_memory.py#L13)过期get会delete | **get-only facade不等于SDK纯读**。可能多出telemetry POST，内存fallback还可能删除过期项。仅静态识别开关名，本轮不改环境、不执行遥测/读写。未解决前不能证明零额外写调用 |

## 身份和官方使用限制的补充

- OIDC包有单独的[verify模块:342](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/oidc/verify.py#L342)进行签名/时间等校验，需verify extra；**存在验证函数不表示RuntimeCache调用了它**。这里只核查存在性与调用边界，未审完全部issuer/JWKS实现、未下载其验证依赖、未取得或验证任何实际token。
- [telemetry credentials:19](validation/ccgp-python-sdk-audit-2026-11-06/wheel-source/vercel/internal/telemetry/credentials.py#L19)的项目/团队ID提取来自参数、环境、解码payload或本地project.json，用于遥测，不是Runtime Cache授权证明。源码中的变量名不是读取实际环境值；本轮没有执行这些函数。
- 官方[文档第196行](validation/ccgp-python-sdk-audit-2026-11-06/official-reference.md#L196)说明缓存按deployment environment隔离，Pro/Enterprise每项目独立，Hobby同团队各项目共享。此前“总是按项目隔离”的概括不充分；**实际团队计划仍未知**，不能因项目ID匹配推定缓存独立。
- 官方[文档第205行](validation/ccgp-python-sdk-audit-2026-11-06/official-reference.md#L205)单项存储上限2MB。观察器4MB是本地拒绝阈值，不是服务端可写容量承诺；本轮不评估真实分片大小、不回补、不调整阈值。
- SDK默认resolver还可能复用进程remembered cache。仅用新RuntimeCache对象、strict参数或本地scope字典，不能独立证明这次选中了正确d后端。debug路径会打印endpoint/headers，未来也不能以debug输出来取身份证据。

## 实际完成、限制与后续

归属/版本/包hash和上述源码事实已完成静态核对，**直接SDK接入仍NO-GO**。阻断是明确的默认失败语义、fallback/telemetry、不可注入的get预算、响应流限额和未认证后端，不应再新加一层假transport来包装成已解决。完整依赖闭包、平台context实现、运行版本和真实执行通道仍未覆盖。

本轮仅文档和公开artifact变化，原应用、依赖锁、内核9781921、守卫605ebad和测试均未改，未新增模拟层，未运行1031/10/3。起点324份数据/fixture/既有证据字节不变。未安装/导入/执行SDK，项目元数据查询0、业务/RuntimeCache/数据库/函数/Queue/模型调用0；未读凭据/环境值/原始日志，未部署/推送或改变环境/计划/权限，apply_allowed=false、migration_usable=false。见[证据清单](validation/ccgp-python-sdk-audit-2026-11-06/manifest.json)。

下一轮[next-task.md](next-task.md)只根据本次精确源码证据，准备**唯一推荐的最小真实接入变更提案与授权包**：明确解决失败语义/无fallback/无telemetry/预算及响应限额的公开支持路径或供应商缺口、需改文件和运行载体、验证与最小权限。不重复此前泛化方案，不造SDK参数、不写新模拟器，不实现/部署真实入口。本轮不把公开候选升级成实际运行版本。推荐GPT-6.1 Sol高（high），实际设置未核实；当前界面无法生成该按钮。
