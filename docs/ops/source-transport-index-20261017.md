# MED-ACTION-P0-001：请求deadline与索引覆盖保护

日期：2026-10-17。状态：**OFFLINE_GUARDS_IMPLEMENTED / OFFICIAL_CONTRACTS_UNREGISTERED / RELEASE_BLOCKED**。

> 后续仅文档/证据更新见[生产只读续核验](release-readback-20261017.md)：已核对生产3216fd9、437条陈旧数据及历史/地区差异；get_project现已成功、日志API按Hobby分类，Cron/Queue/canonical仍阻断。以下“本轮未重查生产”指本实现补丁阶段；164项仍绑定c0d0215，本次只读续核验未改产品或重跑测试。

> 最新[四页受限取证](official-html-20261017.md)已取得本地原文，确认本实现对GB2312及两院真实列表结构仍有缺口，首页14条intent亦超出3条上限；单页不足30日，分页未读。下列“原文缺失”是实现补丁时历史，不再代表当前；注册表仍为空、没有激活或新增产品修复。

分支与草稿：`fix/twice-daily-source-parity-20261017`、PR78，叠加PR75。起点为`17ed8615328721946a5b353341190b4fcf27d82a`；本次集中保存后的精确HEAD须从远端读回，不能继承该起点或祖先CI/发布批准。PR75保持`a2131e4…`不变。

## 本轮实现

- 新增`web/collector_official_transport.py`：保留三源既有host/index，拒绝HTTP、跨源host、凭据、查询参数、未知路由、无效日期及未验证分页路径；重定向每个请求总计最多3次且逐跳检查。只取公开HTML、限制响应1MiB、明确字符集/内容类型，TLS证书错误不作瞬态重试。
- 一个请求在原函数内的独立短生命周期Python子进程执行，父进程等待同一绝对deadline，超时kill并限时回收；子进程自身也设退出闹钟，闹钟不影响父handler或同实例其他请求。没有新服务、容器、数据库、持久进程或付费资源，没有切换运行时。新增两个root helper文件用于隔离传输和结构核验，不改六个parser。
- 每请求最多20秒，source session在首次索引之前建立240秒总预算；索引、详情、最多2次总尝试、至少3秒请求间隔共享该deadline。进程创建返回后检查其耗时，清理最多额外2秒；不能清理时报告失败，不声称停止成功，也不回退到不可取消线程。子进程不继承应用token/DB环境，仅继承必要PATH/语言/TLS信任路径。
- `collector_runtime._prepare_official_source_refresh`可接收已有session的`work_deadline`，取更早的deadline，不在取完索引后重置240秒。该核心仍接受测试reader，不声称任何任意回调都可取消；真实调用方须使用已验证的传输和共享预算。
- 新增`web/collector_official_index.py`：只检查明确列表容器中的公告，排除侧栏，要求列表唯一、结构完整、stable identity不重复、日期倒序，并到达窗口起点。没有下一页链接不等于档案结束；空表、未知结构、乱序、未来日期或短窗口阻断。返回的scoped HTML只含已检查列表锚点，防止原页面侧栏再次被discovery混入。
- **官方结构注册表为空**。生产核验入口先要求代码审查后固定的来源结构及已保存HTML的安全路径、URL、时间与hash；没有注册就拒绝，不将测试构造的结构/boolean或hash当官方证明。当前仅单页检查，不猜分页、不拼URL；一页不足30日须先取得实际分页证据再限定实现。

**三个source仍未注册到STAGE_ORDER或旧incremental allowlist，仍22stage。** 本轮不升级history-only、partial、AI限制或coverage.complete，不重写canonical，不宣称两次搜索恢复。

## 验证与证据

运行：`python docs/ops/evidence/source-transport-index-20261017/verify_focused.py`。

本轮新增32项（transport 19、index 13）＋既有相关132项，共**164项PASS**。主进程阻断socket连接；子进程测试只使用stubbed DNS/响应或本地闹钟，不调用医院HTTP。真实本地子进程进入模拟DNS或正文read后先输出进入标记，父进程在约1秒timeout下终止并回收；测试同时确认进入标记、异常deadline和子进程已退出，避免只因启动慢就假称覆盖了阻塞阶段。

覆盖：网络/永久错误分类、最大重试与间隔、跨域/降级/循环重定向、响应大小/编码、子进程启动耗时、取消/清理失败、凭据环境不继承、继承索引deadline、侧栏旧链接、重复身份/容器、空表/缺结构、窗口不足、scoped HTML与原始hash绑定、mock窗口接入既有核心。首次索引测试有一项异常分类不一致：外链被拒绝但抛transport异常；现统一为结构未知，未放宽URL/结构检查。

[focused.log](evidence/source-transport-index-20261017/focused.log)及[manifest.json](evidence/source-transport-index-20261017/manifest.json)保存模块计数和文件hash。上轮132项证据仍绑定17ed861，未冒充本轮完整验证；没有重跑879历史矩阵。新HEAD完整Verify与独立审查尚未完成，本地164项不是远端CI。

## 未通过项与最小补证

1. **官方原始HTML缺失**：工作区及既有三份checkout未找到两院官方索引捕获，也未找到9/28调研、9/30数据安全正文原始HTML。需要已有存档位置：两个索引各自实际URL、采集时间、原始HTML及真实分页链接/页面；两篇正文同样注明来源与时间。UTF-8保存/转码必须可追溯，不能把构造fixture标成官方抓取。没有资料时保持注册表为空，不新抓取、不猜selector或分页。
2. **结构与窗口仍只离线证明**：测试registry注入与临时synthetic文件不是官方注册；hash只是内容绑定，不认证来源。现有单页倒序列表规则能否匹配真实医院页面、是否需要分页，必须由存档/审查确定。实际暂停缺口和canonical/baseline完整恢复仍单独阻断。
3. **目标平台未验收**：技能确认Python运行时/300秒边界，不能证明本项目当前部署的子进程支持、文件打包和清理行为。本地退出/回收通过不等于Vercel生效。Popen创建/OS调度及清理失败仍按失败处理；不能许诺任意宿主/不可中断系统调用都精确在20秒结束。不创建Preview或部署来补证，也不改架构/升级资源绕过。未来获准的受控部署需先核验helper打包、无网络的本地worker启动/退出及清理，再允许真实周期。
4. **正式接线待完成**：没有生产driver将registered contract、session、scoped HTML和core串起来；25stage必需门禁、准确源级history-only升级、完整新产品验证/独立审查仍待完成。不能将“取页模块存在”当自动刷新已恢复。
5. **线上发布门禁不变**：实际套餐、Cron启停、消费者identity/cap、各部署积压/在途/延迟、完整canonical、旧分区隔离和有效停止/回退仍未补齐。本轮未重查生产，不用旧报告状态代表今天。alias/rollback不停止Queue投递；若只有删除方式，仍须另获仅本次新失败部署的明确授权，不能删除旧生产/回退目标。

## 保存边界与下一步

集中推送同一草稿PR78，分支`deploymentEnabled=false`、保存commit使用`[skip ci]`；不改Cron/Queue/Secrets/域名/账户/安全设置，不合并、不部署/Preview、不启停consumer、不receive/ACK/purge、不删除部署、不触发真实采集/模型或付费升级。

**下一步**：读取用户已有官方HTML存档，核对列表结构和实际分页，注册经过审查的来源contract，再连接session/scoped window/core及三个必需stage；之后做25stage发布回归、完整新产品验证和独立审查。建议 **GPT-6.1-sol · xhigh**。没有存档时准确保留阻断，不能重复构造mock来替代官方证据。
