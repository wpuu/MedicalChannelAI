# CCGP 修复代码 Preview 部署与只读验收

2026-11-06（北京时间）。已把最新来源提交 `82cc43f06c774969eab0fe44f0afc012f37cadac` 部署到现有项目的Preview，内含应用修复 `795ef5efa30b61dd47352c4fb888b02488f16855`。部署 `dpl_8Jhc4imHEd6ndBUoth5xBVTrAyL1` READY，[Preview URL](https://medicalchannelai-b5vc26me3-rerisse7-1717s-projects.vercel.app)。沿用分支专属d周期/数据库，未新建环境或修改定时计划。定向API、数据一致性及页面验收通过，未触发采集或回补。

## 最新任务与已有工作核对

开始时仓库HEAD为82cc43f且干净，远端一致，main仍3216fd9。四类修复及945项Python/完整构建、冻结模板10/10和原CLI复现3/3已完成，本轮只核对其代码绑定和证据，没有重写解析或重复跑同一完整测试。当前代理列表只有根代理，无其他代理在途；分支部署列表无正在构建的旧任务，无附着终端任务或本对话PR。

本轮承接已经授权的“仅Preview部署与定向读回”。Vercel现有项目 `prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM`、分支 `codex/p0-reliability-contracts`、周期 `mcai-p0-20261106-d`、数据库及受限角色 `mcai_p0_epoch_20261106d` 均复用。分支专属Preview变量元数据/非秘密周期值核对一致，未解密数据库或发布/触发凭据，未修改环境变量、Cron、自动任务或项目保护策略。

## 部署结果与验证

- Target：Preview（平台响应target=null的默认Preview语义；非Production）。Framework：Vite。
- 来源提交82cc43f，应用代码与已验证795ef5e一致；19:25:24开始构建，19:26:21 READY，构建56.306秒。
- `/api/status` 返回200、commit=82cc43f、preview_epoch=d、snapshot.source_mode=DATABASE；`public-snapshot?fresh=…`、普通GET及collector-status均200。所有验收HTTP仅GET。
- collector-status显示d周期、active_cycle=null、已完成阶段0，active_incremental=null、incremental链=null。没有启动或重复触发业务任务，没有把已有来源扫描算作本轮新采集。
- 部署前Neon只读完整payload、部署后SQL元数据、fresh GET、普通GET和普通浏览器GET的规范化SHA256均为 `85a1768f1705a3f4bd403ec0b70f80292ac24948806546d4c9be1d690576fead`。SQL逻辑时钟仍 `2026-11-06 07:00:46.604901+00`，与payload精确到微秒，未改16条公开事实或source_health/扫描时钟。
- 页面6项定向验收：准确代码/数据库绑定；浏览器原始数据16条及目标10项产品/数量一致；ALL行动池15/15经真实报名窗口核对；详情10项可见且无资格误项；390px无横向溢出；无页面异常或意外写请求。最终检查2次自动cache_only请求、首次部分检查另1次均由护栏阻断，合计3次，没有实际模型请求。

浏览器工具ego-lite在此Linux不可用，未安装新软件或新建环境，使用已有Chromium/Playwright独立测试上下文。测试先固定ALL地区并设导航/总体绝对截止；访问凭据不进入截图、日志或提交。普通GET读取的是现有真实数据库快照，不是注入的mock页面或QA快照。

## 16条数据库与15条页面的解释

页面观察时点为北京时间19:29。`tjzyefy_20261104_030202660`（院内调研2026年32号—溶栓专用称重床等设备）报名截止为今天16:00，bid_deadline=null，research_event_at=null。它按既有前端 `applyRuntimeActionability` 规则退出当前可行动列表。其余15条项目名全部在页面，关闭项目不在页面，地区仍ALL；这是正常报名窗口关闭，**不是现场调研事件时间关闭，也不是市县漏显**。

第一次脚本固定等待旧的16/16而超时，保留为未通过的部分报告。随后一次短读回捕获实际15/15、页面文字/截图，再以冻结公开截止字段独立核对合同预期，未改应用或事实。诊断时“现场活动时间已到”的初步猜测被字段核对排除，未当作结论或伪造该字段。最终依据是报名16:00结束且没有后续投标窗口，不能因旧测试分母而强行恢复过期条目。

首次创建部署请求因API不接受字面target=preview返回400，未创建部署；按平台默认Preview格式修正一次后成功。没有重复创建有效部署，也没有改变项目保护设置。现有日志工具返回100条构建事件及Vite/Deployment completed；945项及完整本地构建沿用未改变代码的上轮证据，不冒称本轮另跑了945项云端运行测试。

## 权限、未完成与下一轮

短时任务分享访问已撤销，私有访问文件已删除，精确secret扫描通过。北京时间19:31只读复核Production仍 `dpl_4LPKoTdusrvbExXuzbMKtnyiT86C` / `3216fd940dabfa7714383b6436908f9b72ff8a9c` READY，SSO `all_except_custom_domains` 未变。原工作树/main未修改；未合并、提升Production或改域名/DNS/EdgeOne。

本轮只完成部署与服务读回，不是新解析器的原生采集、完整Queue、历史canonical迁移、事件新产物、来源恢复、模型或商业验收。来源健康仍承接旧快照8/14时钟；d仍是公开快照承接，不等于c的canonical运行状态迁移。两条历史差异提案尚未应用，原子提交、并发版本保护、执行回滚及5条云端试回补均未实施，`production_ready=false`。

下一轮完整任务见[next-task.md](next-task.md)：复用现有审查工具补齐最多5条、只读输入、可回放的dry-run变更清单，不再重复部署同一版本。[工作约定](working-protocol.md)已按用户最新指令更新：当前工具没有真正的底部提示词按钮接口，不再用问答选项冒充。下一轮推荐GPT-6.1 Sol高（high），实际运行模型/思考等级未核实。

本轮19:23:14开始，前台截止19:43:14；定向验收在截止前完成，未启动后台观察器。证据见[冻结清单](validation/ccgp-preview-readback-2026-11-06/manifest.json)。
