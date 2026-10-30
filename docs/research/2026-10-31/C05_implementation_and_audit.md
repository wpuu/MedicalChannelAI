# MED-ACTION-20261031/C05｜官方更正、长期失败审计和自然Cron发布门槛

北京时间2026-10-31
工作分支：fix/c05-durable-failure-audit-20261031
起点：C04分支 fix/c04-source-proof-20261031，起点提交815489fb15425137c0ae09850ff0251700764407
精确已通过CI的源码提交：740193927f00aeda924afc131e9f05bea007b5bd
最终裁决：C05_ISOLATED_TEST_PASS / OFFICIAL_CORRECTION_UNVERIFIED / PRODUCTION_NOT_VERIFIED / RELEASE_HOLD

## 一、先核实的现状

- main HEAD仍为3216fd940dabfa7714383b6436908f9b72ff8a9c（2026-10-07）。
- PR #75 Draft/open，HEAD a2131e4733939e07b9531ea4626c9378e0826953。
- PR #78 Draft/open，HEAD d158f8648db17b904300671b0f1ccbae795c324c。
- C04曾完成20项证明相关测试和986项Python全量测试及完整npm build；其证据作为本轮基线保留。
- 当前生产部署仍属于旧main，不包含本轮独立审计，也未正式启用PR78计划的双时段/25-stage及三源完整分页。

## 二、A939/A944官方更正证据

### A-939，第五批检验科设备

2026-10-27原始官方公告：
https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm

当前可从该官页验证的旧正文：
- 四个采购包，共8种明确列出设备；
- 预算509.19万元，合计最高限价428.19万元；
- 原稿获取文件截止11/03 16:00，投标/开标11/17 09:30（均北京时间）；不接受进口产品；
- 附有项目需求书.docx，主公告使用“等”，并非完整BOM。

2026-10-30通过第三方目录确认出现“第五批检验科设备采购项目更正公告”标题：
https://m.chinabidding.cn/xdwzb_3/zbbx/

本轮按项目编号/医院/官方域名/更正公告进行独立搜索：
- 没有检索到可以直接阅读的官方更正全文、官方附件原件；
- 原需求书下载官方链接
  https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=yUJ.S_Ra1oE%2A&method=downEnId
  仍未获得可哈希的真实DOCX字节；网页工具返回CACHE_MISS；
- C02前次官方raw GET为HTTP403，本轮不绕过、不增加代理或伪造原始HTML；
- 因而10/30更正的包、技术规格、厂家资质、获取文件截止、开标日期是否变更全部UNKNOWN。
- 禁止根据10/27旧版条件向客户宣称“最新可投”。

### A-944，第四批检验科设备

2026-10-27原始官页：
https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27572316.htm

2026-10-30第三方转引：
https://www.czhaobiao.com/zb-196981466-3.html

转引称“采购文件/项目需求书发生变更，具体见标色附件，其余内容不变”。本轮未得到官方更正文档和附件的真实字节、SHA256，因此连“其余不变”也不能无保留升级成官方已核实事实。

A-939和A-944必须作为独立项目保留独立版本；不能从A-944的转引推断A-939同样只修改技术参数。真实版本对照暂只保留UNKNOWN及来源等级，不伪造任何包级差异。

## 三、C05真正新增的持久失败审计

### 3.1 方案与代码

C04提供可选的Runtime Cache执行事件+成功快照内部witness，但Cache有TTL和淘汰，失败周期不会产生新成功快照。这是过去7天自然执行无法取证的一项缺口。

C05在隔离分支新增专门的失败事件日志实现：

- web/api/_collectorFailureAudit.js：单独的Postgres追加式public_collector_audit_events表，event_id为确定性SHA256主键、周期/阶段/失败类型/受约束错误码/UTC时点。只接收严格5字段，不能存token、客户资料、原始网页或自由文本错误。写入采用幂等ON CONFLICT DO NOTHING，再从数据库读取同一行严格验证。只读GET限制最近1至7天且上限250行。
- web/api/_collectorAuditHandler.js：独立COLLECTOR_AUDIT_TOKEN（不少于32字符）鉴权、timing-safe比较，COLLECTOR_AUDIT_ENABLED显式true且有DATABASE_URL时才开放；默认返回503未配置，未授权返回401。不给出数据库异常或含凭证细节。
- web/api/public-snapshot.js：仅新增早期分流；原正常GET/PUT发布代码仍按原逻辑执行。受保护子路由走审计处理器。
- web/vercel.json：把 /api/collector-audit 重写到既有/public-snapshot函数并带route=collector-audit，不增加Hobby Function数量；本分支仍显式关闭Preview自动部署。
- web/collector_durable_audit.py：Python单次HTTPS POST（固定自有官方应用域名、超时2秒、无重试）、仅在独立audit token与enabled已设置时调用；失败不泄密、不改变原有采集异常处理。
- web/api/collector-run.py：真实Queue启动报错后尝试记录CRON_QUEUE_FAILED，仍重抛原始异常；队列幂等冲突按旧逻辑。
- web/collector_queue.py：严格租约验证后的stage终止失败或重试失败可记录STAGE_TERMINAL_FAILURE/STAGE_RETRY_ERROR；不能记录无租约消息“成功”。
- web/scripts/check-publish-preflight.mjs：离线临时复制现有公共快照端点时，单独stub未经授权的审计子路由；原有真实发布验证未削弱。
- web/scripts/check-collector-failure-audit.mjs：白名单校验、时间、周期、错误码、防敏感字段、独立鉴权、默认禁用、路由复用、模拟DB幂等和读回失败。
- web/pipeline/tests/test_collector_durable_audit_c05.py：无凭据不访问网络、2秒限时、脱敏、错误后无重试、原始Queue异常不被掩盖、终止失败不会产生C04成功快照回执。
- .github/workflows/c05-durable-audit-verify.yml：隔离GitHub Actions，Python、Node与完整Vite构建，全部无生产环境访问和部署。

### 3.2 Hobby预算真实阻塞已修复

最初直接新增 web/api/collector-audit.js 会让Serverless Function由11个变为12个，触发仓库现有“预留一个Hobby函数槽位”的限制；没有修改限制或加钱。

现在通过受保护子路由复用 web/api/public-snapshot.js 函数，删掉单独函数入口，恢复11个函数及一个预留槽位；独立audit token仍与较高权限的快照发布token分开。

### 3.3 真实测试

隔离CI run：
https://github.com/wpuu/MedicalChannelAI/actions/runs/41097695830

精确测试代码SHA：740193927f00aeda924afc131e9f05bea007b5bd
最终结论：SUCCESS
- C05专项7项 PASS；
- C04既有20项 PASS；
- 旧双时段调度37项 PASS；
- 旧PR78来源状态25项 PASS；
- Python全量993项 PASS，prebuild内重复993项 PASS；
- Node独立安全合约测试PASS（追加幂等、读回失败、无鉴权/默认禁用）；
- 原公开快照Preflight/AI Boundary测试PASS；
- TypeScript PASS、Vite PASS（2.52秒）。

以上是模拟DB与GitHub Hosted Runner测试，不是Neon生产表实写/实读；不得宣传永久审计已在生产启用。

### 3.4 仍需要生产阶段的明确授权与真实验证

本轮没有设置COLLECTOR_AUDIT_ENABLED、没有读取/创建COLLECTOR_AUDIT_TOKEN，没有连接或迁移生产Neon、没有触发真实Cron或Queue、没有Preview/Production部署。

新增失败日志在未来明确授权发布并配置环境之前完全关闭；数据库不可用时也只能返回/记录UNKNOWN，不能因为“错误日志没记录”就称没有失败。

本方案复用现有Postgres数据库但新增独立审计表；后续正式启用前应核查实际迁移权限、数据库连接数、表膨胀与历史保留政策，避免Hobby免费层意外超额。

## 四、七天自然Cron严格验收门槛

独立文件：
docs/research/2026-10-31/C05_seven_day_natural_cron_protocol.md

概要：
- 目前实际生产只一条每天08:20（北京时间）Cron，未来PR75/78双时段不可以当作已运行；
- 真正上线后先完成旧Queue in-flight/delayed分区检查、原始官方source及PR78完整30日窗口验收；
- 若单时段连续7天需7次平台证明的自然触发、有效Queue消费、完整窗口、官方详情、Canonical与持久数据库+公开读回；若双时段需14次；
- 不能以快照当天更新、手工执行或其它AI刷新抵自然运行；
- HTTP403、官方附件缺失、任一完整源未验证、持久审计DB故障、读回冲突与无凭证，都不允许计为PASS；
- 失败周期长期记录由C05独立表负责，但本轮未启用；
- 只有来源原件与七日自动链可核之后才允许真实客户付费Pilot。

## 五、最新生产只读状态的证据边界

C05没有修改main与Production。

已确认生产署名是旧main SHA3216fd9，部署dpl_4LPKoTdusrvbExXuzbMKtnyiT86C，PR75/78仍Draft。

此前C02在2026-10-30成功读到：
- DATABASE公开快照 as_of=2026-10-28T08:27:29.111217+08:00；
- freshness=STALE，degraded=true，pool65；
- collector-status v2 0/22、chain null；
- pipeline-health=HTTP503。

C05尝试最新公开状态API仍出现网页工具不可访问/缓存问题，未得到更新到10月31日的可靠freshness回执。不能基于最近30分钟无Collector日志推断自动Cron一定失败，因为彼时不在自然触发窗口。也不能仅凭Vercel Errors列表没有错误推断每天成功。

**当前真实生产七日成功证据=0天，不符合“每日自动监控已恢复”。**

## 六、C05裁决

工程级：
- **C05_ISOLATED_FULL_BUILD_PASS**。
- 有专属Token+SQL审计表+端点+Python侧车的可测试实现，默认关闭、现有Hobby函数数量不增加。
- 不动PR78原来源完整窗口、最多3条分批、失败不部分发布、不清租约与生产历史。

商业/上线级：
- **RELEASE_HOLD**。
- 更正原件与真实官方DOM未验收；
- 实际生产自然Cron、Queue、来源完整窗口和Durable快照连续7日未取证；
- 独立持久审计尚未启用，不具备真实生产错误历史；
- 对客户的真实价值和付款尚未验证。

下一步MED-ACTION-20261031/C06：
先继续合法取官方更正DOCX原件并做SHA与逐包差异；其次在隔离环境为新增审计DDL提供迁移/容量预检和受信七日验收脚本，审查PR78 Cursor/Manifest全窗口；若源和所有回归可验证，之后才另行申请生产Canary和7日自然运行授权。任何未达门槛不能自动部署或借手工补数据宣称完成。
