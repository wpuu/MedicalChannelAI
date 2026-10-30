# MED-ACTION-20261031/C06｜官方更正原件、迁移预检与自然运行验收准备

起点必须读取：
- docs/research/2026-10-31/C05_implementation_and_audit.md
- docs/research/2026-10-31/C05_validation_evidence.json
- docs/research/2026-10-31/C05_seven_day_natural_cron_protocol.md
- fix/c05-durable-failure-audit-20261031 的最新代码；
- GitHub main、PR75、PR78最新状态。

C05已经提供：7项新测试、C04已有20项，Python全量993项及prebuild/TS/Vite全PASS；独立鉴权失败审计端点在分支默认关闭，Hobby函数仍保留一个空位。**这不是生产Canary通过。**

## A. 官方最新公告版本原件

1. 找到天津第三中心医院 A939/A944 在2026-10-30的官方更正公告正文与带颜色标注的修订项目需求书DOCX。只能从官方开放可访问URL、政府采购公告直接附带的公开附件或用户合法下载后提供的文件读取。
2. 禁止绕过403、登录、验证码或反爬限制；不得将第三方转载推定为官方原件。
3. 若拿到原件，保存SHA256、下载来源、公告版本、附件元数据；逐包比10/27与10/30的产品名、数量、技术参数、资质、预算/最高限价、报名/投标时间；未披露字段为UNKNOWN。
4. 用真实HTML/DOCX对C02包级解析回归。若原件仍拿不到，不重复无意义刷新，保存准确阻碍后转其他工程任务。

## B. 持久审计Postgres schema及容量迁移预检

1. 只读检查现有Neon项目meta与业务表设计，优先检视public_collector_runs现有功能和数据库连接策略；禁止执行生产DDL或写任何行。
2. 审查C05新表public_collector_audit_events的字段白名单、event_id主键、ON CONFLICT幂等、写后读回、索引、权限及7/30/90日保留。
3. 检查新的独立审计令牌与原快照发布令牌完全分离；未启用时是503，不向公众暴露错误历史；考虑严格的限速与GET上限。
4. 用隔离的假DB或授权临时分支DB进行实际SQL冒烟（如能），不可接入Neon生产。
5. 检查C05的同步HTTP失败审计是否增加不必要函数延迟；审计失败不能把原Queue错误吞掉或误变成功。
6. 审查Hobby函数槽位和Cron配额，不能为了上审计增加付费成本或打开Production。

## C. 30日来源完整窗口/Queue续批证明

1. 核PR78源完整索引、分页、候选manifest、3条详情/批、整源fail-closed；绝不偷用现有C04 Stage completed证据替代source window complete。
2. 在隔离测试用合成、官方可验证片段构造30天窗口、多页、多批、部分失败、重复投递、旧部署消息、checksum冲突样本。
3. 检查旧版Queue分区ready/in-flight/delayed的只读证据能否通过官方接口获取；不能获取则记录未知，不删除旧队列/不强制消费。
4. 集成到真实官方数据源前必须有合法原始页面证据，禁止用猜测URL补真实源。

## D. 七天自然Cron验收的真实启动门槛

按C05协议执行。当前main只部署08:20北京时间一条Cron；PR75/78双时段未发布。

在另行明确获得生产Canary授权且全部source/代码/审计迁移门禁满足之前：只能设计、模拟和做只读检查，不能实际改Production或触发Queue/Cron；不能把人工/其他AI刷新写作真实自然周期。

真实生产完成后，连续七个北京时间自然日由平台Cron触发；要求每周期Queue受信、源窗口complete、canonical幂等、安全发布和DB/Serving hash读回，有完整错误审计。任何UNKNOWN/失败均不算PASS。

## E. 交付格式

- 隔离分支 + 精确起始/最终SHA；
- 官方版本对照表，显示各字段官方证据等级；
- SQL迁移安全审计及最小容量估算；
- 30日窗口/3条分批/Queue边界测试证据；
- 真实还是离线/模拟的明确标记；
- 聚焦Python、全量Python、Node安全、TypeScript/Vite完整CI；
- 保持main、PR75/78、Production、Cron、Queue、Secrets、客户外联不变；
- 下一阶段按钮，勿推荐模型或思考等级。

任何未验证项必须保持UNKNOWN或HOLD，不能因为新文档或CI绿色就宣称商业可售。
