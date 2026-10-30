# MedicalChannelAI｜2026-10-30/C02 隔离修复验收索引

状态：C02_OFFLINE_TESTED / RELEASE_HOLD
隔离分支：fix/c02-ccgp-package-products-20261030
基线：PR #78 d158f8648db17b904300671b0f1ccbae795c324c
Production：不变；不合并 main；本分支无 Preview。

- C02_implementation_validation.md：代码变更、修复前红灯/修复后验证、官方原始页面 HTTP403、PR78 共同 npm build 基线失败、生产只读检查及放行门槛。
- C02_validation_evidence.json：审计机器可读摘要、执行的 Actions run ID、修复前后数据、生产快照。
- C01 研究证据不在本分支；请查看 research/medical-action-c01-20261030 的 docs/research/2026-10-30/（包括四批采购包源分级和 C02 最初任务书）。
- 核心代码：web/pipeline/medical_channel_pipeline/ccgp_tianjin_package_table.py；ccgp_detail.py；public_snapshot.py。
- 回归：web/pipeline/tests/test_ccgp_tianjin_package_table_c02.py。
- Actions：c02-offline-ccgp-verify.yml、c02-one-shot-official-read.yml。

下一阶段：C03 实际原始HTML验收、隔离修复旧 AI boundary 测试时钟基准、自动数据新鲜度审计；任何失败都不升级成“已可以收费”。
