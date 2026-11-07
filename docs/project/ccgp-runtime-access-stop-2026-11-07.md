# Queue CCGP单次stage明确拒绝止损R1：离线复现与修复

2026-11-07（Asia/Shanghai）。起点7e65828，旧应用fea6fc7，现有分支codex/p0-reliability-contracts；初始工作树干净，仅根代理，无相关在途工作。读取最新用户四文件授权、working-protocol/current-state/checkpoint/next-task、主链收口、发现/事件预算实现、区域R1及行动雷达合同。前台09:39:07Z开始、09:59:07Z截止。

代码提交 **3f88ff7211200e314dcb6bafa894ec127c1b29bf**，恰好修改授权四文件：collector_runtime.py、sync_ccgp_query.py、既有test_runtime_source_parity_behavior.py及test_ccgp_events.py。其余仅本轮文档与新增artifact；apply_allowed=false、migration_usable=false。SDK及硬取消/严格时限、原子提交/自动回滚和崩溃持久回执强保证保持CLOSED NO-GO。

## 先复现，再修复

使用既有run_stage/query入口、MemoryCache、固定monotonic、冻结天津大口屯HTML/manifest及已有事件fixture；只替换搜索解析边界和HTTP transport，实际执行原事实/事件adapter。外网及真实SDK阻断，输出仅临时目录。

应用源码未修改时，新增1个unittest方法、ccgp/event1/event6×401/403/429共**9个子例全部失败**。首次明确拒绝后，事实仍共2次同host详情请求，事件仍共8次；预期均为1。修复前在请求次数断言处结束，未据此虚构旧canonical/pending保护状态。见[before.json](validation/ccgp-runtime-access-stop-2026-11-07/before.json)、before.log及原测试片段。事件请求扇出身份为本地合成，不冒充多个官方项目。

## 实际变更

- [事实入口局部集合与安全汇总](../../web/collector_runtime.py#L660)、[事件入口局部集合](../../web/collector_runtime.py#L890)仅有budget的既有Queue路径显式启用。字典只属于一次stage，发现跨关键词/类型、事件同片跨项目共享；不写缓存，不跨stage、重试、进程或部署继承。
- query的[scan_events](../../web/pipeline/scripts/sync_ccgp_query.py#L87)及[discover_candidates](../../web/pipeline/scripts/sync_ccgp_query.py#L221)只增加可选blocked_hosts；函数内延迟取得既有access_block_reason/failure_row，保留无guard及CLI默认行为。没有改共享分类器、CliBudget或HTTP helper。
- 明确搜索拒绝登记实际search hostname并抛固定错误，当前不完整stage直接失败，不再执行第二类型/关键词或后续项目。详情按实际URL hostname准入：401/403/429、限流HTML或包装cause登记拒绝；之后同host跳过，另一合法详情host继续核验。搜索、www与裸域不按父域合并，不新增重定向逐跳拦截。
- [事实详情拒绝](../../web/collector_runtime.py#L782)、[事件详情准入](../../web/pipeline/scripts/sync_ccgp_query.py#L164)在adapter前识别marker；拒绝/跳过的事件详情不制造discovery-only fallback。普通及时TimeoutError/URLError、503和解析错误不登记整个host，原有界处理及及时普通事件fallback保留。预算异常先走原超期分支，不被拒绝分类吞掉或生成迟到证据。
- 事实不再把异常message拼进PUBLISH_GATE错误；复用固定phase/reason、计数及最多5个candidate_ref哈希。query内部原CLI报告可保留原格式，guard路径附带安全行供runtime提取；原文/URL/标题/项目号/查询不会随失败诊断持久化。事件原安全转换继续兼容既有未附安全行的报告。只有workflow结果/诊断变化，公开数据结构不改。

源码行号和哈希绑定见[23处引用](validation/ccgp-runtime-access-stop-2026-11-07/source-references.json)。runtime只改_run_ccgp/_run_event_batch，query只改两个函数及必要导入；其他函数/类均AST保持，包括run_stage、区域R1、publish、_cache_set/_cached_list及所有Queue/lease/pending/健康/版本/配对helper。

## 保护与实际验证

新增 **11项测试**（runtime8、event helper3）。最终 **1213项Python、冻结模板10/10、原bootstrap CLI3/3全部通过**，0失败/错误/跳过。原CLI门禁仍隔离空事件watch，不是完整非空事件或真实来源验收；Node/JS源码未改未重跑。171项定向在最后增强搜索状态和guard导入断言前通过；最终1213已包含这些增强，不把中间定向输出称为最终版本单独重跑结果。

| 边界 | 本地观察 |
| --- | --- |
| ccgp/event1/event6×401/403/429 | 同host详情共1次，后续0；失败503，旧committed/staging/pending/成功时钟保持 |
| 搜索401/403/429、包装cause及marker | 搜索共1次，不继续类型/关键词/项目，详情0；固定安全诊断 |
| 详情包装cause/marker | 同host共1次，adapter0；不新增拒绝详情fallback，reason保留HTTP或RATE_LIMITED |
| www拒绝与裸域合法详情 | www后续0，裸域仍实际核验；整体不完整仍不提交部分事实/事件 |
| 普通及时timeout/network/503/解析失败 | 同host后续继续，stage不完整仍503，旧数据/pending/成功时钟保持 |
| 同一FAILED stage第二次run_stage | attempt_count=2且重新允许原host请求，不继承上一调用拒绝集合；最终降级规则仍由原Queue控制 |
| 完整成功/合法空 | ccgp双键PREPARED_LOCAL_READBACK，event1只staging，event6配对提交；源成功时钟仍按七阶段门禁 |
| 返回/异常迟到及timeout参数 | 原工作超期拒绝，停止后续请求，不形成新证据；cap30/剩余−1保持 |
| 无guard/CLI与两种导入顺序 | 原默认路径及及时普通fallback保持；两种导入顺序后实际调用预拒绝guard，零网络且无循环 |
| 旧pending、部分准备、未知写、重复投递、foreign/owner/硬停 | 既有完整回归保留；本轮不改其协议，不声称新增强保证 |

[cases.json](validation/ccgp-runtime-access-stop-2026-11-07/cases.json)直接复用本轮unittest helper归档**78源阶段与10helper回放**；仅保留合成请求的kind/host/timeout及状态保护布尔值，不另建模拟器。搜索解析是现有测试边界桩，真实事实adapter使用冻结官方HTML；事件使用已有fixture。首轮正例因测试复用合成URL导致DUPLICATE_EVENT_ID而拒绝，已为不同事件查询赋独立合成URL；没有放宽去重/配对门禁，最终全套通过。

测试进程用空实际配置、-B禁止运行字节码缓存，外部连接/DNS与真实vercel导入阻断，仓库内输出写入拒绝；已有loopback安全测试仅本机桩，prewarm/generated输出均来自原有替身，没有项目模型调用。最终门禁输出先写临时目录再归档。

**612份起点data/fixture/旧artifact及451份其余web/workflow文件不变**。Queue文件未改，发现270/150/60/60、事件270/180/30/60及原点保持；seed初始化的可能写入照旧披露，committed优先、staging/watch准备/部分未知、完整片/单键配对、pending和兄弟staging、成功时钟、原尝试限额/最终降级、owner及独立调度均保持。[验证摘要](validation/ccgp-runtime-access-stop-2026-11-07/validation-summary.json)、[证据清单](validation/ccgp-runtime-access-stop-2026-11-07/manifest.json)。

## 收口与下一步

**R1的Queue CCGP单次stage止损和事实安全诊断子项已离线复现、修复、验收关闭。** 不是全项目F1完成；共享host跨进程冷却/Retry-After、其他来源止损及七个deep/七个其他增量的预算仍未实施。真实部署、来源恢复、延迟/召回、持久化、公开读回及客户交付未核实。没有网络/实际环境值/凭据/运行日志/真实云端或运行数据访问，没有部署/推送/workflow触发、新环境/路由或计划权限变更。

唯一下一优先项：**R3现有d Preview一次性验收变更/授权决策包，仅离线文档**。用最新本地代码和历史云端记录区分版本身份、部署/受控触发/读回及副作用，给一份可审阅的GO条件或明确NO-GO；不重复收口、不机械铺预算、不重开SDK/强保证或拆多轮模拟补证。本轮不部署、不申请权限或触发业务。完整任务见[next-task](next-task.md)。当前界面无法生成该按钮；推荐GPT-6.1 Sol xhigh，实际设置未核实。
