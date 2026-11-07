# 唯一下一任务：A03｜资格三态证据合同与最小授权卡（仅只读、文档）

最新A02已经按用户2026-11-07T17:04:13Z单独授权，在`web/src/components/today/ActionCard.tsx`与`web/src/pages/OpportunityDetailPage.tsx`扩展了A01分类器的**展示层三态**，并在`web/scripts/check-hematology-whole-device-scope.mjs`加入`--a02-only`定向静态检查入口。GitHub实际新blob35/35项V8静态合约检查通过；原项目工作树/依赖不可访问，**完整Node目标测试并未直接执行，TypeScript typecheck未运行，浏览器或线上未验收**。不得把这些当成B1–B6 PASS。A01/A02保留技术门禁缺口。

首期产品范围已由用户批准：天津经销／代理销售负责人及业务人员，天津血细胞分析仪整机（试剂、质控、耗材和维保排除），真实商机更新→可信匹配与资格判断→私有跟进提醒。**3家试用客户尚未招募**。当前显示的“整机相关”仅为公告产品范围相关，并不意味着具体型号适合、客户有厂家授权或者能够投标。

**唯一增量任务A03：只读现有证据和代码，制定投标资格三态（满足／不满足／未知）的最小证据合同和一个后续可单独授权的开发切片。** 先读最新GitHub HEAD和六份交接文件，静态查看现有客户资料结构、公告资质条款字段、当前AI/规则边界、历史测试样本（仅查看，不运行），说明：
1. 每项资格需哪一条**官方公告明确条件**、哪一条**客户主动确认且允许保存的私有证据**、该证据时效及缺口；无法核实时保持UNKNOWN，不能推断“符合”。
2. 只有官方条件明确且客户证据有效且逐项匹配才可提议SATISFIED；明确违反时NOT_SATISFIED；否则UNKNOWN。模型不作最终资格保证，也不能把“整机相关”当SATISFIED。
3. 只设计一个最小用户界面切片的文件边界、离线合成正反未知案例与后续需要的单独代码授权；**本轮不改代码**，不得触发模型、采集、云端数据库。
4. 若仓库已有相同合同则复用，不重复造方案；当前A02的Node目标脚本与TypeScript类型检查缺口继续保持未验证，不为了补证新建环境或安装依赖。

执行边界：无应用代码/配置/权限/工作流/计划/域名/实际运行数据改动，无部署/采集/模型/真实浏览器/云端验收；d Preview仍NO-GO，SDK及强保证CLOSED NO-GO，`production_ready=false`、`apply_allowed=false`、`migration_usable=false`。有真实新文档时用`[skip ci]`、原分支非强推快进同步并核对远端HEAD；不合并main、不建PR、不自动触发workflow。

推荐GPT-6.1 Sol High，实际配置未核实。

## 完整可复制提示词

```text
继续 MedicalChannelAI，只读推进 A03 资格三态证据合同和首个最小开发授权卡，本轮不写应用代码。

GitHub 仓库 wpuu/MedicalChannelAI，分支 codex/p0-reliability-contracts。先核实远端最新HEAD、原工作树有无未提交改动或在途工作，依次读取 docs/project/HANDOFF.md、working-protocol.md、current-state.md、checkpoint.json、next-task.md、product-mvp-one-page-2026-11-07.md。优先复用A01/A02的实际成果及既有代码，不能依赖旧聊天版本。

三项产品范围已经批准：天津医院检验设备经销/代理商销售用户；天津血细胞分析仪整机，排除试剂、质控、耗材、维保；以真实公告更新、可信产品匹配和资格判断、私有跟进提醒为MVP。A01商机池及A02 Today/详情共享整机相关性三态标签，但标签不代表投标资格满足。3客户试用仍未招募。

只读分析现有业务资料和公开公告事实字段，拆出资格三态 SATISFIED / NOT_SATISFIED / UNKNOWN 的严格证据要求：官方明确的逐项条件、用户真实确认的私有资质/厂家授权/规格证据、是否过期及证据缺口；无法确认时必须UNKNOWN，不得把用户自报产品关键词、模型分数或整机相关标签说成合格。提出一个最小可授权开发切片与离线正负未知用例；不要擅自开发或扩产品线。A01/A02的实际Node目标脚本及TypeScript typecheck仍待在具备原工作树及既有依赖的环境验证，不安装或创建环境。

仅当有真实文档增量时更新方案、HANDOFF、current-state、checkpoint、next-task；按仓库规范提交 [skip ci] 并非强推快进同步原分支、回查远端HEAD。不改变应用、配置、域名、计划、权限、数据，不部署、不触发采集、模型、工作流或真实线上验收。d Preview NO-GO、SDK及强保证CLOSED NO-GO、apply_allowed=false、migration_usable=false及B1-B6均NOT_VERIFIED保持。结束汇报实际完成、验证、未完成与唯一下一任务。推荐 GPT-6.1 Sol High，实际设置未核实。
```
