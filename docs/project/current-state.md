# MedicalChannelAI current state

Updated: 2026-10-03 (Asia/Shanghai).

MedicalChannelAI 是天津起步的医疗器械、IVD、耗材公开情报和单用户销售助手。公共事实必须有官方证据；模型不创造事实。客户私有资源与公共情报分离，关注医院不代表关系分。`production_ready=false`。

## 候选与实际生产

- 当前候选：`fix/tjmugh-verification-20261002`，草稿 [PR #75](https://github.com/wpuu/MedicalChannelAI/pull/75)，未合并。最新远端起点核验为 `3af6db8c678c6f20f8b9d120badd7db102b9d69e`；本轮新增周期候选以 PR 最新 HEAD 与该 HEAD 的 Verify 为准。
- 分支 `deploymentEnabled=false`，本轮未部署/生成 Preview、未恢复 Cron/消费者、未清队列、未真实采集或调用模型。
- Vercel 只读实际生产：`62299590dd3898e040ccc9db5fda1298d4509d51`，READY 部署 `dpl_DW5wrMzvVXS7TLmbqUL1vSfcyuh1`。数据库数据版本 `2026-10-02T14:19:15.713282+08:00`，441 条。这是旧主线，不是候选上线证明。
- 当前目标仅一个人使用：每天早间和午间各一次，候选北京时间 08:20 / 12:20，两条独立每日 Cron，Hobby 小时级精度，不升级套餐。
- 两条 GitHub 采集入口只读回查为 `disabled_manually`；Vercel Cron、消费者、积压与在途任务状态尚未核验。项目详情工具参数契约冲突不代表整个连接不可用；团队、项目列表、部署与日志查询已成功。实际套餐未知。

## 候选验证与限制

原双时段 patch 和原 85 项日志在本环境缺失，不计为已读取证据。本轮从核验后的 PR75 HEAD 恢复改动，保留已通过修复。历史候选 `e30b74a` 的 865项完整 CI 与147项定向已通过；本次保留这些证据，新增5项发布历史门禁及5项真实历史投影/来源边界检查，35项周期/恢复和20项native发布检查通过；最终独立审查及精确新 HEAD CI 见 PR 记录与 [发布清单](../ops/twice-daily-release-20261003.md)。历史 `3af6db8` 840 项/浏览器 36 项等记录仅适用于该旧 HEAD，详见 [可靠性验收](../collection-reliability-verification.md)。未为本轮重跑全部历史矩阵。

候选实现周期独立、同周期幂等、旧周期写入 fence；禁用自动 15 分钟增量链；保留所有配置刷新stage成功门禁、准确覆盖范围、失败旧数据、canonical/缓存与 AI 版本保护。长暂停后缺失 canonical 默认阻断旧种子初始化。生产提交的911条live canonical全部schema验证通过，经静态发布流程的market补全、分区构建及combine复排，在真实旧版本时间上复建的441条卡片与DATABASE读回逐字段一致；这只是历史备份候选，不证明生产缓存已恢复。审查发现的三个既有来源8条历史（含4条公开intent）读取缺口，已用独立v2历史缓存严格读取修正；不从Git/seed自动初始化，不新增采集stage。scheduled worker复用静态分区/组合流程，441条离线投影逐字段相同，修正market/rank差异。三个历史来源没有新监控，coverage明确partial，保留页面提示、AI限制及durable基线比对；不能宣称全量覆盖时间已推进。实际canonical缓存恢复、跨分片完整性、旧队列隔离及两周期成功仍未线上证明。Runtime Cache 无 CAS，发布必须排除旧消费者和旧在途写入，不能把代码 fence 当作分布式原子锁。

## 剩余工作与发布边界

控制面只读核验实际套餐、Cron/消费者/延迟消息与在途任务；建立可验证完整 canonical 恢复条件；满足门禁后由用户批准一次指定 HEAD 合并＋Production 发布，再受控恢复单一当前周期。每天两次恢复成功必须有两个独立周期完成全部配置刷新stage、partial范围准确及页面版本一致的证据。本轮不合并、不发布，不能宣称搜索已经恢复。

天津 403 与国内域名访问单独记录，不新增地区、不换架构或修改 DNS 绕过；它们不阻塞离线候选整理。发布前后、回退后检查以及失败恢复按 [受控恢复清单](../ops/twice-daily-release-20261003.md) 执行。旧 PR #6、581/558 项、2026-09-04 主线与部署状态不再代表当前项目。
