# MED-ACTION-P0-001：三源离线准备/提交核心

日期：2026-10-17。状态：**OFFLINE_CORE_ONLY / NOT_ACTIVATED / RELEASE_BLOCKED**。

> 后续补丁已实现[请求deadline与单页索引保护](source-transport-index-20261017.md)，本报告132项证据仍绑定17ed861阶段；最新结果见后续报告。本报告“尚未实现”是当时范围，不能当作后续补丁状态。三源仍未激活，官方HTML/结构注册、目标平台验证和正式接线继续阻断。

分支：`fix/twice-daily-source-parity-20261017`。起点：PR75 `a2131e4733939e07b9531ea4626c9378e0826953`。PR75保持原HEAD，本批以独立草稿叠加，不混入PR74/76/77。最终精确提交及草稿编号在远端读回/交接登记；任何旧HEAD批准不继承。

## 已完成的产品范围

- 在`web/collector_runtime.py`增加三个来源的内部薄适配、窗口证据约束、整批准备和受周期/base约束的提交核心，直接调用六个既有discovery/detail模块及其stable ID，不复制parser。
- 复用三个已有v2 key，明确intent的stage下划线/source连字符映射；schema、stable ID、source及天津market校验，缺键/坏历史阻断，不读seed/live文件自动初始化。
- 准备阶段不写缓存；任何未知核验错误、后续详情失败、超过3条候选或调用内预算耗尽时没有半source提交。提交前重新检查周期、终点状态和base内容，重复提交幂等；不设置主动TTL，写后读回异常不盲目覆盖为旧数组。read/check/write不是CAS，不宣称消除了任意并发。
- 保留未重新核验历史的observed_at；源级扫描时钟与canonical实际变化分开。现有四条intent保留；现有发布流程、partial、history-only、AI限制及旧周期终点保护不改。
- 仅为本实现分支增加`deploymentEnabled=false`；原两个Cron和Queue配置不变。

**没有注册三个新stage。** `STAGE_ORDER`仍22项，旧增量allowlist不变；原调度入口不会调用这个核心。25stage及源级history-only升级仍是下一阶段目标。这样不会把尚未验证的索引覆盖/请求时限接入发布路径；本批不是可上线修复。

## 离线验证

运行：`python docs/ops/evidence/source-parity-offline-20261017/verify_focused.py`。

该脚本阻断socket.connect、connect_ex、create_connection；真实缓存、Queue send、durable接受均用内存替身。25项新增核心回归，加107项受影响的早午周期、终点竞态、native可靠性、namespace及六个adapter回归，共**132项PASS**。日志：[focused.log](evidence/source-parity-offline-20261017/focused.log)，精确文件hash及模块计数：[manifest.json](evidence/source-parity-offline-20261017/manifest.json)。未重跑879项历史矩阵，没有新HEAD完整CI或独立审查通过的声明。

首次新增22项运行有3个fixture错误：妇产最小构造HTML缺少既有parser所需的“时间”标签，或把截止日期误作发布日期。只修正构造fixture格式，不改parser/日期门禁。随后新增发布链、写前周期切换和过期样本回放边界，最终25项新增检查通过。

HTML均标为**synthetic/mock契约样本**，不是保存的官方原始网页。9/28样本的标题/截止来自已有任务证据，不把它冒充本轮抓取。历史窗口回放核验MARKET_RESEARCH及2026-10-09 16:00 +08:00；10/17回放公开池不包含这个已过期机会。9/30数据安全在discovery被正常排除；妇产非医疗详情作为non-fact处理，不算整源失败。

## 尚未实现，不能据测试推断通过

1. **真实请求总deadline**：本核心没有网络transport、重试或详情间隔实现。240秒检查始于prepare调用，外部提供的index_html在此之前如何取得不在计时内；detail reader返回后能拒绝已超预算结果，但不能取消仍阻塞的请求。现有socket timeout不等于整次请求上限，不能据mock时钟或本批测试宣称300秒函数预算已解决。
2. **索引完整覆盖**：`OfficialSourceWindowProof`仅为内部待接适配器输入，hash只绑定页内容，不认证覆盖范围。没有生产代码构造该proof；也没有HTTP参数/公共API可提交它。测试自行提供mock范围证据，不证明实际索引已完整覆盖30日或暂停缺口。必须补可追溯范围验证，不能将用户可控boolean当作证明；超过3条时不能静默截断成功。
3. **内存准备对象**：`PreparedOfficialSourceRefresh`是同进程内部对象，冻结字符串不提供认证、跨进程游标、持久接续或事务；不序列化成Queue恢复协议。本批没有借此声称PR76北京真实接续已完成。
4. **生产接线**：只有完成上两项，才可把三stage加入顺序、必需列表和分派，验证25stage发布契约及准确源级coverage。当前仍history-only/partial，不能称已有三源每天两次更新。
5. **上线证据**：实际套餐/Cron enabled、消费者identity/cap、各部署ready/in-flight/delayed/expiry、完整canonical/baseline/暂停缺口、有效停止/回退方式仍是硬门禁。本轮未重查Vercel生产，不把10月3日或10月7日历史观测写成今日状态。完整产品HEAD验证及独立审查留待接线完成。

## 保存与操作边界

本地`gh pr view`返回401，但已有GitHub连接正常读回PR75=`a2131e4…`，Git推送通道也可用；不登录、不索要token、不改凭据或安全设置。隔离分支禁用部署，保存提交使用`[skip ci]`；本地132项不是远端CI。

不合并、不部署/Preview、不启停Cron/consumer、不receive/ACK/purge、不删除部署、不恢复canonical、不触发真实采集或模型、不新增付费资源。旧alias回退不停止Queue投递的风险仍按[既有方案](release-preflight-20261003.md)处理，不因本离线核心而解除。没有授权删除旧生产或回退目标。

**下一步**：限定范围实现/验证绝对请求deadline与可追溯索引覆盖，再注册三个必需stage及coverage映射，完成新产品HEAD的必要完整验证和独立审查。推荐 **GPT-6.1-sol · xhigh**；不提前激活来源或开始真实采集。
