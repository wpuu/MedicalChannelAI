# MedicalChannelAI｜2026-10-31 研究与验收索引

状态：C04_ISOLATED_FULL_BUILD_PASS / PRODUCTION_RELEASE_HOLD
当前分支：fix/c04-source-proof-20261031
继承C03：fix/c03-ai-clock-official-provenance-20261031，起点 b756407bd058b69b949c655d47a02da2ee43c077

## C03 历史证据（保持可追溯）

- C03_implementation_and_provenance_audit.md：AI历史测试时间纠偏、官方原件障碍与生产旧状态。
- C03_validation_evidence.json：C03机器验收记录。
- C04_execution_task.md：C04原始任务书，含官方来源与隔离开发边界。

## C04 本轮实际交付

- C04_implementation_and_source_audit.md：中文实施/市场安全审计，官方更正信息分级及无法证实的字段、证据模块、CI与发布HOLD。
- C04_validation_evidence.json：机器可读CI、20项+986项通过、Vercel与GitHub边界。
- C04_official_version_comparison.json：A939/A944官方旧稿及10月30日第三方更正线索逐字段比对，官方更新内容UNKNOWN。
- C05_execution_task.md：真实更正附件/HTML取证、失败持久账本、自然Cron七日验收任务书。
- web/collector_proof.py：单事件证据、读取、Cache TTL21天、可入durable snapshot的有限witness、源级状态。
- web/api/collector-run.py、web/collector_queue.py、web/collector_runtime.py、web/api/collector-status.py：非权威执行侧车，不改原有发布/Lease/Queue判定。
- web/pipeline/tests/test_collector_proof_c04.py：20项纯单元与Cron/Queue集成模拟。
- web/scripts/check-collector-proof-public-snapshot.mjs：验证公开JSON中的脱敏witness以及注入api_key仍被阻断。
- .github/workflows/c04-source-proof-validation.yml：GitHub hosted Ubuntu CI；代码分支关闭自动Preview，无部署。

## 精确CI归属

测试代码 SHA：90c4832379aeae01cc91b1048fe73e425d5673b8
GitHub Actions：https://github.com/wpuu/MedicalChannelAI/actions/runs/41092275503
SUCCESS：
- C04专项20 PASS；
- 旧双时段调度37 PASS；
- 旧医院来源状态机25 PASS；
- Python全量986 PASS，prebuild再跑986 PASS；
- JS公开快照脱敏合约、AI边界、Prebuild、TypeScript、Vite PASS。

本次文档提交在测试代码后追加，不冒称文档HEAD再次运行同一CI。

## 严格门禁

- 原始官方HTML和10月30日更正DOCX未取得可校验字节，官方最新版未能比对。
- RuntimeCache并非不可丢失的审计数据库，durable snapshot仅在成功发布时保留有条件的摘要；失败历史仍缺长期凭证。
- Production自然Cron连续7天真实链仍未验收；不得声称“每天稳定自动监控”。
- main/PR75/PR78/Production/Secrets/Cron/Queue/付费与客户联系均没有改变。
- 后续按 C05_execution_task.md 推进；每轮末尾提供下一步按钮。


## C05 新增交付（2026-10-31）

当前结论：C05_ISOLATED_FULL_BUILD_PASS / OFFICIAL_CORRECTIONS_UNVERIFIED / PROD_RELEASE_HOLD。

- C05_implementation_and_audit.md：正式中文审计，A939/A944官方更正仍UNKNOWN、独立失败审计系统设计、Hobby限制修复、真实CI、真实生产阻碍。
- C05_validation_evidence.json：逐项机器证据，审计default-off/未迁移DB、7项C05及993项全量测试、官方更正缺原件。
- C05_seven_day_natural_cron_protocol.md：七个自然日的真实平台Cron→Queue→官方索引/详情→Canonical→Postgres/Serving读回验收，不允许手工数据替代。
- C06_execution_task.md：官方更正原件、SQL迁移预检、PR78完整30日窗口/<=3详情/批回归，以及生产Canary授权前置。
- web/api/_collectorFailureAudit.js：追加式Postgres失败周期事件表，严格白名单与持久读回。
- web/api/_collectorAuditHandler.js：独立token和default-off子路由，不泄漏错误详情。
- web/api/public-snapshot.js：复用既有函数的受保护审计路由，原快照逻辑不改变。
- web/collector_durable_audit.py、collector-run.py、collector_queue.py：2秒/无重试/失败不掩盖原异常的可选失败记录。
- web/scripts/check-collector-failure-audit.mjs：SQL幂等、默认关闭、鉴权与敏感字段防护。
- web/pipeline/tests/test_collector_durable_audit_c05.py：7项Python单元及Queue/Cron模拟。
- .github/workflows/c05-durable-audit-verify.yml：隔离CI，不触发生产部署。

精确已测试源码SHA：740193927f00aeda924afc131e9f05bea007b5bd
GitHub Actions：https://github.com/wpuu/MedicalChannelAI/actions/runs/41097695830
SUCCESS：C05专项7、C04专项20、旧双时段37、旧来源25、Python全量993、prebuild再次993、Node安全合约、AI边界、TS/Vite全部通过。

安全：C05新审计DDL仅在未来拥有专用token/启用标志及DB后按授权执行；本分支未创建生产表、未配置凭证、未改main/PR75/PR78/Prod/Cron/Queue，预览部署关闭。

下一步：C06_execution_task.md；不要将隔离成功等同原始官方附件、生产审计或七天自然运行已通过。
