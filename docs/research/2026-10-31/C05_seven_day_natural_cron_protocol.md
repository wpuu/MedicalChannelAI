# MED-ACTION-20261031/C05｜七天自然 Cron 验收协议

日期：2026-10-31（北京时间）
状态：PROTOCOL_DEFINED / 真实生产验收天数 0
范围：隔离设计、不得手工刷新生产、不得将离线CI当作生产验收。

## 1. 时间表与真实生效版本

当前main只有北京时间08:20（UTC 00:20）的一次Vercel Cron。PR75/78准备了08:20与12:20双时段，但仍是Draft未发布。

七日验收严格按实际部署生效的Cron安排核算：
- 如果仍为单时段，每天一次，连续7个完整北京时间自然日需7次。
- 如果未来被授权发布双时段，每天早、午两次，连续7日需14次。
- 允许Vercel Hobby调度有自然抖动，但实际执行须在合同窗口内：morning 08:00-10:00；noon 12:00-14:00。
- 不能用数据库snapshot_as_of在当天就推断Cron执行成功。

## 2. 每周期必须同时具有的证据

1. 平台层真实Cron调用与鉴权：Vercel调度事件、实际请求时间、有效授权。Queue内自报VERCEL_CRON字符串不构成来源证明。
2. Queue接受回执：实际send成功或平台验证的幂等重复，独立cycle ID与message ID；发送失败须记入追加式失败审计。
3. Queue消费者按真实版本/时间窗口/租约执行：旧部署在途消息、过期周期、无租约消息不能产生新阶段成功。
4. 所需来源index完整窗口和分页：PR78约定30日页面窗口、正确页数、manifest hash、候选数；每批最多3条详情，分批续接直到全部可核实候选完成。不能因某批成功就宣称整源完成。
5. 官方详情事实身份和生命周期：host、URL、索引发布日期、详情日期、文本、内容hash校验；HTTP403/CAPTCHA/附件缺失必须明确BLOCKED，不通过非授权接口补原件。
6. Canonical状态和历史：失败不覆盖最后完整verified状态，不把以前人工/其他AI补的快照当本轮自然采集；客户私有资料不得进入日志。
7. Durable发布回执与读回：数据库public_verified_snapshots中的新snapshot hash、as-of、coverage与Serving Cache一致；C04 cache source witness若丢失则本周期完整性UNKNOWN。
8. C05独立失败审计：查询7日public_collector_audit_events的受保护记录，含周期/阶段/错误码及写入时间，需有读回；表里没有失败记录不等于本周期无失败。
9. 公开客户页面版本与真实来源一致：遇更正附件无法确认，不可按旧公告把已失效的产品技术参数认成可投最新版。

注意：C04的RECENT_STAGE_WITH_SNAPSHOT_RECEIPT只代表“阶段完成且有对应快照回执”，不代表该来源完整分页和公告附件已核验。

## 3. 不通过、未知及重试

- 来源需要的分页未读全、detail缺证据或发布只完成部分候选：FAIL_COVERAGE。
- 无平台真实Cron证据、Queue回执或DB读回：UNKNOWN，不归PASS。
- 用手工触发或其他AI发布的快照，未绑定实际平台周期：MANUAL_ORIGIN，不计验收。
- Queue至少一次送达允许幂等重试，但不能改变旧verified记录或重复创建机会。
- 任意授权路径403：BLOCKED_SOURCE，保留旧记录并显示STALE；不得绕过访问控制。
- 更正公告没有官方原文/附件时，相关行动卡必须是REQUIRES_MANUAL_CONFIRMATION。
- 七日任意一天关键门槛不通过，都不能累计七天通过；修复且重新授权后从首个真实自然周期重计。

## 4. 五级发布/商业门槛

LEVEL1 OFFLINE_CODE_PASS：隔离分支的Python、Node安全合约、TypeScript、Vite及全量构建通过。C05目前只可达到这个级别。
LEVEL2 SOURCE_DOCUMENT_PASS：A-939/A-944官方10月30日更正原文和标色DOCX真实取得，SHA256回放并逐包核对原稿差异；C02解析器通过真实DOM。
LEVEL3 AUTHORIZED_PRODUCTION_CANARY：另行明确授权后核旧Queue分区、schema、独立审计token、回退策略；真实Cron首个完整周期可核验。
LEVEL4 SEVEN_CONSECUTIVE_DAYS_PASS：实际启用频率下连续7日所有来源完整、Queue/DB/客户读回匹配、没有人工冒充或隐性失败。
LEVEL5 SMALL_PAID_VALIDATION：再邀请3个真实医疗渠道客户按产品和区域试用7天，以至少1笔实际付款及一次真实跟进动作判断商业价值。

未达到LEVEL4不能宣传稳定每日自动；未达到LEVEL5不能宣称付费商业可行性。

## 5. 最小机器证据模板（每周期）

business_date、period、production_sha、platform_cron_request_id、cron_authorized_at、cycle_id、queue_message_id、queue_accepted_at、queue_delivered_at、lease_state、source_id、required_index_window、pages_seen、manifest_sha256、candidates_total、candidates_verified、max_details_per_batch、blocked_reason、canonical_revision、source_last_success_at、durable_snapshot_hash、durable_snapshot_as_of、durable_db_readback_hash、serving_cache_readback_hash、independent_failure_events、missing_evidence、gate。

时间保留UTC和北京时间；无值一律null/UNKNOWN，不允许AI推断；敏感客户数据、凭证、医院关系及完整URL查询参数不得落审计库。

## 6. C05当前缺口

- 追加式失败事件表及受保护HTTP接口仅隔离代码通过；未配置生产独立token和启用标志，未建立生产表，未读回真实生产行。
- C04的成功快照witness附属旧系统受原完整发布门禁控制，Cache事件并非不可丢失。
- 更正官方原件未取得，PR78三源正式启用和真实分页/批次验收未执行。
- 自然Cron连续7天证明0天；生产发布继续HOLD。
