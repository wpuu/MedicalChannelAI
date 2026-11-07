# 唯一下一任务：A02跨页面一致性（需单独授权才能改代码）

**A01已完成的可验证范围：** 当前分支仅商机池`OpportunityPoolPage.tsx`接入了血细胞分析仪整机三态标识，复用新纯函数`hematologyWholeDeviceScope.js`及类型声明；新增离线Node定向34/34 PASS和Node语法检查PASS（Node v22.16.0）。**完整TypeScript类型检查未运行、没有真实浏览器/上线验收**。原Git工作树不在当前容器，其他环境在途UNKNOWN；没有安装或创建新环境。详见`current-state.md`最新段和`checkpoint.json`。

产品三项范围已获批准，无需再审核：天津代理／经销销售用户、天津血细胞分析仪整机、真实更新→可信判断与资格→站内跟进提醒。3家客户试用未招募。**A01不改变评分或用户资格，也未修改Today/商机详情。**

**A02唯一后续候选（未授权，不能自动施工）：** 在`web/src/components/today/ActionCard.tsx`和`web/src/pages/OpportunityDetailPage.tsx`复用A01纯函数和三态文案，使Today与详情不会与商机池呈现矛盾的整机范围提示；如需定向验证可仅追加`web/scripts/check-hematology-whole-device-scope.mjs`既有测试。严格不改后台、评分、采集、模型、数据库、资源资料、资格判断或跟进写入。**这不是B3完整资格验收**；先检查代码及在途改动，已有功能不得重复造轮子。

没有用户**明确授权A02相应文件离线修改**，不得开始应用代码变更。B1–B6均`NOT_VERIFIED`，d Preview在线验收仍NO-GO暂停，SDK/强保证CLOSED NO-GO，`production_ready=false`、`apply_allowed=false`、`migration_usable=false`。新旧测试证据分开，不重跑未变1213 Python／10模板／3CLI或额外采集/模型。后续若出现新授权及有效修改，文档与代码按[skip ci]非强推快进提交当前分支并回读远端；不建PR、不合并main、不自动部署或触发Workflow。

## 完整可复制提示词（仅在用户批准A02后生效）

```text
我单独授权 MedicalChannelAI A02 仅离线跨页面整机三态显示一致性开发。先核实 wpuu/MedicalChannelAI 仓库 codex/p0-reliability-contracts 最新HEAD，按 docs/project/HANDOFF.md、working-protocol.md、current-state.md、checkpoint.json、next-task.md、product-mvp-one-page-2026-11-07.md 和 A01新文件接手，先查已有工作树/在途修改，不覆盖他人成果。

产品范围已批准：天津地区医疗检验设备经销商/代理商销售人员，天津血细胞分析仪整机，排除试剂/质控/耗材/维保，真实商机更新→可信产品匹配与资格→私有跟进。A01已经在OpportunityPoolPage实现纯展示三态，Node离线定向34/34 PASS，仍未完整TypeScript/浏览器验证。

本轮仅授权局部修改 web/src/components/today/ActionCard.tsx 和 web/src/pages/OpportunityDetailPage.tsx，复用已有 web/src/utils/hematologyWholeDeviceScope.js 及 .d.ts 的三态与理由；必要时仅修改已有 web/scripts/check-hematology-whole-device-scope.mjs 增加离线一致性检查。不能修改其他应用文件；不得改变排名、筛选、AI、跟进、资格三态、数据库、采集或事实。若代码结构不支持该限定文件范围，停止扩范围并报告。

仅运行新增或改变的定向Node测试；现成项目依赖可用时运行TypeScript typecheck，不安装依赖、不重跑未变全量套件。不得部署、触发云端采集、模型、工作流、定时计划/权限/环境/运行数据。d Preview NO-GO和SDK/强保证CLOSED NO-GO保持，apply_allowed=false、migration_usable=false，B1–B6仍NOT_VERIFIED。有效更改仅提交[skip ci]、非强推快进GitHub当前分支并核对远端HEAD，不建PR或合并main。最终报实际完成、验证、未完成及下一任务。推荐GPT-6.1 Sol High，实际设置未核实。
```
