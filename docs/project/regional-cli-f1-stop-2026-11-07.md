# F1子项：区域CLI单次调用明确限流止损

2026-11-07（Asia/Shanghai），核对起点1352739，分支codex/p0-reliability-contracts、工作树干净，无其他活跃代理或相关在途任务。开始2026-11-06T17:36:55Z，前台截止17:56:55Z。读取最新协议、状态/checkpoint、next-task、F3报告、共享入口审查和验收合同后，只处理最新明确授权的F1区域CLI子项；F3不重复施工，SDK工作流保持CLOSED NO-GO。

实现提交`01ccaa9c1c9c1f7850d8ad2c9b870b43a966867c`；最终验收源码/测试提交及SHA256见validation-summary.json。不代表实际部署版本。

## 修复前后证据

真实argparse/main与冻结河北/黑龙江官方HTML，I/O边界替换为本地桩，socket/create_connection/build_opener均阻断，运行输入/records/report只写TemporaryDirectory。搜索/详情限流页是使用既有标识的合成挑战页，不冒称新下载的官方响应。

| 场景（2地区×2关键词×1公告类型） | 修复前 | 修复后 |
|---|---|---|
| 第2次scoped搜索明确限流 | 共4次搜索，继续访问后续地区 | 共2次搜索，同搜索host后续0；已发现候选仍可向独立详情host核验 |
| scoped完成后第1次fallback被429拒绝 | 共7次搜索，继续后续关键词 | 共5次搜索，拒绝后搜索host后续0 |
| 第1条详情403拒绝 | 仍请求第2条同host详情 | 共1次详情，同host后续0 |
| 第1条详情返回已有“访问频繁”标识 | 解析失败后仍请求第2条详情 | 在解析前识别，详情host后续0 |

以上失败场景修复前后均已受F3保护（exit2、records不变）；本次修复解决的是**额外请求扇出**，不重复宣称修复部分写入。[before.json](validation/regional-cli-f1-stop-2026-11-07/before.json)、[after.json](validation/regional-cli-f1-stop-2026-11-07/after.json)。

## 最小实现

- [复用分类:226](../../web/pipeline/scripts/sync_regional_ccgp.py#L226)：调用现有collector_diagnostics.failure_row，识别RATE_LIMITED、HTTP401/403/429及既有详情包装码；最多追溯6层显式异常cause。没有另写正则分类器，没有修改collector_diagnostics或runtime入口。
- [单次调用状态:268](../../web/pipeline/scripts/sync_regional_ccgp.py#L268)：blocked_hosts只在本次main内存中存在；[scoped:307](../../web/pipeline/scripts/sync_regional_ccgp.py#L307)、[fallback:363](../../web/pipeline/scripts/sync_regional_ccgp.py#L363)、[detail:434](../../web/pipeline/scripts/sync_regional_ccgp.py#L434)在请求前按显式目标URL的hostname判断。search.ccgp.gov.cn、www.ccgp.gov.cn和允许的裸域分别处理，不按共同父域熔断。
- [warmup:79](../../web/pipeline/scripts/sync_regional_ccgp.py#L79)：CLI注入可选反馈回调，将主页www的明确拒绝/限流反馈给后续详情守卫。默认不注入的runtime调用保留既有best-effort行为；普通主页超时不影响正常搜索/详情。
- [report:526](../../web/pipeline/scripts/sync_regional_ccgp.py#L526)：保存固定原因的blocked_hosts、scoped/详情未执行计数及fallback阻断标识，并增加ACCESS_BLOCKED_SCAN_INCOMPLETE。未知后续分页数不编造精确跳过总数；fallback未真正尝试时national_fallback_used不再声称已使用。records_written=false，沿用F3[写入门禁:560](../../web/pipeline/scripts/sync_regional_ccgp.py#L560)。

普通TimeoutError、URLError、详情NETWORK_ERROR及503不会触发host停止，后续独立候选仍按原有有界循环处理，但失败批次仍受F3拒绝。停止范围只限本次CLI调用的显式目标host，不是持久化冷却、跨进程/跨部署协调，也不是urllib内部重定向链的逐跳拦截。

## 验收

新增13项行为测试，区域CLI共28项；覆盖401/403/429、搜索/详情限流页、fallback后续关键词、包装异常、普通错误、不同host、warmup反馈、下一次CLI调用不继承停止状态，以及默认两种公告类型的嵌套扇出。原F3正反例、合法空、不创建失败输出、9种report别名保护继续保留。

最终全部1059项Python通过，冻结模板10/10、原bootstrap CLI3/3通过；完整回归采用既有外部网络/真实SDK导入阻断器。既有重定向单元测试使用本机loopback桩；F1/F3自身不构造真实opener或网络连接。原CLI3/3仍隔离空事件watch，不是完整事件业务验收。新增默认双公告类型测试后重跑最终套件；早先1058结果不作为最终文件版本证据。

408份1352739已有data/fixture/validation文件逐一SHA256不变，旧F3冻结验证器通过；旧原始数据、样本、历史验收和公开快照未写入。所有事实解析仍复用官方适配器；没有另建审查或模拟引擎。[证据索引](validation/regional-cli-f1-stop-2026-11-07/manifest.json)。

after.json成功用例允许原地更新临时records，故这些用例的inputs_unchanged可为false；这不是仓库输入变更。失败用例的临时输入/records及全部408份受保护仓库文件均保持原字节。证据校验器按这两个边界分别检查，不把合法成功写入误判为失败保护失效。

无外网、真实SDK安装/导入/执行、云端/业务/缓存/数据库/函数/Queue/模型访问；无新环境/路由、依赖锁/计划/变量/权限变更、部署或推送。apply_allowed=false、migration_usable=false。合成测试不是来源恢复或线上运行证据。

## 尚未完成与下一轮

F1区域CLI单次调用子项已离线完成；项目全路径统一止损、跨进程共享冷却/Retry-After调度和F2墙钟预算仍未完成，不能宣称完整F1已解决。既有请求timeout和sleep预算未改变；不能中断已经卡住的同步网络调用。

下一轮先仅文档确定**区域CLI的F2预算合同与唯一最小补丁边界**：根据真实调用者/工作流与现有timeout、sleep、分页/候选边界给出准确预算建议、传递接口和失败收尾保留时间，不把CLI总预算与runtime阶段预算混用，不新增模拟器，不先行修改应用或计划。完整任务见[next-task.md](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol高（high），实际设置未核实。
