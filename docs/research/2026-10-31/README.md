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
