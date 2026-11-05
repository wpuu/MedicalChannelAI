# MedicalChannelAI｜行动雷达离线 Gold Set v0

- 日期：2026-10-07
- 修订：2026-11-05（Asia/Shanghai）
- 状态：RULE_SMOKE_DRAFT / NOT_EXECUTABLE_BENCHMARK
- 目的：不用真实客户资料，先验证“事件生命周期 + 客户产品画像 + 行动建议”能否稳定降噪。
- 说明：本文件记录的是人工期望标签（gold labels），不是 Agnes 已跑出的结果。
- 权威规则：[行动雷达验收合同](../project/action-radar-acceptance-contract.md)。本文件的 15 例仅是规则冒烟集；不代表真实覆盖、统计精确率、召回率或付费价值已验证。

## 固定回放与资格约定

- 下列 `as_of` 是各案例独立的历史判断时钟，不是当前日期，也不是将全部案例塞入同一“最近30天”数据集。只允许使用该时点已公开的事实。
- 正式自动回放前，必须封存官方详情及附件的当时版本、哈希、画像版本和跟进状态。本文原始链接/事实摘要不能替代这些 fixtures；未封存的案例不计自动验收 PASS。
- 默认三个 Persona 都是首次发现项目、无既有跟进；未主动确认的入围、授权、注册/经营资格均为 `UNKNOWN`，不得当作已满足。
- `WATCH` 可包含“确认具体产品/核实资格”问题；`PREPARE` 不表示正式报名已开放。`ACTION_NOW` 必须同时写明具体动作及所需已确认条件，不能仅凭产品语义相近推出可投。
- `BLOCKED_EVIDENCE` 表示缺少可冻结的官方详情，不能产生已确认机会，也不进入模型准确率分母。

## 测试画像

### Persona A｜病理设备渠道
- 包埋盒打号机
- 载玻片打号机
- 免疫组化设备
- 病理设备/病理信息化

### Persona B｜手术/消毒设备渠道
- 脉动真空灭菌器
- 手术动力系统
- 消融设备
- 手术器械

### Persona C｜检验/试剂/常用耗材渠道
- 检验设备
- 检验试剂
- 培养基
- 负压引流/吸痰等常用耗材

## Gold cases

### G01｜天津中医药大学第二附属医院：可控负压吸痰管院内调研
- as_of: 2026-06-26T10:00:00+08:00
- Source: https://www.tjzyefy.com/system/2026/06/25/030193092.shtml
- Lifecycle: MARKET_RESEARCH
- 官方事实：院内调研；报名 2026-06-25 至 2026-07-01 16:00；要求天津市医药采购中心入围厂家或供应商。
- Persona A: PASS
- Persona B: PASS
- Persona C: WATCH（核实天津市医药采购中心入围资格）
- 关键理由：产品直接匹配且历史报名窗口开放，但测试画像没有提供入围资格。
- 条件变体：仅当画像明确确认所需入围及其他硬资格、官方版本已封存时，才允许 ACTION_NOW（按官方要求准备/提交调研材料）；明确未入围则不能推荐报名。
- 时间变体：as_of=2026-07-02T10:00:00+08:00 时，新发现不得推荐报名，不使用后来的延期或结果反推当时事实。
- 禁止误判：不能说“已正式招标”。

### G02｜天津中医药大学第二附属医院：刺探针/包皮切割吻合器/活检针调研
- as_of: 2026-06-24T10:00:00+08:00
- Source: https://www.tjzyefy.com/system/2026/06/23/030192895.shtml
- Lifecycle: MARKET_RESEARCH
- Persona A: PASS
- Persona B: WATCH
- Persona C: PASS
- 关键理由：Persona B 的“手术器械”过宽，不能因为大类相近就直接 ACTION_NOW；只有其真实产品目录包含相关针/吻合器时才能升级。
- 这是一个防止 Agnes 过度泛化的重要 hard negative。

### G03｜天津中医药大学第二附属医院：脉动真空灭菌器采购意向
- as_of: 2026-10-07T15:19:00+08:00
- Fixture status: BLOCKED_EVIDENCE（原稿仅保留索引，未封存该意向详情及官方发布日期）
- Source index: https://www.tjzyefy.com/xwgg/ggtz/
- Lifecycle: PROCUREMENT_INTENT
- Persona A: PASS
- Persona B: PREPARE（规则期望；仅在该 as_of 前官方详情验证成功后评估）
- Persona C: PASS
- 关键理由：明确产品匹配，但采购意向不是报名窗口。
- 推荐动作：准备厂家授权、注册/备案资料、历史案例，继续跟踪正式采购公告。
- 禁止关联：本例医院是第二附属医院，不能与 G09 第一附属医院的同类设备自动合并。

### G04｜天津中医药大学第二附属医院：流式细胞仪等医疗设备采购意向
- as_of: 2026-10-07T15:19:00+08:00
- Fixture status: BLOCKED_EVIDENCE（原稿仅保留索引，未封存该意向详情及官方发布日期）
- Source index: https://www.tjzyefy.com/xwgg/ggtz/
- Lifecycle: PROCUREMENT_INTENT
- Persona A: PASS
- Persona B: PASS
- Persona C: WATCH（规则期望：确认是否具体经营流式细胞仪；官方详情未验证前不交付）
- 关键理由：只有“检验设备”父类别，不能自动认定具备流式细胞仪产品能力。
- 条件变体：画像增加明确的流式细胞仪产品项且详情有对应采购子项后，可为 PREPARE；仍不产生正式报名截止。

### G05｜天津市中心妇产科医院：细菌室培养基询价
- as_of: 2026-06-23T10:00:00+08:00
- Source: https://www.tjzxfc.cn/system/2026/06/22/030306473.shtml
- Lifecycle: QUALIFICATION_WINDOW
- Persona A: PASS
- Persona B: PASS
- Persona C: WATCH（核实具体培养基子项及注册/经营/授权材料）
- 官方事实：细菌/真菌等培养基；要求医疗器械经营/生产、注册证、检测报告、授权等材料；有明确递交期。
- 价值：不仅告诉“有项目”，还应自动形成材料 checklist。
- 条件变体：先从已封存详情确认该 as_of 处于递交期，再确认具体产品子项和硬资格，才允许 ACTION_NOW（对应材料准备/提交）。不能用“检验试剂”类别替代所有具体产品资质。

### G06｜天津市中心妇产科医院：人工智能法律数据库
- as_of: 2026-07-09T10:00:00+08:00
- Source: https://www.tjzxfc.cn/system/2026/07/08/030313812.shtml
- Lifecycle: QUALIFICATION_WINDOW
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 原因：采购单位是医院不等于医疗渠道机会。
- 这是最重要的 hospital-identity hard negative 之一。

### G07｜天津市中心妇产科医院：门禁项目
- as_of: 2026-10-01T10:00:00+08:00
- Source: https://www.tjzxfc.cn/system/2026/09/30/030351603.shtml
- Lifecycle: QUALIFICATION_WINDOW
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 原因：非医疗设备/耗材，与三个画像均无关。

### G08｜天津市肿瘤医院：手术器械公开招标
- as_of: 2026-09-09T10:00:00+08:00
- Source: https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260907_27282318.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: WATCH（具体器械/包件和硬资格待确认）
- Persona C: PASS
- 官方事实：预算 356.052 万元；招标文件获取 2026-09-08 至 2026-09-14；开标 2026-09-29。
- 条件变体：封存需求附件，明确命中 B 的具体产品子项、满足所需条件后，在该历史文件获取期可 ACTION_NOW；“手术器械”大类本身不充分。
- 时间变体：as_of=2026-10-07T15:19:00+08:00 的首次发现应 PASS（新进入动作）；没有后续官方证据时不能编造中标结果或竞品动态。

### G09｜天津中医药大学第一附属医院：脉动真空灭菌器公开招标
- as_of: 2026-09-21T10:00:00+08:00
- Source: https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260918_27358280.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: WATCH（产品直接匹配，核实硬资格及具体包件要求）
- Persona C: PASS
- 条件变体：封存附件并明确满足硬资格、具体包件要求后，在文件获取期 2026-09-18 至 2026-09-24 内可 ACTION_NOW；期后首次发现不能建议正常新报名。
- 关键测试：与 G03 为不同医院，即使产品相同也必须保留独立项目身份。真正“意向→招标”的正例须另补同一采购主体、项目/包号或官方交叉引用证据；本文尚无该正例。

### G10｜中国医学科学院血液病医院：试剂耗材采购
- as_of: 2026-09-11T10:00:00+08:00
- Source: https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260910_27302788.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: PASS
- Persona C: WATCH（待附件拆分具体产品与包件、确认画像和资格）
- 官方事实：预算 262 万元；试剂耗材第三批。
- 注意：需要附件进一步拆产品明细，标题级不能假设所有 Persona C 产品都能投。
- 条件变体：官方附件给出明确子项，画像对应产品、硬资格以及文件获取窗口均满足后，才评估具体 ACTION_NOW；本稿未提供完整窗口及需求附件，不能直接升级。

### G11｜天津国际旅行卫生保健中心：临检实验室设备
- as_of: 2026-09-15T10:00:00+08:00
- Source: https://www.ccgp.gov.cn/cggg/zygg/jzxcs/202609/t20260911_27310145.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: PASS
- Persona C: WATCH（需求书中的具体设备待核实）
- 官方事实：预算 26 万元；采购文件获取 2026-09-14 至 2026-09-18。
- 注意：具体设备需以需求书为准。
- 禁止误判：泛“检验设备”不能自动成为具体产品命中；采购期开放也不能补足未知产品和资格。

### G12｜天津市第五中心医院：数字减影血管造影机中标
- as_of: 2026-09-29T10:00:00+08:00
- Source: https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412423.htm
- Lifecycle: AWARD_RESULT
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 扩展变体：仅对明确经营 DSA 或关注已证实竞品的画像，才另评估竞争情报；本轮三个画像均不包含该条件，不能因此扩展已交付模块。
- Gold 目的：结果公告不能因为金额大就对所有医疗渠道客户推送。

### G13｜天津中医药大学第一附属医院：医用内窥镜中标
- as_of: 2026-09-11T10:00:00+08:00
- Source: https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260910_27308714.htm
- Lifecycle: AWARD_RESULT
- Persona A: PASS
- Persona B: WATCH（仅核实产品范围，不作为新报名机会）
- Persona C: PASS
- 测试：大类“手术设备”不能无限扩张。

### G14｜天津市人民医院：家具采购
- as_of: 2026-09-12T10:00:00+08:00
- Source: https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260911_27315713.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 原因：医院采购不等于医疗渠道机会。

### G15｜天津市医药采购中心：口腔牙冠类耗材限价挂网价格
- as_of: 2026-10-07T15:19:00+08:00
- Fixture status: BLOCKED_EVIDENCE（原稿仅有网站首页，缺少政策详情、版本、生效时间和适用范围）
- Source: https://www.tjmpc.cn/
- Lifecycle: POLICY_OR_PRICING
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 扩展变体：对口腔耗材画像，也必须先补齐官方通知与适用产品/期限，再判断核实或执行动作；不得从首页推导需要立即调整价格。
- Gold 目的：政策通知必须基于客户产品线定向，不应全行业广播。

## 必须通过的模型行为

### 1. 医院身份不等于相关
G06/G07/G14 必须全部 PASS。

### 2. 大类不能无限泛化
G02/G13 不允许因为“手术相关”就自动强匹配 Persona B。

### 3. 时间状态必须覆盖语义相关
G08/G09/G10/G11 在获取文件期结束后，不能继续 ACTION_NOW。

### 4. 生命周期必须区分
PROCUREMENT_INTENT ≠ MARKET_RESEARCH ≠ FORMAL_TENDER ≠ AWARD_RESULT。

### 5. 关键事实不由 Agnes 创造
预算、日期、联系人、产品型号、资格要求只能来自 source evidence。

### 6. 无匹配时允许 0 条
不能为了填满“今日推荐”而输出低相关项目。

## 冒烟验收与后续盲测

15 公告 × 3 画像是重复使用同一公告的规则检查，不是 45 个独立公告样本；增加时间/资格变体后须按各自固定输入单独编号。缺 fixture、资格或唯一预期的案例报告 BLOCKED，不算 PASS，也不把缺失当模型错误。

冒烟要求：明确非医疗或不相关项不误推；生命周期不冒充；资格 UNKNOWN 不冒充满足；窗口关闭后不建议正常新报名；跨医院同产品不合并；unsupported critical fact 为零。不确定则 WATCH/PASS 或明确提问，不补全。

本文件不再以原稿的“误推率≤5% / 早期召回率≥90%”放行产品：少量、手选且有缺失证据的样本不能证明这些总体指标。另建连续时间段的官方公告盲测集和明确正反例，按项目分组隔离调试/评估；分别统计每客户去重 precision、已知相关公告 recall、采集遗漏、延迟、样本数及阻塞项。零推送的 precision 为不适用。

冒烟通过只是后续盲测的前提；不代表相关性/资格门禁已实现，不代表四个栏目已交付，也不代表 7 天付费探索或续费价值已经成立。
