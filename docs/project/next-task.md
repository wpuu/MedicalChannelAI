# 唯一下一任务：A05 CCGP资格要求原文有界离线提取（尚待单独授权）

**A04已完成其获批离线四文件范围，不重做：** `web/src/utils/qualificationEvidenceGate.js`及`.d.ts`增加纯函数严格三态；`web/src/pages/OpportunityDetailPage.tsx`只对当前真实公开商机展示`UNKNOWN`资格待核和证据缺口；`web/scripts/check-qualification-evidence-gate.mjs`新增Q01–Q15及边界合成检查。现有Node v22.16.0对与GitHub新JS blob **字节相同的纯函数**以内存执行36/36项PASS（git SHA: `c5f2bb6ef434640e600e7870bad7cc527b20078e`）；**新增独立.mjs文件未在原工作树直接执行，完整TypeScript typecheck也未运行**，原项目工作树/就绪依赖不可用，不能把这两项称通过。

B1–B6真实业务验收仍NOT_VERIFIED；d Preview NO-GO，SDK/强保证CLOSED NO-GO，`production_ready=false`、`apply_allowed=false`、`migration_usable=false`；3家试用客户仍未招募。首期天津、血细胞分析仪整机（排除试剂/质控/耗材/维保）及客户定位已经批准，不必重复确认。

**A05唯一候选（需用户单独批准才能修改代码）**：只在`web/pipeline/medical_channel_pipeline/ccgp_detail.py`添加一个可离线调用的、边界明确的“申请人/供应商资格要求”原文片段定位器，在`web/pipeline/tests/test_ccgp_detail.py`添加定向合成案例。对“略”、“详见附件”、缺分包或公告正文不完整返回`INCOMPLETE`，不编造硬资格，不将该辅助片段写入旧`validate_record`或`PublicFacts`，不修改正式采集运行、HTTP、数据库/模型/Profile/AI、前端和定时计划。离线原文提取**不等于资格已核实，也不代表B3通过**。

A05开始前核远端最新HEAD、六份交接文件和已有 parser 代码、原工作树/在途变更；已有功能则复用。若两文件不够，停止并说明所缺新授权。只运行新增定向离线案例，既有依赖可用再做必要门禁，不安装或新建环境。有效成果只以`[skip ci]`正常提交、非强推快进归档当前GitHub分支并独立回读远端HEAD；无变更不空提交，不合并main，不建PR，不部署、不采集/模型或操作真实数据。

推荐GPT-6.1 Sol / High，实际档位未核实。

## 完整可复制提示词（单独批准A05后使用）

```text
我单独批准 MedicalChannelAI A05 两文件离线资格条款有界提取切片。先核实 GitHub wpuu/MedicalChannelAI 的 codex/p0-reliability-contracts 最新 HEAD，按 docs/project/HANDOFF.md、working-protocol.md、current-state.md、checkpoint.json、next-task.md、product-mvp-one-page-2026-11-07.md 及 qualification-tristate-evidence-contract-2026-11-08.md 接手。核查已有工作树、未提交改动和在途任务，不覆盖。

严格仅允许修改 web/pipeline/medical_channel_pipeline/ccgp_detail.py 与 web/pipeline/tests/test_ccgp_detail.py。对已有CCGP离线公告文本“二、申请人的资格要求/供应商资格要求”做明确起止边界的原文片段/位置提取；缺少全文、附件、分包归属或只有“略/详见招标文件”时返回INCOMPLETE，不把提取段落等同经完整核验的资格清单，也不触及canonical record、公有快照、Profile或DB。新增本地合成正反缺失案例并只跑定向离线检查。

不能修改其它应用、配置、权限、定时计划、工作流、域名或运行数据，不创建环境、安装依赖、上线、调用模型、采集或实际官方站点，不触发d Preview；B1–B6继续NOT_VERIFIED，d Preview NO-GO、SDK强保证CLOSED NO-GO，apply_allowed=false、migration_usable=false。若两文件无法实现停止并报告，不扩范围。更新必要交接，GitHub [skip ci] 非强推快进同步当前分支并回查远端HEAD，不合并main/建PR。最后列完成、验证、未完成、唯一下一任务。推荐GPT-6.1 Sol High，实际模型与档位未核实。
```
