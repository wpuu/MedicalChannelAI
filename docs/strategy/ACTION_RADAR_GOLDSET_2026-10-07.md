# MedicalChannelAI｜行动雷达离线 Gold Set v0

- 日期：2026-10-07
- 状态：OFFLINE_VALIDATION_DATASET
- 目的：不用真实客户资料，先验证“事件生命周期 + 客户产品画像 + 行动建议”能否稳定降噪。
- 说明：本文件记录的是人工期望标签（gold labels），不是 Agnes 已跑出的结果。

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
- Source: https://www.tjzyefy.com/system/2026/06/25/030193092.shtml
- Lifecycle: MARKET_RESEARCH
- 官方事实：院内调研；报名 2026-06-25 至 2026-07-01 16:00；要求天津市医药采购中心入围厂家或供应商。
- Persona A: PASS
- Persona B: PASS
- Persona C: ACTION_NOW
- 关键理由：产品直接匹配；属于正式采购前调研窗口；有明确报名截止和材料要求。
- 禁止误判：不能说“已正式招标”。

### G02｜天津中医药大学第二附属医院：刺探针/包皮切割吻合器/活检针调研
- Source: https://www.tjzyefy.com/system/2026/06/23/030192895.shtml
- Lifecycle: MARKET_RESEARCH
- Persona A: PASS
- Persona B: WATCH
- Persona C: PASS
- 关键理由：Persona B 的“手术器械”过宽，不能因为大类相近就直接 ACTION_NOW；只有其真实产品目录包含相关针/吻合器时才能升级。
- 这是一个防止 Agnes 过度泛化的重要 hard negative。

### G03｜天津中医药大学第二附属医院：脉动真空灭菌器采购意向
- Source index: https://www.tjzyefy.com/xwgg/ggtz/
- Lifecycle: PROCUREMENT_INTENT
- Persona A: PASS
- Persona B: PREPARE
- Persona C: PASS
- 关键理由：明确产品匹配，但采购意向不是报名窗口。
- 推荐动作：准备厂家授权、注册/备案资料、历史案例，继续跟踪正式采购公告。

### G04｜天津中医药大学第二附属医院：流式细胞仪等医疗设备采购意向
- Source index: https://www.tjzyefy.com/xwgg/ggtz/
- Lifecycle: PROCUREMENT_INTENT
- Persona A: PASS
- Persona B: PASS
- Persona C: PREPARE
- 关键理由：检验/实验室设备方向匹配；仍处提前布局阶段。

### G05｜天津市中心妇产科医院：细菌室培养基询价
- Source: https://www.tjzxfc.cn/system/2026/06/22/030306473.shtml
- Lifecycle: QUALIFICATION_WINDOW
- Persona A: PASS
- Persona B: PASS
- Persona C: ACTION_NOW
- 官方事实：细菌/真菌等培养基；要求医疗器械经营/生产、注册证、检测报告、授权等材料；有明确递交期。
- 价值：不仅告诉“有项目”，还应自动形成材料 checklist。

### G06｜天津市中心妇产科医院：人工智能法律数据库
- Source: https://www.tjzxfc.cn/system/2026/07/08/030313812.shtml
- Lifecycle: QUALIFICATION_WINDOW
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 原因：采购单位是医院不等于医疗渠道机会。
- 这是最重要的 hospital-identity hard negative 之一。

### G07｜天津市中心妇产科医院：门禁项目
- Source: https://www.tjzxfc.cn/system/2026/09/30/030351603.shtml
- Lifecycle: QUALIFICATION_WINDOW
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 原因：非医疗设备/耗材，与三个画像均无关。

### G08｜天津市肿瘤医院：手术器械公开招标
- Source: https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260907_27282318.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: ACTION_NOW（仅在招标文件获取窗口仍开放时）
- Persona C: PASS
- 官方事实：预算 356.052 万元；招标文件获取 2026-09-08 至 2026-09-14；开标 2026-09-29。
- 时间规则：如果雷达在 2026-10-07 回放，不得仍给 ACTION_NOW，应为 PASS/LATE + COMPETITOR_WATCH。

### G09｜天津中医药大学第一附属医院：脉动真空灭菌器公开招标
- Source: https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260918_27358280.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: ACTION_NOW（仅文件获取期 2026-09-18 至 2026-09-24 内）
- Persona C: PASS
- 关键测试：同一产品从 PROCUREMENT_INTENT → FORMAL_TENDER 时应串成生命周期，不得当成两个独立陌生项目。

### G10｜中国医学科学院血液病医院：试剂耗材采购
- Source: https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260910_27302788.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: PASS
- Persona C: ACTION_NOW（在文件获取期内）
- 官方事实：预算 262 万元；试剂耗材第三批。
- 注意：需要附件进一步拆产品明细，标题级不能假设所有 Persona C 产品都能投。

### G11｜天津国际旅行卫生保健中心：临检实验室设备
- Source: https://www.ccgp.gov.cn/cggg/zygg/jzxcs/202609/t20260911_27310145.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: PASS
- Persona C: ACTION_NOW（在采购文件获取期内）
- 官方事实：预算 26 万元；采购文件获取 2026-09-14 至 2026-09-18。
- 注意：具体设备需以需求书为准。

### G12｜天津市第五中心医院：数字减影血管造影机中标
- Source: https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412423.htm
- Lifecycle: AWARD_RESULT
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 但对于“影像设备渠道”画像应为 COMPETITOR_INTELLIGENCE。
- Gold 目的：结果公告不能因为金额大就对所有医疗渠道客户推送。

### G13｜天津中医药大学第一附属医院：医用内窥镜中标
- Source: https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260910_27308714.htm
- Lifecycle: AWARD_RESULT
- Persona A: PASS
- Persona B: WATCH（仅当客户真实经营内窥镜/手术镜产品时升级）
- Persona C: PASS
- 测试：大类“手术设备”不能无限扩张。

### G14｜天津市人民医院：家具采购
- Source: https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260911_27315713.htm
- Lifecycle: FORMAL_TENDER
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 原因：医院采购不等于医疗渠道机会。

### G15｜天津市医药采购中心：口腔牙冠类耗材限价挂网价格
- Source: https://www.tjmpc.cn/
- Lifecycle: POLICY_OR_PRICING
- Persona A: PASS
- Persona B: PASS
- Persona C: PASS
- 但“口腔耗材渠道”画像应为 ACTION_NOW/WATCH，取决于是否存在需要确认价格/执行的具体动作。
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

## 最低验收线

在 15 个 gold cases × 3 personas = 45 个判断上：

- hard negative（明确 PASS）误推率 ≤ 5%；
- 生命周期分类 100% 正确；
- 已过报名/文件获取期的项目，不得输出 ACTION_NOW；
- 直接产品匹配的早期调研/意向召回率 ≥ 90%；
- 任何 unsupported critical fact = 0；
- 模型不确定时必须降级 WATCH/PASS 或提出确认问题，不得补全。

只有 gold set 通过后，才值得把 3 个真实客户画像接入 7 天付费验证。
