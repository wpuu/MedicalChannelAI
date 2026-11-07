# 下一任务（唯一）：等待单独授权A01后进行4文件离线最小切片

**已完成，不再重做：** 2026-11-08 的 [MVP代码差距矩阵与A01授权卡](mvp-gap-and-a01-authorization-2026-11-08.md)。三项产品范围**已经批准**：天津医院检验设备代理/经销销售用户；天津血细胞分析仪**整机**（试剂、质控、耗材、维保及其他设备排除）；真实公告更新→可信匹配/资格→站内跟进提醒，页面只读已发布数据/后台受控采集。

**A01仅提出，尚未获工程授权：** 只在商机池显示“整机相关／非本期整机／证据不足待核”的保守三态及解释，不把IVD或检验科关键词当整机证据；不修改服务器公共事实、采集、用户数据、评分、资格、模型及Today/详情。拟触及四文件：
1. `web/src/utils/hematologyWholeDeviceScope.js`（新，纯函数）
2. `web/src/utils/hematologyWholeDeviceScope.d.ts`（新）
3. `web/src/pages/OpportunityPoolPage.tsx`（仅本页局部显示）
4. `web/scripts/check-hematology-whole-device-scope.mjs`（新，离线Node断言）

**用户下一次如明确说“批准A01按四文件离线施工”，才有权实施。** 没有额外授权则不改应用，不重复提交相同审查报告。

## A01的计划验收（未执行）

- 官方结构化整机名称为整机相关；试剂、质控、校准液、耗材、维保与非天津为非本期；只写IVD、项目标题或缺少官方设备明细为证据不足；整机+试剂同公告仍只认整机条目；不制造资格已满足或可投结论。
- `cd web && node scripts/check-hematology-whole-device-scope.mjs`定向案例通过；现有依赖已就绪时`npm run typecheck`通过。不得改变已有工作流或自动抓取，不重跑无变化1213/10/3，需安装／扩范围时单独说明。
- **实施后也不称B1–B6通过**：真实线上/d Preview仍NO-GO，SDK/强保证CLOSED NO-GO；`apply_allowed=false`、`migration_usable=false`。另行批准且具完整门禁前不得部署、触发采集/模型/数据库、改计划/域名/权限、联系客户。
- 先按最新GitHub HEAD及六份交接文件核对当前工作树/在途；不得覆盖；仅在用户明确授权的实施范围内改动并创建有证据的变更；GitHub归档含`[skip ci]`，正常快进、回读远端HEAD，不强推、不合并main、不建PR/触发workflow。

推荐 GPT-6.1 Sol High；实际设置未核实。

## 完整可复制提示词（**仅在批准A01后发送**）

```text
我单独授权MedicalChannelAI 的A01四文件本地离线实施，仅做天津血细胞分析仪整机相关性三态标识；不授权云端运行。

先核实 wpuu/MedicalChannelAI 的 codex/p0-reliability-contracts 最新HEAD，按 docs/project/HANDOFF.md、working-protocol.md、current-state.md、checkpoint.json、next-task.md、product-mvp-one-page-2026-11-07.md 和 docs/project/mvp-gap-and-a01-authorization-2026-11-08.md 接手。若本地工作树存在，先核未提交改动和在途工作，不覆盖。产品三项范围已批准，无须重新提问；3家真实客户试用未招募。

仅允许新增 web/src/utils/hematologyWholeDeviceScope.js、hematologyWholeDeviceScope.d.ts、web/scripts/check-hematology-whole-device-scope.mjs，以及局部修改 web/src/pages/OpportunityPoolPage.tsx。实现商机池三态：结构化官方设备明细明确血细胞分析仪整机=相关但资格未知；纯试剂/质控/耗材/维保或明确非天津=非本期；IVD泛词、仅标题无结构化设备明细或来源区域不明=待核。混合公告逐设备识别，不因试剂一起出现而排除真实整机。展示理由，不制造资格结论，不改变原公开快照、评分排序、AI、Today/详情或跟进写入。

先独立离线验证明确正负、混合和未知案例，运行本次新增定向Node断言；仅在既有依赖就绪时运行TypeScript typecheck。无新输入/代码变化不重跑历史全量测试。若边界不够或有已实现同功能，停止扩范围并报告。

本次不允许部署、不启动采集/模型/工作流、不改任何数据库/运行缓存、域名、计划、权限或环境，不读实际凭据/运行数据；真实d Preview验收保持NO-GO，SDK及强保证CLOSED NO-GO，apply_allowed=false、migration_usable=false。仅在有效变更后更新必要交接，提交[skip ci]、非强推快进当前GitHub分支并核实远端HEAD；不建PR、不合并main。结束报告实际完成、定向测试证据、未完成与唯一下一任务。推荐GPT-6.1 Sol High，实际设置未核实。
```
