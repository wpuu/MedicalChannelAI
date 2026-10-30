# MED-ACTION-20261030/C03｜AI 测试时钟纠偏、官方原始资料与采集链验收

- 记录日期：2026-10-31（北京时间，接续10月30日 C03 任务）
- 项目：MedicalChannelAI
- 基于 C02 commit：8ed6bd0917f76b41ae48fba22b326ba1aa0be01b
- 本轮候选分支：fix/c03-ai-clock-official-provenance-20261031
- 生产主分支仍为：3216fd940dabfa7714383b6436908f9b72ff8a9c
- C03 裁决：FULL_BUILD_PASS / ORIGINAL_OFFICIAL_HTML_NOT_VERIFIED / PRODUCTION_COLLECTOR_NOT_VERIFIED / RELEASE_HOLD
- 不变更 main、PR75、PR78、Production、Cron、Queue、数据、密钥，不建立付费试用。

## 一、C03-A：真实官方原文与附件核查

目标公告：天津市第三中心医院东丽院区第五批检验科设备采购，项目编号 XCSD-2026-A-939。

官方10月27日公告：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm

公开网页正文可以通过中国政府采购网公开查看，确认：
- 第1包：全自动生殖道分泌物分析仪、血气分析仪；预算248万，限价227万；
- 第2包：全自动化学发光免疫分析仪、血液分析仪；预算104.99万，限价59.99万；
- 第3包：全自动尿液分析流水线、微生物样本前处理系统；预算95万，限价80万；
- 第4包：生化培养箱、二氧化碳温箱；预算61.2万，限价61.2万；
- 合计预算509.19万元，最高限价428.19万元；不接受进口产品；另有官方需求书 DOCX，主公告设备名称带“等”，不完整。
- 这些只是2026-10-27版公告可核实的事实，不代表2026-10-30更正后的最新版。

原始字节验收仍未得到：
1. 旧 C02 一次 GitHub-hosted GET 返回 HTTP403，未绕过；原始 HTML 字节数、SHA256均无。
2. 2026-10-31 检查官方网站所列项目需求书下载入口，公开链接为：
   https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=yUJ.S_Ra1oE%2A&method=downEnId
   网页下载端点返回 cache miss，未得到原始 DOCX 文件，未读取任何附件字节。
3. 此次没有使用代理、登录替身、验证码绕过或绕开403；没有将公开网页正文重建HTML冒充原始网页。
4. 因此 C02 的9/10项离线包级测试仍是由官方文字构造的 OFFLINE_SYNTHETIC_HTML，而不是官方原始 DOM 的真实回放。
5. 原始 HTML/正式附件验收保持 BLOCKED，不能宣称真实原始页面包级解析 100%。

### 2026-10-30 最新更正风险

发现两个与此同院采购有关的第三方索引/转引，尚未核到更正后的正式官方内容：

- XCSD-2026-A-939（第五批）：2026-10-30第三方索引出现“第五批检验科设备采购项目更正公告”。
  线索：https://m.chinabidding.cn/xdwzb_3/zbbx/
- XCSD-2026-A-944（第四批）：2026-10-30建筑市场网转引的更正公告提及“采购文件、项目需求书发生变更，具体见附件标注颜色部分，其余内容不变”。
  转引：https://www.czhaobiao.com/zb-196981466-3.html

上述两项不得解释为第五批更正内容必然与第四批相同。第五批更正事项、有效截止日、采购包明细是否变化，必须拿到该批正式更正全文才能判断。

C03 的数据可靠性决策：
- 把10月27日的四包八件设备视为“历史公告版本的可读正文事实”，不是截至10月31日已确认的最新招标条件；
- 对商业行动卡应标“更正内容待官方核实”，不直接告诉客户按旧需求报名；
- 后续有更正公告时，官方更正正文、版本序列和变动字段应高于旧单一公告缓存；
- 不允许用第三方索引强行覆盖官方日期/预算/资格事实。

## 二、C03-B：旧 AI 503/409 构建失败的准确原因及修复

历史基线：PR78的 npm run build 会在 web/scripts/check-ai-boundary.mjs 报：
AI_BOUNDARY_UNCONFIGURED: expected 503, got 409。

代码审查：
- 原测试把仓库中历史 verified snapshot 的机会 ID 用作未配置模型测试；
- runtimeWindowStatus 使用执行时的真实时间；
- 旧项目在2026-10月已过报名/投标有效窗口时，AI核心正确地首先返回 HTTP409/OPPORTUNITY_WINDOW_CLOSED，避免分析已经终止的商机；
- 所以测试期望的 HTTP503/AI_NOT_CONFIGURED 未必能够执行到；
- 真实API仍应以409拒绝过期项目，绝不能把生产代码改为先检查 Key 再允许分析过期机会。

本轮实际修改只有 web/scripts/check-ai-boundary.mjs：
1. 测试时钟以已验证历史 snapshot 的 snapshot_as_of 为准；
2. 从卡片/机会池中选取在该时点不是 CLOSED 的已验证项目；
3. 在测试程序内部临时冻结 global Date 的当前时间，旧系统的HTTP503、429、模型重试等用例仍测试原本的行为；
4. 在 finally 中恢复原始 global Date，避免其他脚本受到污染；
5. 另外使用真正的 Date.now 直接确认一条明确过期的项目仍为 CLOSED；
6. 原有精确日期、date-only以及2000年已过期项目必须返回409的断言保留；
7. 未修改生产 handler、runtimeWindowStatus、源采集器或任何过期项目安全规则。

### 真实 GitHub Actions 验收

隔离CI run：
https://github.com/wpuu/MedicalChannelAI/actions/runs/41087486515

准确 SHA：3ef18842c199e141d010bdc77c3e6cac56e40063

结果：SUCCESS
- C02 包级定向回归：10 tests PASS；
- Python 完整流水线：966 tests PASS；
- check-ai-boundary.mjs：PASS；
- npm run build 内再跑一次完整 966 tests，全部PASS；
- Prebuild verification：PASS；
- TypeScript：PASS；
- Vite：PASS（3.07秒，CI编译耗时）。

这证明“完整构建阻塞”在C03的隔离分支已解决，与C02相比有真实提升。不能把此CI成功直接推导为真实官方HTML通过或生产部署可用。

## 三、C03-C：Production Cron→Queue→Source→Snapshot 只读核验

### 线上真实发布身份

- Production deploy：dpl_4LPKoTdusrvbExXuzbMKtnyiT86C，READY；
- Production commit：3216fd940dabfa7714383b6436908f9b72ff8a9c；
- 区域：iad1；
- 本轮C03分支对应 Preview 部署数：0；
- PR75、PR78均仍 Draft/open，未合并。

### 实际已部署代码的调度定义

main 的 web/vercel.json 只有一条 Cron：
- 路径 /api/collector-run
- 时间 20 0 * * *（UTC）= 北京时间每天08:20；
- 启动队列topic medicalchannelai-refresh-v2；
- 依赖Vercel Queue consumer串行分阶段执行。
- PR75/PR78所讨论的每天08:20、12:20两条Cron并未部署到main；不能把PR的设计当生产当前能力。

这些是“部署源配置事实”，**不是 Cron 在某一天确实执行成功的证明**。

### 最后一个已经成功读取的线上快照证据

C02在2026-10-30核验过：
- /api/status：DATABASE snapshot=2026-10-28T08:27:29.111217+08:00；freshness=STALE；degraded=true；opportunity_pool=65；
- /api/collector-status：v2 state local_date/cycle_as_of/updated_at均为空；stage完成0/22；incremental chain null；各已列源 last_completed_scan 无证据；
- /api/pipeline-health：HTTP503。

这只能得出：当时可靠自动新鲜度未达到业务承诺，不能从数据库时间倒推是哪种发布来源。

C03 2026-10-31重新尝试读取时：
-公开状态API工具连接发生内部错误；web直接打开API亦不可用；
-因此**没有拿到较C02更晚的可靠实时快照**。绝不假装10月31日状态已核对。

### Vercel日志调查的具体限制

- 过去7日聚合Error列表返回“no runtime errors found”，不等于Cron已执行，因为没有成功/失败完整请求流证据；
- 过去7日历史单条日志的请求遭到Hobby计划日志保留/后端接口限制；
- 最近30分钟的collector查询没有日志，但查询时不在北京时间08:20计划窗口，不能据此证明服务不可用；
- Vercel工具无法提供当前Queue ready/in-flight/delayed及deployment-pinned消费者积压的完整安全审计；
- 故Cron的触发、Queue投递、Source扫描、canonical保存、durable snapshot读回证据均未通过核验；具体阻塞点 UNKNOWN。

### 正确的验收机制

后续应在隔离代码中设计耐久、最小、无敏感字段的自动化证据：
- cron_trigger_at、trigger_request_id；
- queue_send_accepted_at、queue_delivery_at；
- cycle_id与source_id；
- source_attempted_at、source_last_success_at、failure_code；
- canonical_write_version；
- durable_snapshot_hash/as_of/readback_at；
- 容错与版本门禁、源级STALE状态；
- 这些字段只记录生命周期和去敏的计数/摘要，不记录采购私有数据、凭证或URL凭证。

该机制在没有未来真实Production发布授权前只能离线设计/验证；不能在本轮手工触发刷新或修改主环境。

## 四、发布状态与 C04

本轮通过：
- C02包级离线回归保留；
- 历史AI时间边界问题解决；
- 完整CI和前端构建通过；
- 确认生产未改、C03无Preview；
- 识别了10/30更正公告的源版本风险。

本轮尚未通过：
- 原始官方HTML字节/附件验收；
- 2026-10-30第五批最新更正详情和原始附件逐条核实；
- PR75/PR78完整源窗口与Queue续批生产门禁；
- 连续7天真实自动采集与持久化快照读回；
- 有效Agnes相关性基准、真实客户付费。

**最终裁决：C03_ISOLATED_BUILD_PASS / RELEASE_HOLD。**

C04应当先获取并核对官方更正全文/附件和10/27原稿差异，再做真实DOM包级解析回放；并在隔离开发阶段补能审计生产自然Cron的耐久最小证据与测试，不触碰Prod。若官方文档仍不可读取，必须继续HOLD；不要用第三方转引或模型推断替代。
