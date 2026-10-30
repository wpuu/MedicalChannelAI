# MED-ACTION-20261030/C01｜MedicalChannelAI 真实客户价值差距审计

研究日期：2026-10-30（北京时间）
目标仓库：wpuu/MedicalChannelAI
执行范围：公开市场资料、GitHub 主分支及 Draft PR、Vercel 生产元数据、官方公告、现有生产公开快照
交付：本报告与同目录 C01_action_card_evidence.json
当前裁决：C01_RESEARCH_COMPLETED / PRODUCT_GAP_FOUND / COMMERCIAL_VALIDATION_NOT_PASSED
安全与执行：只读生产，不触碰密钥，不部署、不合并、不联系客户、不购买标书

重要说明：本报告中所有客户行动分类均为人工研究假设，不是 Agnes 模型基准测试，也不是资格审查或法律结论。某些项目来源只得到官方列表或者官方搜索索引摘要，已在 JSON 中分级标注，不得把这类证据提升成详细正文已经独立核实。

## 一、商业结论

建议继续 MedicalChannelAI，但现在不允许公开承诺“每天可靠、实时、高精度医疗采购行动雷达”，也不适宜启动真实收费试验。

原因按优先级：

1. P0 自动监控可信度不足。生产最后公开快照停在 2026-10-28 08:27 北京时间，10月30日核查时系统显示 STALE 和 degraded，pipeline-health 返回 503，collector-status 没有可读到的本周期 deep/chain/各源扫描成功证据。
2. P1 已收录公告缺产品级事实。天津第三中心医院东丽院区10月27日的四批检验科设备采购均已入库，四条 product_items 和 product_categories 都为空，并且 coverage_status=PARTIAL。第五批官方公告正文实际包含多采购包与明确设备名称，说明“有公告”不等于“能判断这家渠道商是否经营这件产品”。
3. 商业竞争严峻。剑鱼、千里马、泰茂等已公开展示定向订阅、AI 匹配、竞品监控、资格/投标辅助。第三方蓝燕云在同一条天津第五批项目已经提取具体设备、采购包、预算、最高限价、获取文件时间。抽取正文并推送只是市场基线，不可宣称独特。
4. 仍待验证的增量价值是：客户自身代理产品 SKU、厂家授权和地域经营范围的精确映射；项目包级别可做/待核/不做；报名窗口与已参与项目的不同处理；多个同院批次的去噪聚合；风险、费用及有效下一步。
5. 不存在本轮完成的真实客户付费证据，也未接入或复测 Agnes 的有效基准密钥。

决策：C01 通过“找到真实可复现产品缺口”门槛，但不通过“可以收费试用”门槛。下一步是 C02 隔离修复/验证，而非继续拓展全国信源和前端。

## 二、源代码与线上实际状态

### 2.1 GitHub

- main 最新提交：3216fd940dabfa7714383b6436908f9b72ff8a9c，提交日期 2026-10-07；截至本次核对未看到新的 main 提交。
- 历史 P0 隔离候选：codex/medical-action-p0-runtime-source-parity，HEAD b5e6cdfbc19a9f14b3b2e9a4622de86c206dd293，旧 Preview 771 tests 通过但尚无生产 Cron 完整自动链验收。
- 历史 P1：codex/medical-action-relevance-benchmark，HEAD b3dc84d3438d965dd1c6123457ca9a02555a7a42。以往人工 Gold Set 及测试不能替代现在真实客户测试；GitHub Actions 旧 Agnes Secret 曾 HTTP 401，而历史 Production 简单模型探针 HTTP 200，本轮没有再次复测。
- 2026-10-18 Draft PR #78：feat: 三源离线核心与真实页面适配（未激活），HEAD d158f8648db17b904300671b0f1ccbae795c324c；BASE 是 PR75 分支而不是 main；PR 说明三源仍 history-only，正式 25-stage 尚未接线，发布门禁 BLOCKED，双时段自动搜索未恢复。不能把它当已发布功能。
- PR #78 增加了实际 HTML 编码及索引行结构适配，但官方完整分页/窗口合同、整源批次状态与 3 详情上限等还未验收。
- 旧 P0 方案不可未经审查直接覆盖 PR78 的后续更严格安全约束。

参见：
https://github.com/wpuu/MedicalChannelAI/pull/78
https://github.com/wpuu/MedicalChannelAI/blob/d158f8648db17b904300671b0f1ccbae795c324c/docs/ops/source-capture-fixes-20261018.md

### 2.2 Vercel Production 只读检查

- 部署 ID：dpl_4LPKoTdusrvbExXuzbMKtnyiT86C；target production；READY；commit 3216fd9；区域 iad1。
- /api/status：ready=true、degraded=true、source_mode=DATABASE、snapshot_as_of=2026-10-28T08:27:29.111217+08:00、freshness=STALE、opportunity_pool_count=65。
- /api/collector-status：local_date、cycle_as_of、updated_at 均为 null；completed_stage_count=0 / total_stage_count=22；incremental chain=null；旧来源 last_completed_scan 都没有可读取记录。
- /api/pipeline-health：HTTP 503。
- 因此实际生产不满足“每日自动监控”的宣传要求。
- 仅凭数据库 10月28日更新不能断言那次是 Cron、GitHub Actions 或人工发布；根因尚未完成证据归属。
- 下次 P0 实测必须分别保留 cron trigger、Queue 接受、stage 开始/结束、每源 last_success、最终持久化快照读回证据。

只读状态：
https://medicalchannelai.vercel.app/api/status
https://medicalchannelai.vercel.app/api/collector-status
https://medicalchannelai.vercel.app/api/pipeline-health

## 三、真实公告与客户行动卡

观察时点：2026-10-30 北京时间下午。所有已经过去的文件获取或报名时间都不得写为“今天可报名”。

### 3.1 病理设备渠道商（Persona A）

A1：天津静海区医院医共体医学检验设备采购第3包。

- 官方公告2026-10-12；项目编号0615-2641032190995；第3包预算约63.29万元。
- 产品：组织包埋机、轮转式组织切片机、全自动组织脱水机、全自动染色封片机。
- 采购类别可能被表述为“临床检验设备”，但真实品类是病理相关，证实不能只依赖一级目录分类。
- 文件获取截止2026-10-19 16:30，开标2026-11-02 09:00。
- 10月30日行动：新用户默认 CLOSED_FOR_NEW_DOCUMENT_ACQUISITION；已参与用户继续 Followup；若有正式更正/合法例外须重新核实。
- 官方：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261012_27476215.htm
- 第三方同案：https://tj.zhaobiao.lanyancloud.com/notice/db973b9f8bfa4750

A2：解放军总医院全自动免疫组化染色机成交结果。

- 2026-10-29 官方列表出现“全自动免疫组化染色机项目成交结果公示（2026-JQ06-W3257）”。
- 正确生命周期是 AWARD_RESULT；对该产品渠道只能做竞品/中标跟踪，不得推为开放投标。
- 具体中标厂家、金额没有从详情独立核实。
- 官方列表：https://zbcg.301hospital.com.cn/admin-portal-proclamation.html

A3：上海嘉定区中医医院病理设备采购（地理负例）。

- 2026-10-28，预算约193万元，有包埋、脱水、切片、免疫组化等。
- 若客户业务范围仅天津/北京 → PASS_REGION；不能因为产品高度匹配就推销。
- 官方：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261028_27573424.htm

### 3.2 手术、消毒与消融设备渠道商（Persona B）

B1：天津市静海区医院医共体手术急救设备第7包。

- 2026-10-14，项目HYGP-2026-A-050，射频消融治疗系统，第7包预算约38.36万元。
- 供应条件包括不接受进口产品；实际许可、医疗器械注册/经营、生产或代理资格以官方采购文件为准。
- 获取文件截止2026-10-21 17:00，投标/开标2026-11-04 09:30。
- 10月30日新用户 CLOSED_FOR_NEW_DOCUMENT_ACQUISITION；已合法参与的渠道可跟踪答疑、投标、结果。
- 同一主项目有其他手术相关包，不能因为经销“手术器械”就默认有全部包的可投资格。
- 官方：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261014_27494080.htm

### 3.3 检验设备、试剂与耗材渠道商（Persona C）

C1：天津市第三中心医院东丽院区第五批检验科设备采购。

- 官方2026-10-27，项目XCSD-2026-A-939；总预算509.19万元，最高限价428.19万元。
- 官方正文有四个采购包，含全自动生殖道分泌物分析仪、血气分析仪、全自动化学发光免疫分析仪、血液分析仪、全自动尿液分析流水线、微生物样本前处理系统、生化培养箱、二氧化碳温箱等。
- 采购文件获取截至2026-11-03 16:00；投标截止2026-11-17 09:30。
- 当前 Action Now 仅意味着“如客户真的有对应产品/授权，应立即核对包次、经营资质及合法报名路径”；绝不意味着自动符合投标资格。
- 官方：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm
- 第三方同案：https://tj.zhaobiao.lanyancloud.com/notice/aa31dd3bf55b410e

C2：二附院微生物检验用培养基/培养液调研。

- 2026-10-09 公告；报名截至10月11日17:00；市场调研不是正式招标。
- 10月30日应仅历史跟踪，不能推当前报名。
- 官方：https://www.tjzyefy.com/system/2026/10/09/030199590.shtml

C3：二附院一次性无菌留置引流导管调研。

- 2026-10-26，报名10月30日16:00截止；本轮北京时间下午查询已经过期。
- 若客户做负压吸痰管，也不得把它直接判断成“同一商品”。
- 需要核对是否为天津医药采购中心入围厂家/供应商。
- 官方：https://www.tjzyefy.com/system/2026/10/26/030201578.shtml

### 3.4 应被压制的负例

- 二附院10月28日医院安防设备院内调研，虽然报名到11月2日16:30，但对三类医疗渠道商均为 PASS_NON_MEDICAL：
  https://www.tjzyefy.com/system/2026/10/28/030202117.shtml
- 二附院10月29日教学训练模型调研，至11月4日16:00；除非客户明确经销教学训练模型，否则不得因为“手术模拟”而推给卖手术器械的客户：
  https://www.tjzyefy.com/system/2026/10/29/030202182.shtml
- 北京301 10月29日列表同时有全自动核酸提取纯化仪谈判邀请及疑似同编号流标公示，须先做公告版本/状态核对，再决定是否可进入 Action Now。
  https://zbcg.301hospital.com.cn/admin-portal-proclamation.html

样本证据分级和人工预期输出见 C01_action_card_evidence.json。

## 四、最重要的同案“产品明细缺失”复现

从2026-10-28 08:27生产 public snapshot 检索到四个同院同日采购：

| 批次 | 编号 | 预算（人民币） | 获取文件截止 | 产品项数量 |
|---|---|---:|---|---:|
| 第一批 | XCSD-2026-A-942 | 2400万元 | 11月3日16:00 | 0 |
| 第二批 | XCSD-2026-A-943 | 983万元 | 11月3日16:00 | 0 |
| 第四批 | XCSD-2026-A-944 | 490.1万元 | 11月3日16:00 | 0 |
| 第五批 | XCSD-2026-A-939 | 509.19万元 | 11月3日16:00 | 0 |

四条均 coverage_status=PARTIAL、product_items=[]、product_categories=[]。

生产读取证据： https://medicalchannelai.vercel.app/api/public-snapshot

四条的独立官方 URL：
- 第一批：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27572315.htm
- 第二批：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27572314.htm
- 第四批：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27572316.htm
- 第五批：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm

至少第五批主公告已经包含明确的采购包及设备名称，不能因没有解析出产品项便让 Agnes 根据“检验科设备”猜测产品。

C02 应审计为什么 parser/collector 丢弃了正文中已经具备的采购包信息，先完成第五批的高置信产品级抽取，再检查其他三批及附件。

建议功能：
- 保留独立项目编号与官方来源；
- 每包独立产品名称/数量/金额或限价（只取有来源的字段）；
- 单个医院多个采购批次聚合成一条待办提醒，但不合并成一个采购项目；
- source span/evidence URL 可直接回原文；
- 报名/采购文件获取截止与开标分别处理；
- 对缺失的字段明确显示“未知/待人工核实”，绝不让 AI 填补。

## 五、竞品同案对照与收费理由

### 5.1 剑鱼标讯

公开超级订阅基础档约680元/年，全国订阅、区域/行业/关键词、微信或邮箱推送；高阶会员包含采购意向、监控和商机服务。官网宣传 AI 匹配与接近实时提醒。其公开 Open Platform 资料展示 AI/API/MCP 接入和用量服务。

https://www.jianyu360.cn/product/index?serviceType=0
https://www.jianyu360.cn/front/subscribe.html
https://www.jianyu360.cn/swordfish/page_big_pc/ai/doc/quick-start

价格和处理时延是官方营销/官网展示，未做外部独立测量。API/MCP 不等于授权第三方转售或免费使用。

### 5.2 千里马招标网

有 AI 语义/同义扩展、动态提醒、项目变更和竞品监控等公开宣传；不应将“AI筛选+提醒”称为我方独占。
https://www.qianlima.com/news/684.html

### 5.3 泰茂医疗器械招标网

医疗器械垂直定价公开为VIP1 9800元、VIP2 19800元、VIP3 29800元级别，提供医疗标讯、报名节点、申报和竞品服务，具体购买仍需问价核实。
https://ylqxzb.com/vip/remark.html

### 5.4 蓝燕云：同案已经做到了产品级提取

XCSD-2026-A-939 这条天津第三中心医院项目，第三方展示了产品、预算、最高限价、时间及相关条件。
https://tj.zhaobiao.lanyancloud.com/notice/aa31dd3bf55b410e

静海病理采购包的同案也公开列出病理设备：
https://tj.zhaobiao.lanyancloud.com/notice/db973b9f8bfa4750

因此 C02 的“产品项抽取 + 截止判断”是恢复市场基础能力，而非新增独家价值。

### 5.5 尚未核实的差异

本次没有进入竞品客户私有账户，没有付费登录，没有同一客户产品画像的平行实测，也没有比较同时间戳的入库与推送到达时间。因此：
- 不声称我方发现更早；
- 不声称竞品不能做产品/SKU级匹配；
- 不声称竞品无法识别文件获取窗口；
- 不使用竞品挂牌价格推算客户量或支付意愿。

只有同案并行测试，且实际客户认同“减少操作时间/避免错过项目/发现真正可跟进的包”，才算可售增量。

## 六、C02 的最小工程路线与验收

### C02-1 包级产品事实恢复

只选择四条天津第三中心医院同日检验科项目，优先第五批；不扩省份、不开前端重做。

对每个独立采购包抽取：
- 来源 URL、project number、package number；
- 原文产品名称、数量（若有）、预算/最高限价（若有）；
- 文件获取截止、投标截止；
- 国产/进口限制、医疗资质要求（若来源明确）；
- 若需附件，注明附件下载与使用条件；
- 原文找不到的字段强制 UNKNOWN。

验收：第五批官方正文可核对的产品信息至少95%召回，不能制造任何日期/金额/型号/许可证事实；三批未能读取的来源不得强行填报。

### C02-2 源级 freshness 和自动链

生产只读状态目前 STALE，故修复必须基于最新 PR78、PR75 的 source contract 和 fail-closed 规则，而不能简单用旧 P0 草案覆盖。

需能观察并保留：
cron_trigger_at、queue_accept_at、cycle_completed_at、每个source的last_success/last_error、snapshot_persisted_at/readback_at。

至少连续7天非人工触发运行，有可回源的新公告与失败告警，才考虑“每日自动”的商业表述。

### C02-3 客户经营范围与付费验证

最小客户信息：业务区域、3—10种具体产品、厂家/品牌或授权能力、不能参与的资质及产品情况。不得要求医院关系、底价等敏感信息为必填。

行动卡分级：
- ACTION_NOW（尚在合法文件获取/报名窗口，客户有明确产品匹配；仍需人工核资质）；
- PREPARE（采购意向/院内调研，标记真实生命周期）；
- WATCH（中标结果、已参与项目、竞争与更正信息）；
- PASS（非业务、非经营区域、客户明确无法参与、关键窗口已关闭）；
- NEEDS_MANUAL_REVIEW（包内产品/报名/资格缺事实，禁止 AI 作最后肯定判断）。

真实收费试验前置条件：
1. 最近7天源级自动化证据可靠，未靠人工刷新伪装；
2. 当前选定项目产品级召回≥95%，重大事实幻觉0；
3. 新发现项目与客户已参与项目的期限逻辑分开；
4. 明确无关推送≤5%，高价值漏报需逐条复核；
5. 至少三名真实渠道客户试用7天，至少一人按明确价格实际付款，且至少有一条提醒触发业务动作；
6. 数据来源许可、授权边界和客户私有数据处理合法。

如果技术条件未通过，则不拉真实付费试用；如果技术通过但真实客户不买，不继续堆功能，优先试 BYOS（客户自带合法来源/API/提醒）作为精简行动层。

## 七、最终裁决

C01 真实商业差距审计完成，找到可复现的同案产品缺口和生产 freshness 阻塞。

工程优先级：C02-1 包级事实和公开证据 → C02-2 可靠自动化 → C02-3 模糊相关性 Agnes/客户画像 → 小额真实收费验证。

但“可以收费”仍判 NOT_READY，不声称这次有模型实测或真实客户购买证据。

建议模型：GPT-6.1 Sol High；如果要跨 PR75/PR78 重建 source Queue cycle、窗口、部分提交和回滚安全合同，使用 Extra High。

本轮未改变 main、Production、账户、Cron、Queue、Secrets 或任何对外业务状态。


## 八、补充同案资料：三批产品及跨境聚合错误

本轮随后查到三个更多同批次的公开转引：

- 第一批 XCSD-2026-A-942，预算2400万元、最高限价800万元。公开转引采购需求出现全自动生化免疫流水线。
  https://tj.zhaobiao.lanyancloud.com/notice/451caeec538e4d4a
- 第二批 XCSD-2026-A-943，预算983万元、最高限价600万元，公开转引采购需求出现免疫流水线、全自动酶免仪。
  https://www.lfzct.com/info/Rmzxcgr8AAAALw1HvFxvaFeAAAAQ%3D%3D?city=%E5%A4%A9%E6%B4%A5%E5%B8%82
- 第四批 XCSD-2026-A-944，预算490.1万元、最高限价482.1万元，公开转引第1包有生物显微镜、医学显微镜、生物安全柜；第2包有医用冷藏/冷冻冰箱与负80度冰箱。
  https://www.lfzct.com/info/KL43PqviwfHGMk1wciNodw%3D%3D?city=%E5%A4%A9%E6%B4%A5%E5%B8%82
- **证据分级**：以上第一、第二、第四批原始中国政府采购网 URL 此轮重新打开受到访问限制，因此这些具体产品和最高限价只能记为 SECONDARY_REPRINT，**不得称已独立重开官方正文**；进入生产 verified canonical 之前必须由正式官方原文或官方附件重新确认。
- 第五批 XCSD-2026-A-939 的四包八个明示产品及各包预算/限价则已通过政府采购网直接复核。其公告使用“等”且另附需求书，因此八个名称不是完整采购清单。
- 以上带证据级别的回归数据保存为同目录 C01_same_hospital_package_fixture.json，可用于工程师的包级解析验收，但所有 SECONDARY_REPRINT 条目必须先复核才能升级为 VERIFIED。

还发现同案国际聚合商的实际错误：
- GlobalTenders 在第一批/第四批页面将医疗设备标成 X-ray inspection equipment / Fire Safety and Security，并显示截止 2026-11-11，与国内官方开标信息（第一批11/18、第四批11/17）不一致。
- https://www.globaltenders.com/tender-detail/public-tender-for-the-first-project-for-the-AuQJRdem0V09WOWT
- https://www.globaltenders.com/tender-detail/public-call-for-tenders-for-the-fourth-batch-X9AXEHNwyAKxuLDk
- 它展示的 secondary deadline 不可当正式投标截止；**信息源冲突发现+官方纠错**可能是面向跨境用户的价值之一，但仅两例不能推定这类平台整体错误率。

以上发现使下轮 C02 增加两项验收：
1. 每个采购包事实必须有 source confidence，允许“官方原文待核”，不把第三方复制内容提升为权威；
2. 若第三方与官方时间/类别冲突，不能选一个看似合理的数值，应高亮冲突并以可验证的官方事实为准。
