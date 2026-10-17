# MedicalChannelAI current state

Updated: 2026-10-17。`production_ready=false`，**发布门禁BLOCKED**；每天两次搜索尚未恢复。最新生产与发布/回退依据是[10月17日续核验](../ops/release-readback-20261017.md)，10月3日记录保留为历史。

MedicalChannelAI 是天津起步的医疗器械、IVD、耗材公开情报和单用户销售助手。公共事实必须有官方证据，模型不创造事实；客户私有资源与公共情报分离。

## 候选与实际生产

- 基础草稿[PR75](https://github.com/wpuu/MedicalChannelAI/pull/75)：`fix/tjmugh-verification-20261002`，HEAD `a2131e4733939e07b9531ea4626c9378e0826953`，未合并。产品祖先8b4b749有879项及完整构建历史CI，不能转移给不同产品代码。
- 实现草稿[PR78](https://github.com/wpuu/MedicalChannelAI/pull/78)：`fix/twice-daily-source-parity-20261017`，产品冻结`c0d0215d99a8f109cfe62a313f0bf6daf9d8a771`；本轮仅保存只读证据/文档，最终文档HEAD从PR读回。base是PR75分支，合并它不会直接更新main；未来须先整理成一份目标为main且验证通过的最终候选，才能提出一次合并/一次Production审批。PR74/76/77不混入。
- GitHub main与**实际生产提交**均为`3216fd940dabfa7714383b6436908f9b72ff8a9c`。10月17日别名GET、部署详情和公开status一致：`medicalchannelai.vercel.app` → READY `dpl_4LPKoTdusrvbExXuzbMKtnyiT86C`、iad1。旧6229959/dpl_DW5…是10月3日历史，不能继续当当前生产/默认回退目标。
- 生产status为DATABASE、STALE/degraded；版本`2026-10-07T08:27:29.025919+08:00`，437条。可读不代表自动更新成功。上述READY只是代码回退候选，仍须核验隔离/兼容性；回退不得覆盖较新数据库事实。
- 两个候选分支配置`deploymentEnabled=false`；本轮无合并、部署/Preview、Cron/consumer变更、Queue receive/ACK/purge、部署删除、真实来源采集、模型调用、账户/安全变更或付费升级。

## 离线实现与验证

[三源离线核心](../ops/source-parity-offline-20261017.md)复用六个既有parser、stable ID和三个独立v2历史key；准备不写入，提交绑定cycle/base、保留历史、无主动TTL。缺失历史、失败、超限、旧周期或base变化阻断，不seed/bootstrap，不把Runtime Cache读后写称CAS。

[取页与索引保护](../ops/source-transport-index-20261017.md)已实现：同函数内短生命周期子进程请求/回收、20秒请求与240秒source共享预算、重试/间隔/URL/大小/编码约束，以及指定列表结构、顺序、identity和窗口起点检查。**官方结构注册表为空**，仅单页检查，不猜selector/分页。目标Vercel打包、spawn和清理行为未验收。

仍22stage，三源没有接入正式driver/必需列表，仍history-only、coverage partial及AI限制。设计期望25stage不是产品事实；synthetic HTML/mock/hash不是官方来源证明。

- c0d0215已有32项新增＋132项相关，共**164项本地离线PASS**；此前132项是17ed861阶段，不重复累加。证据明确区分父进程禁外连和仅stubbed网络的本地子进程。
- 本轮产品/测试/配置未改，测试重跑**0项**；不重复164/879及历史矩阵。c0d0215远端Actions为0，完整新产品Verify及独立审查仍未完成。保存后读回文档HEAD和检查，不把本地测试或祖先CI称新HEAD CI。
- 8b4b749历史[Verify37117043888 SUCCESS](https://github.com/wpuu/MedicalChannelAI/actions/runs/37117043888)、98项定向和终点竞态审查保留原提交归属。原patch/85项日志在当前环境缺失，不声称已读；更早840/865/870/875项不代表当前候选。

## 当前线上差异与未通过项

公开池437条ID唯一、rank连续；相对实际生产commit内441条静态文件，缺4条旧采购意向、无新增ID，且437条均缺`market_code / market_name / market_admin_code`。428个共同ID的rank不同，但版本时钟不同，不能仅据此判排序错误。公开遗漏不证明canonical已删除。PR75已有历史读取/投影最小修复，尚未上线；不临时扩展代码、不把旧公开卡片或快照回填数据库。

`get_project({idOrName,teamId})`现已成功，旧schema错误不再是本入口阻碍。团队/项目未返回billing字段；runtime logs API明确按Hobby保留期拒绝24h查询，改30m成功无collector记录。记录API报告的Hobby和billing页面未读回两个事实。部署文件树和旧observability schema各404，不是整个连接不可访问。无可用本地Vercel CLI/现成认证入口，不索要新token。

仍缺：实际Cron列表/enabled及暂停持久性；所有deployment/region/topic/group消费者身份、实际cap/lease及其他订阅者；ready/in-flight/delayed/expiry和有效停投递；完整canonical/history/events/watch/staging及published baseline与真实durable版本/hash的库存。active=null、stages空、15分钟策略/chain=null及30m无日志不能证明旧链已停或队列为空。GitHub fallback的disabled_manually只有10月3日历史，本轮workflow GET被包装器拒绝。

三个旧来源必须保留历史及准确partial/AI限制。旧911canonical/441静态审计是历史候选，不能覆盖当前10月7日版本、最后未发布事实和暂停缺口；禁止Git/seed/bundled自动恢复、伪造空数组或推进observed_at。

PR75保留早午独立、同周期幂等、终点标记与旧周期fence，候选不自动启动15分钟链。恢复不能手删ACTIVE/META或强开旧早间任务。Runtime Cache无CAS，必须排除旧部署/旧在途，不能靠代码配置证明线上串行。

## 发布边界与下一步

官方Queue按deployment分区，alias/rollback不停止旧投递。先证明旧分区隔离或在真实expiry/函数时限后复读静默，保护旧READY回退目标。若失败停止只能删除部署，未来审批须明确仅删除本次新建失败部署，先恢复已隔离旧READY alias，再停止新分区并等在途结束；不得删除旧目标或回写旧snapshot。完整顺序见[最新核验](../ops/release-readback-20261017.md)，当前不可执行发布审批。

门禁全通过后，针对最终精确HEAD申请一次合并/一次Production；调度保持停止先验收一个当前真实周期，再按批准范围启用两条各每日一次Cron，观察另一时段自然周期。北京名义08:20/12:20，UTC `20 0 * * *` / `20 4 * * *`，Hobby小时级精度，不依赖精确到点。未完成两个独立周期线上验收不得声称每日两次恢复。

**下一步**：取得已有官方索引/正文存档与真实分页、现有账户Cron/Queue/canonical只读读回；注册经审查contract后再接25stage并验证新产品。资料缺失时保留阻断，不重复造mock/报告或申请上线。建议 **GPT-6.1-sol · xhigh**；固定字段归档可用high。天津403和国内域名访问单独待验，不改来源地区、DNS或架构绕过。
