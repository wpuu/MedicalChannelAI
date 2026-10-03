# 单用户每日两次搜索候选与受控恢复清单

记录日期：2026-10-03，北京时间。候选分支 `fix/tjmugh-verification-20261002`，草稿 [PR #75](https://github.com/wpuu/MedicalChannelAI/pull/75)。未合并、未部署、未创建 Preview、未恢复 Cron/消费者、未清队列、未调用真实来源或模型。`production_ready=false`，该分支 `deploymentEnabled=false`。

## 资产与证据来源

本环境最初是 `main` 的干净副本；未找到原 `.medicalchannelai-onboarding/schedule/twice-daily-search.patch` 或原 85 项测试日志。原任务可读记录未恢复其正文。本轮不声称读取或复用缺失资产；从远端实际 HEAD `3af6db8c678c6f20f8b9d120badd7db102b9d69e` 的已通过修复恢复候选，保留原 PR 所有修复。新生成的同名本地 patch 是本轮重建补丁，不是原文件。

此前 840 Python、浏览器 36 项与独立审查记录是该旧 HEAD 的历史证据，参见 [原验收记录](../collection-reliability-verification.md)，不计成本轮运行。本轮定向日志保存在 [evidence](evidence/twice-daily-20261003/)。新增 25 项周期/恢复测试；既有相关 76 项 collector、14 项 tick、12 项 namespace、4 项 queue、4 项 fallback 与12项 stage-dispatch 合约通过（共 147 项）。不为更新数字重跑历史浏览器或全部历史矩阵。首推 `2b913388a20b6ac961394de8564dc4a5aa98d013` 的 [Verify 37108302750](https://github.com/wpuu/MedicalChannelAI/actions/runs/37108302750) 执行 865 Python 测试，2 项旧 AST 分派测试因新增周期保护 wrapper 提取范围改变而失败。仅修正两项测试提取 `_run_stage` 并保留 wrapper 委托断言，12 项分派定向检查通过，产品冻结源哈希不变。必要修正集中补推一次，未手动重跑 CI、未重复部署；最终结果在 PR 检查与 PR 描述按精确 HEAD 回读登记。

## 时段、幂等与数据保护

- 候选 Cron：`20 0 * * *` → `?period=morning`，`20 4 * * *` → `?period=noon`；北京时间名义 08:20 / 12:20。每条每天一次，不使用一个 `20 0,4 * * *`，不升级套餐。
- [官方 usage-and-pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)，2026-10-03 实际读取：各套餐最多 100 个 Cron；Hobby 每个任务每天一次、小时级精度（±59 分钟），文档例子为小时内任意时刻。技能中“最多 2 个”过时。[Queue concepts](https://vercel.com/docs/queues/concepts) 与 [Python SDK](https://vercel.com/docs/queues/python-sdk) 同日读取确认 cap 控制 push dispatcher 的组内在途数量，满额直到 ACK/lease 到期才再投递；官方 JSON schema 确认 v2 trigger 支持 `maxConcurrency`/`maxDeliveries`。实际账号套餐仍未知，不能把文档条款当成该账号已核验的套餐。
- 周期由中国日期与明确 `period` 标识，早间和午间独立；入口接受 08:00–10:00 / 12:00–14:00 的恢复容差窗口（右端不包含），窗口不是准时承诺。首次真实触发时间冻结为 `cycle_as_of`，重试不改变；小时初触发不会制造未来版本时间。所有 stage 使用相同周期时钟，但 RUNNING 租约使用真实 wall clock。
- 同周期开始和各 stage 的 Queue key 保持幂等；已结束周期不重新发送。活跃 RUNNING 重复投递返回冲突；明确超过 300 秒函数上限＋60 秒缓冲后才允许重试。周期重试额度各自独立。
- 新消息携带 `schedule_version=twice-daily-v1`。旧格式 deep、incremental、tick 仅确认不执行、不续链；任何自动增量分支关闭。完整或失败 deep 终点不再启动 15 分钟链；手动 incremental 入口拒绝。
- 执行前、canonical/status 写前、持久发布前、读缓存提交和回滚前检查周期所有权；状态比较也包含 `cycle_id`。旧日消息丢弃，同日旧周期不能覆盖新周期。v2 Queue 和 canonical namespace 保持；无新来源、地区或架构。
- 保留完整覆盖发布门禁、失败保留旧公开版本、canonical/缓存保护、durable 单调版本事务门禁、AI 版本/来源绑定。数据库和 Runtime Cache 没有跨存储事务；durable 已接受但缓存失败仍需线上验证读恢复。
- Runtime Cache 无 CAS，不能把读后写 fence 称作分布式原子锁。依赖官方 push group 在途串行上限：候选 decorator 和 JSON trigger 均显式 `maxConcurrency=1`，消息 lease 与 retry interval 改为 360 秒，大于函数 300 秒上限；发布前必须排除旧部署消费者和仍在途函数。该控制面门禁未满足时禁止恢复执行。

## 独立审查发现与修正

审查复现两个并行 handler 绕过 Queue cap 时可同时首次读取空 META 并执行相同 stage；这说明缓存读后写不是锁。候选显式修正部署 trigger 串行 cap 与 360 秒租约/重试配置，保留实际控制面串行、旧 consumer 排除与在途结束为硬门禁，不能用此文声称任意并发 exactly-once。审查另验证 durable 返回间 lease 切到午间时，早间失败仍准确 `durable_accepted=true`，回滚不覆盖午间缓存。新测试也覆盖已接受重复 Queue key 的 SDK 异常，真实发送失败继续重试。详见 [独立审查](evidence/twice-daily-20261003/independent-review.md)。

四项 Node 发布/AI 行为检查通过：publish-preflight、publish-durable-base、partial-coverage-ai、ai-decision-provenance；网络/数据库为替身。TypeScript 与 Vite build 通过，未运行 prebuild 以免再次运行全历史矩阵或改写 bundled snapshot；完整候选 CI 由一次推送执行。

## 本轮线上只读结果与未知项

已有连接成功读取 Vercel 团队、MedicalChannelAI 项目列表、部署列表和部署详情。目标项目 `prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM`，团队 `team_jEy8Ex9vRDBdXj1cQPKF8sRd`。当前生产别名对应 `dpl_DW5wrMzvVXS7TLmbqUL1vSfcyuh1`，READY，主线 `62299590dd3898e040ccc9db5fda1298d4509d51`，不是候选。

`get_project` 按公开 schema 传 `projectId` 后，后端报缺 `idOrName`；按报错传 `idOrName` 后，连接器外层移除该字段并报必需 `projectId` 缺失。这是此单个工具外层/内层参数契约冲突，不是 Vercel 全部不可访问。团队列表没有返回 billing plan；现有可用工具没有返回 Cron enablement 或 queue consumer/backlog/in-flight/delayed retry 控制面清单。本轮环境无配置好的 Vercel REST/CLI 凭据，不读取或猜测令牌，不进行额外登录。

近 24 小时生产部署 `collector` 日志查询成功但无记录，不能据此认定 Cron 已停、消费者已停或队列为空。只读 `/api/collector-status` 返回 active cycle/scan 为 null、stages/ledger 为空；缓存过期也会产生同样结果，不能证明没有在途或延迟消息。只读 `/api/status`：旧提交 `6229959`，DATABASE，版本 `2026-10-02T14:19:15.713282+08:00`，441 条；旧版本 `ready=true/degraded=false` 不证明候选完整覆盖或搜索已恢复。两条 GitHub 采集入口回读仍为 `disabled_manually`。

国内域名/天津 403 的历史阻碍单独保留，未改 DNS、不绕访问限制；本轮不新增国内网络证明，代码候选整理可继续。

## 发布前门禁（需要控制面读取；本轮未执行配置变更）

1. 精确候选 HEAD 的 Verify 成功、独立审查无未解决阻断；PR 为 draft，先冻结预期 merge HEAD 和生产旧部署/配置/最后已验证数据版本、revision/hash。
2. 读回实际 billing plan、两条每日 Cron 配置是否可接受和启用状态；不升级。取得可操作控制面后，先暂停 Cron 与所有旧/新 consumer，GitHub fallback 保持 disabled；记录配置回读，不凭日志无记录推断已暂停。
3. 读取 v2 topic 的注册消费者及 deployment 归属、ready/in-flight/scheduled retry 数量与最晚可见投递。等在途函数超过最大时限＋缓冲并确认结束；旧消费者不能再订阅或写。保留旧积压，不清空队列；部署后只允许新消费者接收，旧 payload 在新处理器被隔离确认。旧部署直接回退时它会接受旧 payload，因此消费者在回退全过程保持暂停。
4. **长暂停 canonical 恢复是硬门禁。** 只读检查所有 canonical 分片、notice events、watch 与最后真实 durable snapshot 的一致性。全部缓存过期时本候选禁止用旧种子/内置快照初始化，明确失败 `COLLECTOR_CANONICAL_HISTORY_UNAVAILABLE`。public snapshot 投影不足以反推出完整 canonical，不能复制快照伪造历史。只能从可验证完整 canonical 备份恢复，或在另行明确授权的真实完整来源重建后逐来源核验；缺任何必需历史时继续暂停，不伪造空数组，不宣称可自动成功恢复。本轮未证明备份存在，也未执行重建。
5. 读回发布/CRON 凭据配置、canonical 完整性和现有消费者串行设置；确认 snapshot/status 只读路径可用。权限、字段读取或 canonical 任何硬门禁未解决，不进行合并发布或恢复采集。

## 一次受控发布与验收

上述前置门禁满足、用户批准后，针对冻结且 CI 成功的 PR75 HEAD 合并到 `main`，只产生一次正式 Production 部署；main 现有 Git 集成会部署，不另外创建 Preview 或重复手动 deploy。Cron/消费者仍保持暂停直到实际新生产 commit、artifact、配置、canonical 与读路径核对通过。

先核验 `/api/status` 的新 commit、旧数据还可读、Today/Pool/Detail 显示的版本和 AI cache-only 绑定；不要调用模型生成来验收。开启仅新 deployment 的串行 consumer，旧积压隔离结果与无自动 tick continuation 可回读后，在一个匹配时段只启动一个当前新周期（需要发布审批覆盖此真实采集动作），不补跑旧周期。核验全 stage 完整门禁、同周期重试、durable 接受、cache readback 与页面同一版本/完整覆盖；失败保留旧数据，停止自动恢复，不把 HTTP 202 当搜索成功。确认早间和午间分别形成独立 cycle 并通过实际完整门禁后，才可称“每日两次搜索恢复”。随后按批准范围恢复两条每日 Cron，保留 GitHub fallback 关闭。

## 失败、回退与恢复

出现版本倒退、覆盖不全误放行、canonical 缺失、消费者重叠、在途旧写入、异常耗量或 cache/durable 分歧：先停两条 Cron 与全部 consumer，等待并读回在途结束，保存 cycle、去敏感诊断、durable/cache 的版本/revision/hash。不清队列或直接恢复旧 consumer。

将生产别名回退至已记录旧 READY 部署 `dpl_DW5wrMzvVXS7TLmbqUL1vSfcyuh1`（若生产此前变化须重新确认）；只回退代码/别名，不自动回写旧数据库快照，不覆盖较新的已接受事实。核验实际旧 commit、最后已验证数据可读、页面降级/版本与 AI 绑定；旧代码的健康状态字段不能当候选门禁证据。回退后两条新 Cron 和所有消费者保持暂停，确认没有新 stage/tick/模型调用。修复在候选分支离线复验，再申请一次明确恢复；不得靠恢复旧 15 分钟链或补跑历史消息掩盖失败。

## 审批对象

批准对象是**指定 HEAD 的 PR75 一次合并＋一次 Production 发布，以及通过门禁后的单一当前周期受控恢复**；不包括付费升级、Preview、清队列、任意补采或模型调用。此文没有授予发布权限。本轮只准备候选，控制面、canonical 恢复与两周期线上验收未完成。
