# 官方页面编码与列表适配离线修复

状态：**OFFLINE_FIXES_VERIFIED / SOURCES_NOT_ACTIVATED / RELEASE_BLOCKED**。分支`fix/twice-daily-source-parity-20261017`、草稿PR78；起点`dd97beedcd7ef3ec8c1eb91fdef4780afbbea883`，最终精确HEAD按保存后远端读回。PR75保持a2131e4，旧提交批准/完整CI不继承。

本轮复用10月17日明确批准取得的4份本地原文；新增来源HTTP请求0，没有重新抓取、分页/JS请求、原文上传、产品采集/模型调用或线上操作。工作区资产及raw hash已核对，未声称缺失资产存在。

## 实现与保护

- `collector_official_transport.py`新增受限编码选择：只在最初8192字节的head范围解析meta，支持HTTP charset、HTML5/meta http-equiv及UTF-8 BOM，规范化明确允许的UTF-8/GB2312/GBK/GB18030别名。声明冲突、未知/空/重复歧义声明或解码错误均阻断；不替换坏字符、不尝试猜码。不把注释、script文本或body中的假meta当编码声明，保留既有响应字节、类型、时限/重试保护。新冲突原因可从子进程原样传回且不作瞬态重试。
- `collector_official_index.py`保留原simple-list行为，新增两套**捕获模板的离线shape**。二附院定位唯一公告td及固定table行/分页占位结构，妇产定位`ul#xwzx-list`和其table包装；仅处理实际已观察到的CMS重复链接/两个位置的多余引号。按逻辑行提取；相同href只可在该行指定嵌套位置出现，跨行重复stable identity、异域/不同href、额外锚点、未知/重复/空/未闭合结构仍拒绝。树深48、节点4096、标题长度及已有页面大小受限。
- 这不是通用HTML修复器。结构/属性改变时阻断，不扩大为全页搜索，不让侧栏旧链接补足窗口；分页script仅核对已观察到的静态标记，不执行或请求。
- `captured_index_shape()`只返回模板描述，**不注册官方contract、不产生覆盖证明**。正式`verify_registered_source_window()`继续先要求已审查登记；注册表仍为空。完整30日检查、future notice/倒序/hash/周期门禁不放宽。
- 没有改六个既有parser、collector runtime、STAGE_ORDER、MAX_DETAILS=3、canonical key、Queue/Cron配置或AI保护；仍22stage、三源history-only/partial。此补丁的产品blob已与c0d0215不同，不能再宣称494条产品tree与祖先一致。

## 必要检查与真实原文回放

运行[evidence/verify_focused.py](evidence/source-capture-fixes-20261018/verify_focused.py)：**20项新增＋57项相关，共77项PASS**，2.224秒。新增9项编码、11项列表/资源边界；相关为既有transport19、index13、source core25。父进程socket连接禁止；旧transport子进程检查仍仅使用stubbed DNS/body及本地计时，没有真实来源请求。没有重跑164/879或其他历史矩阵，完整新产品Verify及独立审查仍待完成。

新增覆盖：缺HTTP charset的GB2312、支持编码/别名/BOM一致、header/meta冲突与歧义拒绝、扫描边界、子进程错误传递；三stage对应模板、侧栏隔离、跨行/alias重复、嵌套href不一致、未知结构/内容、乱序/未来/无效日期、有限CMS引号例外、分页不作覆盖证明、树深/节点限制、shape不能注册或变更source。资源上限测试先用了不足4096节点的样本，已改为确实超过上限的600行并区分depth/nodes；没有放宽产品限制。

运行[replay_captures.py](evidence/source-capture-fixes-20261018/replay_captures.py)，必须显式指定现有本地目录，缺文件/hash不符即失败，无抓取fallback：

```bash
python docs/ops/evidence/source-capture-fixes-20261018/verify_focused.py
python docs/ops/evidence/source-capture-fixes-20261018/replay_captures.py \
  --captures /workspace/.medicalchannelai-onboarding/MedicalChannelAI/official-html-20261017
```

4页由修复后的decoder解码，UTF-8内容hash与10月17日诊断逐页相同；妇产GB2312缺口已修正。二附院research/intent均识别20个逻辑公告，妇产10个；诊断scoped discovery计数仍2/14/1。三者按**真实捕获日10月17日**检查9月18日开始的窗口，均返回`OFFICIAL_INDEX_WINDOW_NOT_COVERED`；正式注册入口均返回`OFFICIAL_INDEX_CONTRACT_UNVERIFIED`。没有把旧页当10月18日的新观察，也没有伪造window、调用stage或写canonical。四份原文仍只在本地，Git保存脚本/结果/log/hash，不声称裸仓库有原文或完整新CI通过。

## 续批门禁审阅：需要实现，当前不启用

第一张索引已有14条intent候选，3条/批至少需要5批；候选范围还未完整，14不是全窗口总数。把上限改为14或截前三均不能满足现有预算和完整覆盖要求。**本轮不实现新的cursor/暂存/发送协议**，也不声称已有原子游标；下一实现须在既有Queue内满足：

1. **先固定真实窗口与清单，再开始批次。** 必须有真实分页/终点、跨页顺序/唯一identity和完整范围证据；manifest绑定source、cycle/anchor、窗口、页面内容hash、候选ID/URL/标题/顺序、历史base摘要及版本。没有真实分页证据时manifest不能成为可完成状态，不从当前14条推定全部、不能把历史fixture当新周期观察。
2. **每次最多3详情，共享该次函数预算。** 消息绑定manifest hash/版本及批次位置，同一批重投有稳定dedupe键；现有串行/lease/retry和旧部署排除仍是前提，不能把多个handler读后写称CAS。重试不能无上限重抓或重置本次预算，未知/过期/manifest不一致消息拒绝，不借新服务/地区/付费资源解决。
3. **整源完成前只暂存，不更新canonical。** 每批核验结果/已确认non-fact及进度须可读回且绑定清单；全部候选恰好有结论、没有失败/遗漏后才合并完整历史并一次提交。任一批失败保留原canonical/公开版本；不能每批覆盖源数组，再把半源写入包装成失败保护。缓存逐出或进度不一致必须阻断，不初始化空manifest/空历史续跑。
4. **旧早间批次不能写午间。** 每次读取/暂存/入队/最终提交前检查当前cycle/anchor及manifest归属；terminal/旧消息不清除新状态，不删ACTIVE/META或强开旧周期。全部完成才可将该source stage标COMPLETED，最终发布仍要求所有配置stage及准确coverage/AI版本门禁。
5. **有明确失败与恢复验收后再接driver。** 测试至少覆盖批间中断/重投、丢失/损坏暂存、清单改变、同一候选重复/缺失、旧早间在午间期间返回、预算/队列发送失败和最终base变化。完整历史/真实published baseline与durable/cache不一致时仍阻断；不得复制旧公开快照补状态。实际消费者、旧分区及数据恢复门禁未读回前，即使离线协议通过也不能启动。

以上是实现前约束审阅，**不是独立审查完成或已经生效的续批能力**。现有核心仍按整源最多3条阻断14候选；续批状态如何保存/失效与最终提交的故障边界须在实现中具体证明，不假称Runtime Cache有持久CAS。

## 保存与下一步

同一草稿PR78集中提交推送一次，`deploymentEnabled=false`、commit用`[skip ci]`；新HEAD CI/部署须另读回。不合并、不部署/Preview、不恢复调度/consumer、不收取/ACK/purge、不删部署、不写线上数据。生产、套餐/Cron/Queue/canonical库存的[最近只读记录](release-readback-20261017.md)保留10月17日原时间，本轮未重复查询或填为通过。

下一步：在不激活的分支实现并验证上述既有Queue内的manifest/批次暂存/整源提交协议；实际分页取证不在已用完的4页授权内，不能自动追加或猜路由。完整25stage、官方contract/历史配对、目标Vercel打包/子进程验收、完整新产品验证/独立审查以及线上控制面仍阻断发布。建议 **GPT-6.1-sol · xhigh**，每天两次搜索尚未恢复。
