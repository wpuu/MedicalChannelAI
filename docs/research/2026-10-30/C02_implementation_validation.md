# MED-ACTION-20261030/C02｜隔离修复、回归验证与生产只读审计

日期：2026-10-30
状态：ISOLATED_FIX_TESTED / OFFICIAL_RAW_HTML_BLOCKED / FULL_BUILD_BASELINE_FAILED / PRODUCTION_HOLD
起点：PR #78 SHA d158f8648db17b904300671b0f1ccbae795c324c（该 PR 基于 PR #75，均未合并 main）
隔离分支：fix/c02-ccgp-package-products-20261030
上轮证据：https://github.com/wpuu/MedicalChannelAI/tree/research/medical-action-c01-20261030/docs/research/2026-10-30

## 一、本轮完成的代码

仅在隔离分支开发，不更改PR75、PR78、main或Production。

- 新增 web/pipeline/medical_channel_pipeline/ccgp_tianjin_package_table.py：严格六列的包级采购需求适配器，要求包号、是否限价、预算（万元）、最高限价（万元）、采购目录、采购需求的表头完全一致；当前仅接受临床检验设备；支持普通表和 CMS 外层嵌套表。
- 完整性保护：每包编号连续，金额用Decimal准确换算，包预算、总预算与官方主公告一致，包限价合计与主公告一致；任何一行、任何一包不匹配即返回空，不部分发布。
- 明示产品拆分：只根据“采购[设备A、设备B]等，具体内容详见项目需求书”原文抓名称；未公开具体数量则quantity=None，绝不推测；包级金额不能当单个产品报价。每包non_exhaustive=true，主公告名单不等于完整附件清单。
- 修改 ccgp_detail.py：旧有标准采购表和明确名称数量提取器完全保留，只在旧product_items为空时补用新适配器；新事实带官方URL、locator及package_id。
- 修改 public_snapshot.py：仅在CCGP来源存在匹配官方 evidence 时暴露采购包明细，保持 coverage_status=PARTIAL；旧项目若无包事实，公共JSON结构不变。
- 新增 test_ccgp_tianjin_package_table_c02.py：使用“由官方可读正文人工转录的合成HTML”验证四包八设备、金额、嵌套表、未知数量、公共快照以及非医疗、错表头、缺包、预算错误、附件缺内容、第三方误导日期和非官方Host等负例。
- 新增独立GitHub Actions离线验证workflow、单次官方原始HTML只读验证workflow；C02分支vercel.json明确关闭Preview，日志显示该分支Preview为零。

## 二、已运行的测试与严格边界

### 修复前真实RED

GitHub Actions：https://github.com/wpuu/MedicalChannelAI/actions/runs/41067224428

9项隔离测试中2项按预期失败：普通与CMS嵌套表结构均只能抽出0个产品；官方公告可读正文有4个包8个明示设备。其余7项安全测试通过。

### 修复后通过的部分

GitHub Actions：https://github.com/wpuu/MedicalChannelAI/actions/runs/41068437787

- C02 定向解析测试 PASS（新增公开快照验证）；
- 原有CCGP解析测试 PASS；
- 完整Python pipeline单测 PASS；
- 独立TypeScript类型检查 PASS；
- 独立Vite build PASS；
- C02合成表的预算为5091900元，包预算分别2480000/1049900/950000/612000；总最高限价4281900元，包最高限价分别2270000/599900/800000/612000；八个明示产品都带包号、数量null，不把清单认作完整BOM。
- 项目公开快照可以读到四包和八个产品，coverage_status仍PARTIAL。

### 完整组合npm run build尚未通过

- 新C02分支 npm run build 报：AI_BOUNDARY_UNCONFIGURED: expected 503, got 409。
- 该次 workflow 的第二个job使用完全未修改的 PR #78 起点SHA在相同GitHub Runner、相同依赖环境中重新执行 npm run build，也报完全一致的 AI_BOUNDARY_UNCONFIGURED: expected 503, got 409。
- 因此这是原PR78基线已有的组合构建阻塞，不是本轮采购包parser带来的新增回归。可能与历史测试机会窗口已过有关，但具体根因未重新证明。
- 严格状态：Python/TS/Vite分别成功；完整npm run build BLOCKED。不得宣传整体绿色，更不能为求通过而削弱线上409过期窗口保护。

### 官方原始HTML没有通过活体验收

单次限时、限大小、无代理、无重试的官方GET Action：
https://github.com/wpuu/MedicalChannelAI/actions/runs/41068131756

- 结果 HTTP 403 Forbidden；未绕过、未追加请求。
- 无法获取可复核原始HTML字节及SHA256，也不能声称已在真实原始HTML DOM上验证该适配器。
- 本轮只证明按真实官方文字合成、注明OFFLINE_SYNTHETIC_HTML的严格两种表格形态可正确解析。
- 原始真实DOM受访问限制必须保持 NOT_VERIFIED。

官方公告：https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm

## 三、Production新鲜度只读检查

- Production SHA依然3216fd940dabfa7714383b6436908f9b72ff8a9c；部署 dpl_4LPKoTdusrvbExXuzbMKtnyiT86C仍READY；
- 最新DATABASE公开快照时间 2026-10-28T08:27:29.111217+08:00；
- API status：degraded=true、freshness=STALE、机会池65；
- collector-status：v2本期cycle无记录、0/22 stage完成、chain=null、既有五源last_completed_scan=null；
- pipeline-health：HTTP 503；
- 没有证据证明当前自然Cron正常推动。不能从数据库快照倒推是哪种程序写入的。
- 本轮无Production部署、无Preview、无main合并、无cron/queue/cache/db/密钥修改。

入口：
https://medicalchannelai.vercel.app/api/status
https://medicalchannelai.vercel.app/api/collector-status
https://medicalchannelai.vercel.app/api/pipeline-health

## 四、C02放行裁决

C02代码级离线修复完成，真实HTML与整体构建及自然自动采集均未全部验收。项目发布状态：HOLD。

进入C03：
1. 采用合规、明确授权的原始政府采购网页/官方附件读取路径，核对真实DOM、SHA256、逐包金额和不完整产品范围；网页403时不得绕过。
2. 独立定位旧PR78的AI边界测试503/409差异并修复测试时间基准，禁止改变产品真实过期保护。
3. 继续只读排查Cron→Queue→source→canonical→durable snapshot实际运行证据；沿用PR75/PR78最新安全门禁，不拿旧P0覆盖。
4. 完整构建与真实源验收、连续7天自动采集可靠性通过之前，不申请Production，也不启动对外付费Pilot。

最终原则：无论何时，都不允许AI补出不存在的采购数量、注册证、联系人或中标概率。
