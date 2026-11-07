# MedicalChannelAI｜MVP用户可见代码差距与A01最小开发授权卡

**审查日：2026-11-08（北京时间）｜只读源代码核查，非运行验收**  
仓库 `wpuu/MedicalChannelAI`，分支 `codex/p0-reliability-contracts`，基线 `aa026fefde0436779674180d03df628fe9a8e46c`。审批范围见[已批准MVP](product-mvp-one-page-2026-11-07.md)，**不用再次审核三项产品方向**。

## 0. 证据与结论边界

- 本轮读取六份交接文件与原分支上的前端页面、服务层、私有API、来源时效规则、公共医疗范围配置和少量相关现有测试源。原`/workspace/MedicalChannelAI-p0`工作树在当前容器**不存在**，因此**其他环境的未提交改动及在途任务未知**；未创建新工作树。
- **本轮不运行**应用、测试、构建、SDK、采集、模型，不访问云端业务服务及真实运行数据。本报告说“代码存在／静态见到”不代表部署版本、实时工作正常、用户可用。
- 沿用已有历史：应用验证代码`3f88ff7`，1213 Python／10模板／3原CLI仅**历史离线记录**；真实d Preview验收**NO-GO暂停**，SDK及强保证**CLOSED NO-GO**，`production_ready=false`、`apply_allowed=false`、`migration_usable=false`。
- **已批准**：天津地区医院检验设备经销／代理商销售用户，天津采购单位**血细胞分析仪整机**，真实更新→可信匹配与资格判断→私有跟进提醒，前台重新加载已发布结果／受控后台采集。试剂／质控／耗材／维保及其他检验设备**排除首期**。**3家真实客户试用仍是待实施建议**，未招募、未获本轮外联或试用授权。

## 1. 用户可见路径差距矩阵（静态证据）

状态使用**代码已有、部分已有、检查路径未见、历史测试存在但线上未知、运行未知**，不能把静态“已有”理解成业务PASS。

| MVP功能 | 已查的实际路径和关键事实 | 审查结论 |
| --- | --- | --- |
| **客户资料：产品和授权** | [web/src/pages/ResourcesPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/ResourcesPage.tsx#L54-L94)的“我的资源”直接调用`loadLocalCustomerProfile/saveLocalCustomerProfile`，提示保存在当前浏览器；[web/src/services/profileApi.ts](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/services/profileApi.ts#L116-L160)有API账号资料读写；[web/src/components/opportunity/OpportunityExecutionCard.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/components/opportunity/OpportunityExecutionCard.tsx#L186-L255)从商机详情可保存当前账号产品能力。[web/src/services/localCustomerProfile.ts](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/services/localCustomerProfile.ts#L11-L47)数据结构是关键词、能力类型、医院关系／目标，**不含单独的厂家授权证据、报名所需资格逐项确认**。 | **部分已有**：用户资料录入/不同路径存在；“我的资源”页面与账号侧保存语义不同，跨设备一致性/资格证明**未知**。 |
| **天津地区限定** | [web/src/config/marketPreference.ts](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/config/marketPreference.ts#L1-L76)默认天津但允许北京、河北、东北等并可改选；[web/src/pages/OpportunityPoolPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/OpportunityPoolPage.tsx#L338-L354)使用`facts.market_code`筛用户选择的地区，不是批准范围的天津永久锁定。 | **部分已有**：天津筛选能力已有；首期统一只显示天津**未形成产品专属不变量**，本轮不改历史多地区通用功能。 |
| **血细胞分析仪整机判别** | [web/src/services/localCustomerProfile.ts](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/services/localCustomerProfile.ts#L67-L110)与[web/api/_privateProfileContext.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_privateProfileContext.js#L4-L94)使用通用`IVD`别名，将检测试剂、质控品、校准品放在同组，[web/api/_privateProfileContext.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_privateProfileContext.js#L234-L244)关键词匹配可形成客户能力；[web/pipeline/data/medical_channel_scope.json](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/pipeline/data/medical_channel_scope.json#L1-L60)医疗大类含试剂、质控品。[web/src/pages/OpportunityPoolPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/OpportunityPoolPage.tsx#L99-L152)目前商机卡片显示优先级、阶段、地区，**未见首期整机专属三态标识**。 | **专属规则缺失（检查路径内）**。**宽泛IVD匹配≠已验证血球仪整机匹配**；可能导致试剂／质控被误判为业务相关，需要先避免误导性显示。 |
| **可信资格三态** | [web/src/components/opportunity/OpportunityExecutionCard.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/components/opportunity/OpportunityExecutionCard.tsx#L245-L274)录入`DIRECT_AUTHORIZED`等**用户自报能力类型**；[web/api/_privateProfileContext.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_privateProfileContext.js#L234-L305)把自报关键词用于优先级；[web/src/components/opportunity/DecisionCard.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/components/opportunity/DecisionCard.tsx#L21-L111)为AI行动建议，不是官方逐项资质校验。 | **完整资格核验未见**：无证据支持`满足／不满足／未知`对应真实招标资格材料；不能把自报授权或AI评分当可投判定。 |
| **有效时间和公告阶段** | [web/api/_runtimeOpportunityTime.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_runtimeOpportunityTime.js#L68-L116)根据报名／投标截止和调研时间处理关闭／晚窗口；[web/src/pages/OpportunityPoolPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/OpportunityPoolPage.tsx#L338-L354)已有开放／提前布局／晚窗口过滤。 | **部分已有＋历史离线证据**：时间逻辑存在；具体线上当前窗口、官方原文与源新鲜度本轮**未知**。 |
| **页面重载与后台采集分工** | [web/src/services/ApiTodayActionsService.ts](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/services/ApiTodayActionsService.ts#L478-L519)使用GET读取`/today`，[web/src/pages/OpportunityPoolPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/OpportunityPoolPage.tsx#L300-L335)取现有商机池，[web/src/services/verifiedSnapshotClient.ts](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/services/verifiedSnapshotClient.ts#L29-L63)读取发布快照；[web/src/pages/TodayPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/TodayPage.tsx#L95-L180)还会调用提醒／状态及缓存AI建议读取，不能据此等同采集执行。后端有独立collector，但**本轮未启动**。 | **代码路径上前台读、后台采集分离，业务效果未验**。不能据GET名称断言所有请求严格无副作用，历史NO-GO仍约束真实查询。 |
| **私有跟进／站内提醒** | [web/api/_privateCore.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_privateCore.js#L530-L560)写`private_followups/private_followup_events`，[web/api/_privateCore.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_privateCore.js#L805-L908)按`user_id/organization_id`查询提醒及ACK；[web/src/services/reminderApi.ts](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/services/reminderApi.ts#L165-L197)对应API。[web/src/pages/FollowedPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/FollowedPage.tsx#L120-L188)可重读账号跟进列表，[web/src/components/today/DueRemindersPanel.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/components/today/DueRemindersPanel.tsx#L43-L87)明确**站内提醒，非微信/短信/系统Push**。 | **代码已有、真实跨登录／跨账号隔离／持久性待验**。历史离线测试[web/pipeline/tests/test_reminder_next_action_ui.py](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/pipeline/tests/test_reminder_next_action_ui.py#L1-L53)只证明存在对应逻辑断言，不是线上B5通过。 |
| **官方更正和结束后保留历史** | [web/api/_runtimeOpportunityTime.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_runtimeOpportunityTime.js#L68-L116)存在关闭窗口判断；[web/src/pages/FollowedPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/FollowedPage.tsx#L198-L230)文案与列表保留历史记录；[web/src/pages/OpportunityDetailPage.tsx](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/src/pages/OpportunityDetailPage.tsx#L280-L288)可展示历史私有快照。 | **部分已有，线上B6未知**。无本轮真实公告更正取证；历史快照不可冒充最新官方结论。 |

**关键约束：** 上述“未见”只表示本轮审阅的相关路径缺少可证实现，不对未读的整个仓库断言绝对不存在。产品资格、来源覆盖、持续调度、云端保存均不从代码静态存在推断为PASS。

## 2. 与已批准六项B1–B6对应

| 验收 | 当前证据和缺口 | 本轮状态 |
| --- | --- | --- |
| **B1 真实更新** | 官方采集／快照代码和历史记录存在；未冻结本轮真实天津血球仪整机公告样本，未运行实际发现→核验→发布→用户页面链路。 | **NOT_VERIFIED** |
| **B2 重新加载** | 前台GET已发布结果的读路径存在；未证实实际发布前后版本变化、刷新不触发真实采集/副作用。 | **NOT_VERIFIED** |
| **B3 可信匹配／资格／时间** | 通用匹配和时间代码部分存在；**整机与试剂／质控分界缺失**，招标资格三态证据未见。首个切片A01**仅解决整机相关性的前台保守标识**，不完成资格判断。 | **NOT_VERIFIED；A01拟修一个子项** |
| **B4 故障诚实** | [web/api/_sourceHealth.js](https://github.com/wpuu/MedicalChannelAI/blob/aa026fefde0436779674180d03df628fe9a8e46c/web/api/_sourceHealth.js#L1-L63)有`HEALTHY/FAILING/STALE/UNKNOWN`判断与成功时钟；本轮没验证真实来源失败或独立发布。 | **NOT_VERIFIED** |
| **B5 私有跟进** | 用户作用域SQL与站内提醒代码存在；未做两个账号的退出重进、隔离及提醒持久性线上实测。 | **NOT_VERIFIED** |
| **B6 更正／关闭** | 过期窗口和跟进快照代码存在；缺当前真实官方更正样本的全链路对照。 | **NOT_VERIFIED** |

## 3. 唯一首个最小可授权开发切片：A01

### A01｜天津血细胞分析仪**整机相关性三态标识**（商机池，离线）

**目标用户效果：** 在`/opportunities`商机卡片，用户能一眼看到「**整机相关（仍须核资格）**／**非本期整机**／**证据不足待核**」，并看到**从哪一项官方结构化设备名称作出的解释**。不再把通用IVD关键词或“检验科”单独当作整机匹配证据。保留查看官方依据入口和现有跟进流程。

**为什么只选这个切片：** 血球仪整机与试剂耗材误混会直接损害首期用户可信度；目前代码路径明确使用通用别名，而前端卡片有明确接入点。它**无需新采集、数据库/SDK/模型、产品档案迁移**，可完全离线运行定向样本检验。先标清事实边界，再讨论资格三态、推荐排序及真实来源验收。

**拟触及精确文件（仅4个，须用户另行批准后才可改）：**

1. **新增** `web/src/utils/hematologyWholeDeviceScope.js`：独立无副作用纯函数，对`facts.market_code`、`facts.products`中实际官方产品名／规格、必要时可靠的产品类别作保守三态判断。**不能把通用IVD、检验、医院名或无结构化证据的标题推成确认整机**。结构化设备和试剂混合时逐项判断；不因出现试剂就否决同时存在的真实整机项目。
2. **新增** `web/src/utils/hematologyWholeDeviceScope.d.ts`：声明`IN_SCOPE/OUT_OF_SCOPE/NEEDS_EVIDENCE`及理由/证据类型供TypeScript页面使用；不添加新运行依赖。
3. **仅修改** `web/src/pages/OpportunityPoolPage.tsx`：在商机卡显示三态及依据，非本期/不明标清，不将非本期标为已符合、也不暗改原公开事实、服务器评分／排序、现有地区选择、提醒或AI分析动作；本切片**不宣称首页Today、详情页、后端评分已同步升级**。
4. **新增** `web/scripts/check-hematology-whole-device-scope.mjs`：无网络的Node断言脚本，直接调用纯函数覆盖以下离线案例，不引入测试依赖。

**离线定向通过条件（实际尚未执行）：** 至少覆盖显式血细胞分析仪／血球仪整机；三分类／五分类仅有官方规格时才展示；“血细胞分析仪专用试剂／稀释液／质控品／校准品／耗材”；纯维保；混合整机+试剂（只认整机项）；仅`IVD`或“检验设备”；只有标题无可靠产品明细；天津以外地区；地区缺失；缺官方依据；无任何候选时显示“0条”。每例断言**分类、保守理由与无资格承诺**。只有明确官方产品明细可证时显示`IN_SCOPE`；缺证为`NEEDS_EVIDENCE`而不是主观补全。回归不修改已有客户端筛选、账号状态及快照对象。

定向脚本预期命令：`cd web && node scripts/check-hematology-whole-device-scope.mjs`；如依赖已经存在，再做`npm run typecheck`。**这些是以后获授权实施时的验收计划，本轮未执行**。若需要安装依赖、改锁文件或扩文件范围，必须另行说明并取得授权。

**必须明确不能宣称：** A01即使离线PASS，B1–B6均仍**NOT_VERIFIED**；它不实现资格证书比对或三态资格裁决，不改变Today/详情/后台结果，不等于全部商机收口、不证明真实新公告、线上稳定性或真实客户满意。对多地区通用页面仅加保守试点标签，不删除原地区资产；首期全路径的天津限定仍需后续独立切片。

### A01的单独授权与停止门禁

- **尚未授权应用修改。** 需要用户明确批准**仅此4文件、本地离线的A01实现与定向测试**，不得推断从“批准产品方向／继续文档分析”获得工程开工许可。
- 若获授权：先核当前远端HEAD、原工作树及在途修改；发现已有同类实现先复用／停止重复工程；按最小4文件实施，测定向合约；无运行环境或真实测试失败则标记未完成，不扩大到环境建设／云端验证。
- 真实Preview／云端B1–B6验收**仍禁止**：若日后要做，必须另有完整d Preview门禁证据及逐动作授权；不能借A01顺带发布、触发采集／模型／队列／计划、查询真实数据库、读实际环境／权限。
- GitHub归档授权仅涵盖获授权的文档或A01成果；需`[skip ci]`非强推快进，严格回读远端HEAD。禁止合并main／PR／workflow／部署。当前A01**仅文档授权卡，不是已施工**。

**唯一下一任务：** 等用户明确授权A01四文件**本地离线实现**后执行；未授权则保持只读与已有批准的产品范围，不重复写同类差距报告。推荐GPT-6.1 Sol High，实际设置未核实。
