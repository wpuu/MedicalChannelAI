# 10月17日生产只读续核验

状态：**RELEASE_BLOCKED**。本轮只读线上核验、保存证据和修正文档，产品代码与配置不变，测试重跑0项。

## 精确对象与新证据

- 实现草稿[PR78](https://github.com/wpuu/MedicalChannelAI/pull/78)开始及核验时HEAD为`c0d0215d99a8f109cfe62a313f0bf6daf9d8a771`，仍draft/open/unmerged；基础PR75保持`a2131e4733939e07b9531ea4626c9378e0826953`。本轮文档保存会产生新HEAD，最终精确SHA从远端读回；旧HEAD批准不继承。
- **当前生产已变化**：`medicalchannelai.vercel.app`别名实际指向READY `dpl_4LPKoTdusrvbExXuzbMKtnyiT86C`，精确提交`3216fd940dabfa7714383b6436908f9b72ff8a9c`、main、iad1、Git来源，创建时间`2026-10-07T07:42:29.650Z`。别名GET、部署详情和公开status的短SHA一致。10月3日6229959/dpl_DW5…仅保留历史，不能继续当作本次默认回退目标。
- `get_project({idOrName,teamId})`本轮成功；旧schema冲突已不再阻断这个入口。返回的`latestDeployment`是`dpl_FjZACpMQZfx4NDcww4nzHoJ6xyeN`、target=null，不能当Production；生产归属由上述别名和详情确定。团队GET也成功，但没有返回billing plan字段。
- 24h runtime logs请求返回400，API明确说 **“The hobby plan does not retain runtime logs for the requested time range.”** 因此记录实际API按Hobby分类，不再笼统写完全未知；不是billing页面直接读回。按建议改为30m后查询成功、无`collector`记录，窗口`04:58:13.666Z–05:28:13.666Z`。前一结果是查询失败，后一结果才是无匹配日志；两者均不能证明队列为空或消费者停用。不升级日志套餐。
- 部署文件树GET返回404 `File tree not found`；旧observability schema路径GET返回404 `Observability Data not found`。不猜指标、不从这些单项错误推断整个Vercel连接失效。GitHub workflow目录/具名GET被当前fetch包装器拒绝，未重试同类路径；两条采集workflow的`disabled_manually`仍只是10月3日历史读回。
- 本地三个checkout只找到应用/原型HTML；没有医院原始索引、分页或9/28、9/30正文。PR78评论为空，main最近提交仍3216fd9；没有新官方存档可供注册。官方结构注册表继续为空，仍22stage、history-only/partial及AI限制。

## 当前公开数据与具体差异

`2026-10-17T05:28:11Z`起，对生产域名仅GET `/api/status`、`/api/collector-status`、`/api/public-snapshot`各一次，均200；未访问采集入口或医院网站，未调用模型。

| 项目 | 实际读回 | 含义 |
| --- | --- | --- |
| 数据来源/时间 | DATABASE；`2026-10-07T08:27:29.025919+08:00` | 不是10月2日旧441条基线；新候选也没有上线 |
| 可读/新鲜度 | ready=true、degraded=true、STALE，读取时age14700分钟 | 可读不等于自动搜索恢复 |
| 公开池 | 437条、437唯一`opportunity_id`、rank连续1–437 | 与status count一致 |
| 历史差异 | 相对同生产commit的`web/public/data/today-actions.public.json`441条，恰好缺4条intent，无新增ID | 四ID为`…030195986 / …030195988 / …030195991 / …030195992`，完整值在证据JSON；10月3日公开读回曾全部存在。公开池遗漏不证明canonical已删除 |
| 地区字段 | 437条均无`facts.market_code / market_name / market_admin_code`，仍有原始region | 静态文件具有6地区身份；当前运行态不能标注“地区字段与静态一致” |
| 排序 | 428个共同ID的rank与静态文件不同 | 两个真实版本时间不同，不能仅以此认定排序算法错误；本轮未重建/重排历史矩阵 |
| 覆盖 | `coverage_warning=PARTIAL_OR_SOURCE_SPECIFIC_COVERAGE_MAY_APPLY`；无结构化`collection_coverage` | 旧生产覆盖范围未知，不能用候选partial保护冒充线上已生效 |
| Collector | 22stage、active=null、stages空；15分钟tick策略仍返回、chain=null | 是缓存状态，不是Cron/消费者/Queue清单；不能据此说旧链已停 |

本次发现的是**旧生产仍暴露的历史遗漏/投影差异**，不是对未上线PR78的回归判定。最小代码范围已在PR75：严格读取三个独立历史key、完整published baseline/canonical门禁、复用静态分区/组合投影及地区metadata；已有相关检查不重复跑。尚缺当前完整canonical库存和可验证历史恢复依据，不能直接把四张公开卡片或旧441条写回数据库“修复”。未来新周期必须保留canonical历史，公开展示则遵守真实生命周期，不要求过期记录永久展示。

## 逐项发布门禁

| 门禁 | 结论 | 尚需的验收证据 |
| --- | --- | --- |
| 精确生产归属 | READ_BACK | 当前3216fd9与别名已绑定；执行前再冻结READY目标及数据版本/revision/hash |
| 套餐/两个每日任务 | PARTIAL | API按Hobby分类；billing字段未返回。沿用两个独立每日任务`20 0 * * *`、`20 4 * * *`，北京名义08:20/12:20，小时级精度；不是线上列表/enabled证明 |
| 实际Cron及其他入口 | BLOCKED | 现有返回无Cron配置/enabled/暂停持久性；GitHubfallback本轮状态未读回 |
| 唯一串行消费者与旧分区 | BLOCKED | 每个deployment/region/topic/group身份、其他订阅者、实际cap/lease/retry/函数时限、ready/in-flight/delayed/最晚expiry及复读静默证据均缺 |
| canonical与历史保留 | BLOCKED | 完整源级canonical/history/events/watch/staging及最后真实published baseline库存、schema/ID/hash/时钟与durable一致；旧911/441审计不能覆盖10月7日后状态或暂停缺口 |
| 早午状态保护 | OFFLINE_EVIDENCE_ONLY | PR75既有fence、终点重投及回滚证据保留；不得删除ACTIVE/META或强开旧早间周期，旧消费者仍必须排除 |
| 三源正式集成 | BLOCKED | 原始HTML/真实分页、注册contract、25stage driver、目标Vercel打包/子进程验收、完整新产品验证及独立审查尚缺 |
| 发布/失败停止 | BLOCKED | alias切换不停止deployment-pinned Queue；尚无旧分区静默或有效非破坏性停投递证据，不能执行发布 |

## 一次发布与回退范围（未获准执行）

1. 补齐以上门禁后才提出审批；重新冻结最终精确产品HEAD、main、实际旧READY部署和最新durable数据版本/revision/hash。PR78当前base是PR75分支，**合并PR78不会直接发布main**。未来要先整理成一份经验证、目标为main的最终候选，再申请一次合并＋一次Git集成Production部署；不能把当前堆叠关系说成已有一步发布条件。
2. 获准后先停止实际Cron及其他生产入口，核验暂停在部署后仍有效。按真实deployment/group隔离旧积压；不搬运、不receive/ACK/purge。没有已验证停投递机制时，旧ready/in-flight/delayed必须全0、expiry已知，等待实际函数上限＋缓冲后复读仍静默；缺任一项停止在合并前。保留旧READY回退目标，禁止删除它。
3. 仅一次合并及一次Production部署；核对新SHA/alias、实际唯一串行consumer、旧分区静默、helper打包/无医院外连的启动与退出、完整canonical及旧数据可读。检查失败时不启动首周期。目标平台验收与真实采集分别受审批范围约束，不另建Preview。
4. 调度保持停止时，仅在真实匹配窗口启动一个当前周期一次；验收全部配置stage、真实时间、canonical历史、地区字段、排序/版本、durable接受与cache读回、准确partial和AI版本绑定。202不等于通过；不调用模型、不伪造时钟、不手删周期标记重试。缺窗口就等下一真实窗口。
5. 首周期通过后，仅按同次明确批准范围启用两条各每日一次Cron；观察另一时段自然周期，不额外手动补采、不恢复旧15分钟链。两周期全部验收前不得声称每天两次恢复。
6. 任一步失败：先停Cron/所有入口，记录cycle/最后接受版本和队列各分区状态，保护canonical、队列和较新durable事实；使用事先验证的停投递方式并等在途结束。若只有官方删除方式，须预先明确批准**仅删除此次新建的失败部署ID**：先恢复受保护的旧READY alias（旧分区已静默），再删除失败新部署、等待实际函数上限＋缓冲并读回。禁止删除旧回退目标或回写旧snapshot。回退后核验alias/commit、最后已接受数据、partial/AI绑定及所有入口停止；任一无法验证不能标回退成功。

当前`dpl_4LP…/3216fd9`只是已确认的代码回退**候选**，不是数据恢复来源或通过全部兼容性门禁的承诺。回退代码不得把10月7日437条或10月2日441条覆盖到最后真实数据库。原详细[发布前清单](release-preflight-20261003.md)和[恢复清单](twice-daily-release-20261003.md)的10月3日事实按历史阅读，以本报告更新的实际生产为准。

## 证据、边界与下一步

[证据目录](evidence/release-readback-20261017)：control-plane.json为必要字段的规范化工具读回；status/collector-status保存原始JSON；public-readback.json保存HTTP时间/响应hash、池及静态对比；public-pool-projection.json仅保存437条ID/rank/地区投影。完整1.6MB公开响应仅在本地`/tmp/medicalchannelai-readback-20261017/public-snapshot.json`，不声称随PR保存完整原文；投影不是canonical备份。没有新增医院采集、数据库/RuntimeCache修复、账户或安全修改。

已有164项离线证据仍绑定产品c0d0215；本轮不重跑164/879或已通过的定向检查。c0d0215远端Actions为0，不标CI通过；文档提交使用`[skip ci]`，产品blob必须与c0d0215完全相同，保存后读回精确HEAD、CI及无部署记录。

**下一步**：取得已有官方HTML存档位置与现有账户的Cron/Queue/canonical只读读回；按真实结构注册contract后再接25stage并做新产品验证。阻碍未解除时不重复造mock或报告、不请求发布批准。建议 **GPT-6.1-sol · xhigh**；拿到证据后的固定文档归档可用high。
