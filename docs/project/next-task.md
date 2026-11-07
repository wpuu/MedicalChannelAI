# 下一任务（唯一）：A04资格证据门禁，只在用户另行批准后离线开发

**A03已完成，不再重复方案分析。** 已核实名为`qualification-tristate-evidence-contract-2026-11-08.md`的资格三态证据合同、现有字段缺口和下一授权卡。三项业务范围此前已批准：天津检验设备经销／代理销售用户、天津血细胞分析仪整机（试剂／质控／耗材／维保排除）、真实商机更新→可信匹配/资格→站内跟进；3家试用客户**仍未招募**。

## A04唯一提议（当前未授权）

**目标**：在商机详情建立“资格待核”的可信证据缺口提示。原公开快照**没有已核验的资格条款全集**、客户Profile没有证书／厂家授权证明，故现有真实卡片只能`UNKNOWN`，不能因`IN_SCOPE`、`DIRECT_AUTHORIZED`或AI高分转成`SATISFIED`。仅在离线完整合成“官方要求＋客户有效证明”时断言`SATISFIED`，有明确无合规替代的反证时`NOT_SATISFIED`，其余`UNKNOWN`；这些不能伪装为线上客户资格通过。

**用户如明确批准**，仅授权以下4个应用文件：
1. 新增`web/src/utils/qualificationEvidenceGate.js`（无网络/无存储的纯判定器）。
2. 新增`web/src/utils/qualificationEvidenceGate.d.ts`（明确三态输入/来源与输出类型）。
3. 仅修改`web/src/pages/OpportunityDetailPage.tsx`（展示默认UNKNOWN、官方链接及缺失证据说明，不上传/保存客户证件，不修改AI/跟进）。
4. 新增`web/scripts/check-qualification-evidence-gate.mjs`（离线合成正/负/未知与版本、包件、时效、安全回归）。

**仅实施条件**：再次核GitHub远端HEAD，读本分支最新HANDOFF/working-protocol/current-state/checkpoint/next-task/产品稿和A03合同，若已有原工作树先查未提交变更/在途并复用；没有环境不新建、不安装依赖。只运行新增定向Node测试，原依赖已经可用才运行TypeScript typecheck。任何要求改Profile、服务器、公开Schema、DB、附件采集或扩大文件范围的情形必须停止并申请新授权。

**保留限制**：A01离线34/34历史PASS；A02 GitHub blob 35/35静态PASS，但`--a02-only`真实Node脚本和完整TypeScript检查未运行；B1–B6全部NOT_VERIFIED；d Preview NO-GO，SDK/强保证CLOSED NO-GO；`production_ready=false`/`apply_allowed=false`/`migration_usable=false`；无部署、模型、采集、生产数据和真实客户试用。没有新的明确批准，不写任何应用代码；也不重复生成同类A03文档。

推荐 GPT-6.1 Sol / High，实际运行档未核实。

## 完整可复制提示词（用户单独批准 A04 时使用）

```text
我单独批准 MedicalChannelAI 的 A04 资格证据门禁最小离线开发切片，只允许本消息列出的4个应用文件及必要交接文档修改，不授权真实运行和线上资格判定。

唯一仓库 https://github.com/wpuu/MedicalChannelAI ，分支 codex/p0-reliability-contracts。先核远端最新HEAD，再依次读取 docs/project/HANDOFF.md、working-protocol.md、current-state.md、checkpoint.json、next-task.md、product-mvp-one-page-2026-11-07.md、qualification-tristate-evidence-contract-2026-11-08.md；核对可用本地原工作树的未提交改动和在途工作，不覆盖他人。复用A01/A02已有的产品相关性三态，不重做。

按A03资格证据合同，只新增 web/src/utils/qualificationEvidenceGate.js、qualificationEvidenceGate.d.ts、web/scripts/check-qualification-evidence-gate.mjs，并仅局部修改 web/src/pages/OpportunityDetailPage.tsx。建无网络纯函数的资格三态判定：同一项目/包件/官方版本和完整官方硬资格、客户许可的真实有效证据逐项一致时仅可给“资料预核匹配”SATISFIED；有明确无有效替代的反证才NOT_SATISFIED；官方条款/附件/客户证书/厂家授权/有效期缺证一律UNKNOWN。所有当前没有资格输入的真实卡片只能UNKNOWN，展示缺哪些官方/客户证据及官方来源入口，不允许填写/上传/存储证照号码，不改后端/公开快照/客户Profile/数据库/AI/跟进/评分。

只以合成正负未知、公告更正、包件错位、资料过期与客户间隔离案例执行新增离线Node断言；仅在现有项目依赖可用时执行TypeScript typecheck，不安装依赖、不运行无变化的旧1213/10/3全套。若仅4文件无法安全达成，停止并报告，不扩范围。A01/A02的历史门禁事实保持，不能把合成通过或静态测试当线上业务通过。

不得部署、触发采集/模型/工作流、修改运行数据库、缓存、域名、权限、计划、配置或读取实际凭据/客户证书。真实d Preview NO-GO、SDK及强保证CLOSED NO-GO，apply_allowed=false、migration_usable=false，B1–B6仍NOT_VERIFIED。将真实有效改动和交接文档以[skip ci]正常提交并非强推快进同步当前GitHub分支，核对远端HEAD；不建PR、不合并main。结束列实际完成、验证、未完成和唯一下一任务。推荐GPT-6.1 Sol High，实际设置未核实。
```
