# MED-ACTION-20261031/C05｜官方更正原件与自动采集发布前硬门禁

起点（必须读取）：
- docs/research/2026-10-31/C04_implementation_and_source_audit.md
- docs/research/2026-10-31/C04_validation_evidence.json
- docs/research/2026-10-31/C04_official_version_comparison.json
- fix/c04-source-proof-20261031（从 fix/c03 分支继承 C02包表与C03构建修复）
- PR75、PR78最新HEAD、main最新HEAD
当前状态：BUILD_PASS / SOURCE_UNVERIFIED / REAL_AUTOMATION_NOT_PROVEN / RELEASE_HOLD

## C05-A 官方更正文件原件与版本化闭环

项目分别处理：
1. XCSD-2026-A-939 第五批：
   - 原2026-10-27官页 https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm
   - 原需求书入口 https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=yUJ.S_Ra1oE%2A&method=downEnId
   - 2026-10-30仅第三方更正标题；必须优先找真正官方更正详情及修订的DOCX。
2. XCSD-2026-A-944 第四批：
   - 原官页 https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27572316.htm
   - 2026-10-30第三方转载提及有标色更正的项目需求书，具体参数未核。

完成条件：
- 不绕过登录/验证码/403，不猜隐藏附件URL，不从商业付费来源未经许可下载；
- 真实原始HTML/附件可取得时，保存原件 SHA256、合法来源、最终URL、时间、受控版本对照（单次页面和附件下载有体积上限；必要可让用户从官方页面自行提供附件）；
- 不可得时保留UNKNOWN，不用第三方条目改真实采购事实；
- 将10/27→10/30每包产品、参数、数量、预算、限价、供应资格、获取文件期限、投标期限逐项比对，改动字段与未披露字段分开；
- 对原有C02包级解析器用真实官方DOM而非合成fixture回放；真实DOM失败时仍不视为可生产。

## C05-B 长效失败审计与源级完整性

C04已解决代码中记录Cron接受/Queue分阶段/持久快照成功的可选witness，新增20项专门测试，全量986项过、完整build过，但Cache不是永久数据库。

下一步：
- 不覆盖既有C04证据与原始Queue权限；
- 设计独立、可查询、持久化的失败周期审计（只存最小状态码、周期标识、SHA、时间戳及版本，允许可靠读回和7天查询；不能误把成功无凭证当自然执行）；
- 对重投/重复消息、旧上午周期vs午间周期和deployment-pinned backlog逐项测试；
- C04已存在snapshot witness，评估能否从已有public_verified_snapshots记录中查询，而不增加新表；若数据库操作需要迁移，必须在隔离SQL审计并明确生产授权门槛；
- 证明一条source的完整索引窗口/分页及全部候选详情，不是只要运行成功就当源已完成；
- 按PR78政策：单批<=3详情、manifest完整、超时/中断不部分发布、异常不清ACTIVE、不基于旧快照回填、不会将伪造发布日期推进freshness。

## C05-C 自然Cron验收设计及发布门禁

- 核main实际生产Cron (当前一天一次 08:20 北京时间)，PR75/78是两个周期但均未发布；
- 禁止用手工/其他AI触发的快照冒充自然Cron；
- 必须在另行授权安全发布后，记录每个自然周期的trigger→Queue accepted→delivery→source range完整→canonical→durable accepted/readback，连续7天，按实际计划频次核算；
- 评估旧分区ready/in-flight/delayed/expiry，明确旧READY回退和失败新部署的安全停机条件；不可任意删除旧部署或消费旧消息；
- 未通过任何一项硬门槛：保持Production HOLD，不拉真实付费试用。

## C05-D 隔离执行与交付

- 在最新C04提交上新建独立分支，先设置deploymentEnabled=false；
- 运行聚焦/完整Python、AI边界、TS/Vite/全量npm build；分清OFFLINE vs REAL SOURCE vs PRODUCTION；
- 所有结果中文归档GitHub，机器证据与失败原文要包含准确来源/日期/HTTP状态/sha但不泄露密钥；
- 不合并main、不更新Production、不开新Preview、不改Cron、密钥、付费和用户/医院账户；
- 若官方真实附件无法取得，继续推进不依赖它的独立审计与测试，别卡住整个项目；但绝不能将它标通过。

完成后继续提供「推进下一步」按钮，不推荐模型和思考等级。
