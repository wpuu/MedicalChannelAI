# MedicalChannelAI current state

Updated: 2026-10-17. 本轮在隔离分支实现三源离线准备/提交核心；下列10月3日线上观测仍是历史证据，不冒充今日生产状态。

最新补丁：[请求deadline与索引保护](../ops/source-transport-index-20261017.md)已实现，32项新增＋132项相关共164项离线通过。同函数内可终止取页、共享索引/详情预算及指定列表窗口检查有本地证据；官方结构注册表仍为空，实际HTML/分页、Vercel打包/子进程行为和正式25stage接线未验证。以下132项说明保留为上轮历史；当前仍22stage/history-only/partial，不能称生产已修复。下一步需已有官方HTML存档，建议GPT-6.1-sol · xhigh，不新抓取或部署补证。

MedicalChannelAI 是天津起步的医疗器械、IVD、耗材公开情报和单用户销售助手。公共事实必须有官方证据；模型不创造事实。客户私有资源与公共情报分离，关注医院不代表关系分。`production_ready=false`。

## 10月17日离线实现进展

- 实现分支`fix/twice-daily-source-parity-20261017`从PR75文档HEAD`a2131e4733939e07b9531ea4626c9378e0826953`分出，禁用部署；PR75原候选保持不变。此实现已修改runtime，不能再称所有产品blob与8b4b749相同，也不能继承祖先879项CI。
- [三源离线核心](../ops/source-parity-offline-20261017.md)已完成：复用parser/stable ID及独立v2 key，准备时无写入，周期/base绑定提交、无主动TTL、历史保留和失败保护；25项新增＋107项相关检查共132项在禁止外连条件下通过。
- **尚未激活**：真实请求deadline与索引覆盖没有生产实现，三源未加入调度/分派，当前仍22stage、history-only/partial及AI限制。mock样本不是真实官方HTML或运行态成功证据；没有新HEAD完整CI或独立审查完成声明。
- 下一步实现并验证请求总时限和可追溯索引覆盖，之后才注册三个必需stage及准确coverage，再进行必要完整验证/独立审查。建议GPT-6.1-sol使用xhigh；本轮不部署、不采集、不调用模型，线上门禁不变。

## 候选与实际生产

- 基础候选：`fix/tjmugh-verification-20261002`，草稿 [PR #75](https://github.com/wpuu/MedicalChannelAI/pull/75)，未合并。设计阶段从`ca91df269636d8604814d2e744d12587b8fadc82`保存为`a2131e4733939e07b9531ea4626c9378e0826953`，基础候选产品blob仍绑定8b4b749的既有验证。本次实现另开上述分支，不覆盖PR75；最终精确实现HEAD见新草稿读回，旧提交批准不沿用。
- GitHub main读回为`3216fd940dabfa7714383b6436908f9b72ff8a9c`。10月7日新增的是4份行动雷达任务/策略文档，不是runtime修复；当前完整产品集成仍以PR75为唯一基线，不覆盖为旧main代码。
- 分支 `deploymentEnabled=false`，本轮未部署/生成 Preview、未恢复 Cron/消费者、未清队列、未真实采集或调用模型。
- 10月3日Vercel历史只读生产：`62299590dd3898e040ccc9db5fda1298d4509d51`，READY 部署 `dpl_DW5wrMzvVXS7TLmbqUL1vSfcyuh1`。数据库数据版本 `2026-10-02T14:19:15.713282+08:00`，441 条。本轮未重查Vercel；这不是10月17日实际生产或候选上线证明。
- 当前目标仅一个人使用：每天早间和午间各一次，候选北京时间 08:20 / 12:20，两条独立每日 Cron，Hobby 小时级精度，不升级套餐。
- 2026-10-03 13:02Z生产status为DATABASE、STALE/degraded（旧数据版本不变）；此前healthy结果不能当当前状态。13:03Z公开441的地区字段/rank与生产发布文件一致，4条历史intent仍保留；这不是完整RuntimeCache恢复。
- 两条 GitHub 采集入口此前只读回查为 `disabled_manually`；Vercel Cron、消费者、积压与在途任务状态尚未核验。项目详情工具参数契约冲突不代表整个连接不可用；此前团队、项目列表、部署与日志查询成功。实际套餐未知。
- 21:46北京时间续核验开始于文档HEAD `a503eed41ac1cb4ec0acddd3be3b44fd5cceb649`；main/生产未变。GitHub branch GET已读回main保护停用、必需检查off/空，rulesets为空，当前合并规则缺项解除；详细保护接口仍403。此次仅补存文档证据，最终文档HEAD见PR回读，旧HEAD批准不沿用。

## 候选验证与限制

原patch/85项日志缺失是历史记录，不计已读取。冻结产品8b4b749的既有 [Verify37117043888 SUCCESS](https://github.com/wpuu/MedicalChannelAI/actions/runs/37117043888) 记录879项Python及完整Node/prebuild/TypeScript/Vite，live探测skipped；已有定向98项与续办独立竞态审查通过。此前设计阶段只读回CI元数据和5份冻结哈希，历史日志接口未返回正文，不声称重新提取879项日志。本次实现新增25项与相关107项共132项离线通过；没有重跑879项或投影历史矩阵，不把父候选完整CI当实现分支CI。更早840/865/870/875和浏览器证据只适用于各自旧HEAD。

候选实现周期独立、同周期幂等、旧周期写入 fence；禁用自动 15 分钟增量链；保留所有配置刷新stage成功门禁、准确覆盖范围、失败旧数据、canonical/缓存与 AI 版本保护。长暂停后缺失 canonical 默认阻断旧种子初始化。生产提交的911条live canonical全部schema验证通过，经静态发布流程的market补全、分区构建及combine复排，在真实旧版本时间上复建的441条卡片与DATABASE读回逐字段一致；这只是历史备份候选，不证明生产缓存已恢复。审查发现的三个既有来源8条历史（含4条公开intent）读取缺口，已用独立v2历史缓存严格读取修正；不从Git/seed自动初始化，不新增采集stage。scheduled worker复用静态分区/组合流程，441条离线投影逐字段相同，修正market/rank差异。三个历史来源没有新监控，coverage明确partial，保留页面提示、AI限制及durable基线比对；不能宣称全量覆盖时间已推进。实际canonical缓存恢复、跨分片完整性、旧队列隔离及两周期成功仍未线上证明。Runtime Cache 无 CAS，发布必须排除旧消费者和旧在途写入，不能把代码 fence 当作分布式原子锁。

## 剩余工作与发布边界

10月17日已保存[三源双时段集成设计](../tasks/MED_ACTION_P0_001_TWICE_DAILY_INTEGRATION_2026-10-17.md)，已有离线核心，但**正式接线尚未实现**。三源拟作为每周期三个必需Queue stage；不恢复15分钟链、不从repo/seed自动bootstrap。新增阶段从22变25是设计期望，不是当前产品事实。当前三源仍history-only、coverage partial及AI限制保持；预算、官方fixture、缺口覆盖和完整新产品HEAD验证仍待完成。10月7日审计关于旧生产15分钟链运行是当日观测，不能把候选禁用链的代码当作线上已停。

下一步：在已禁用部署的实现分支验证实际请求总时限、索引完整覆盖及fixture来源，随后完成25stage分派、必需列表与发布契约。建议GPT-6.1-sol使用xhigh处理预算与周期/缓存边界，明确的adapter映射可用high。未完成前不激活三源，不把本地聚焦验证当完整新产品CI。

**当前发布门禁BLOCKED。** 现有连接未暴露实际plan/Cron/Queue/完整RuntimeCache库存，项目详情有schema冲突；不索要新token。官方Queue的deployment分区意味着alias回退不停止旧消费，原“暂停consumer/新worker处理旧积压”操作假设已纠正，完整计划见 [只读发布前核验](../ops/release-preflight-20261003.md)。GitHub main详细保护接口仍403，但受支持的branch GET已确认当前protected=false、保护停用且必需检查空，rulesets也为空；当前规则读回通过，执行前再核对，不修改保护或把祖先CI冒充新HEADCI。需既有账户控制面/人工读回剩余缺项，并确认有效停投递及仅删除本次失败部署的审批边界；建立完整canonical恢复条件；满足门禁后由用户批准一次指定 HEAD 合并＋Production 发布，再受控恢复单一当前周期；该周期验收通过后按批准范围启用两条每日Cron，观察另一时段自然触发，不额外手动补采。每天两次恢复成功必须有两个独立周期完成全部配置刷新stage、partial范围准确及页面版本一致的证据。本轮不合并、不发布，不能宣称搜索已经恢复。

天津 403 与国内域名访问单独记录，不新增地区、不换架构或修改 DNS 绕过；它们不阻塞离线候选整理。发布前后、回退后检查以及失败恢复按 [受控恢复清单](../ops/twice-daily-release-20261003.md) 执行。旧 PR #6、581/558 项、2026-09-04 主线与部署状态不再代表当前项目。
