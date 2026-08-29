# MedicalChannelAI — READ FIRST

## 仓库身份

- Repository: `wpuu/MedicalChannelAI`
- 主分支: `main`
- 当前开发分支: `dev/tianjin-pilot-v0.1`
- 当前阶段: `M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`
- Draft PR: `#1`
- `production_ready=false`
- `merge_approved=false`

本仓库独立开发医疗渠道经营 AI / 医疗商业情报 Agent。天津是首个 Pilot，后续可扩展到全国医疗器械、IVD、耗材渠道商及厂家销售。

## 开始工作前必须读取

1. `docs/project/current-state.md`
2. `docs/project/checkpoint.json`
3. `docs/research/schemas/`
4. `tools/medical_pilot/source_registry.tianjin.v0.1.json`
5. `tools/medical_pilot/source_topology.tianjin.v0.1.json`
6. `tools/medical_pilot/coverage_manifest.tianjin.v0.1.json`
7. `tools/medical_pilot/identity_policy.tianjin.v0.1.json`
8. `tools/medical_pilot/product_taxonomy.v0.1.json`
9. `tools/medical_pilot/product_classifier_registry.v0.1.json`

不要依赖聊天记录判断当前完成状态；以 GitHub 实际分支和 checkpoint 为准。

## 不可违反的最高规则

1. **模型不得创造采购事实。** 医院/采购人、项目名、预算、日期、截止时间、生命周期、中标供应商/金额、官方品牌/型号/数量/价格、来源 URL 必须来自 Evidence。
2. 官方事实必须可以回到原始公开来源，保留 Snapshot SHA-256 与 Evidence locator/hash。
3. 抓取失败、来源不可用、字段缺失、官方信息冲突时必须显式降级；不得用模型补全。
4. 项目按 lifecycle 聚合，不把单篇旧公告长期当作当前状态。
5. `VERIFIED` 新终止可覆盖旧 `VERIFIED` 招标；`UNVERIFIED` 新事件不得覆盖已验证状态。
6. 采购意向只公开月份时不得伪造具体日；官方发布时间只有 `DAY` 精度时不得计算分钟级 source latency。
7. 客户经营画像条件不足必须继续追问；不得生成高可信个性化推荐。
8. 客户画像可以很宽，限制的是单次执行预算，不得要求客户为了性能填写虚假的小范围。
9. 交互查询使用共享 VERIFIED Fact Index，不做 `区域 × 产品 × 数据源` 的实时笛卡尔爬取。
10. 正式产品匹配使用受控 `taxonomy_ids`；机构等级/类型必须有官方或人工确认 provenance。
11. Subscription Prefilter 只做性能预筛，最终通知必须通过完整 Match Gate。
12. 公共订阅事件边界必须使用 VERIFIED Material Event Envelope；change_fields 必须逐项 Evidence-grounded，持久化 event 进入订阅前必须重算 hash/idempotency。
13. 普通匹配进入 daily digest；只有 fully-confirmed profile + 高优先级才允许即时提醒。
14. `WON / LOST / NOT_FIT / ARCHIVED` 默认抑制同一 opportunity 的重复通知；活跃项目有 owner 时优先路由 owner。
15. Notification Delivery 必须复用稳定 identity；SUPPRESSED 使用 `audience=NONE`，重试不得创建新通知。
16. 模型上下文按单商机限制，不把整个候选池放入一次 prompt，也不截断官方 Fact 冒充完整事实。
17. 天津财政政府采购 `tjgp.cz.tj.gov.cn` 与 `ccgp-tianjin.gov.cn`（含 www）是同一 PRIMARY Source 官方 host/alias，不得重复计商机。
18. `tj_government_procurement_center` / `tjgpc.zwfwb.tj.gov.cn` 是集采项目 PRIMARY 补充源，不是全市财政采购源替代品；同项目仍按 project_number 聚合。
19. **附件发现不等于下载授权。** `AttachmentCandidate.download_authorized=false` 时 Fetcher 必须在网络前拒绝。
20. `tjgpc downloadFile.do` 的 nested `fileUrl` 永远不得直接请求；只允许已观察 origin/path 结构用于安全校验，未知 host/端口/路径拒绝。
21. 附件下载同时校验扩展名/MIME/magic：PDF `%PDF-`，DOCX/XLSX ZIP，DOC/XLS OLE。
22. 搜索索引能读取官方附件正文不等于 MedicalChannelAI 已捕获 bytes；当前真实官方附件 bytes=0，医疗附件 bytes=0。
23. Coverage 当前仍为 `PARTIAL / NOT_EXHAUSTIVE`，不得宣称天津全覆盖。
24. Agnes 2.5 Flash 仍为 `GO_FOR_BENCHMARK`；taxonomy classifier 为 `BENCHMARK_PENDING`，不能驱动正式 Match。
25. GitHub Actions Runner 问题仍存在；没有 Python step 执行证据就不能说 tests PASS。
26. 不自行 merge PR #1。

## 当前真实规模

- **7个运行时 P0 Source：4 IMPLEMENTED + 3 PARTIAL**
- 50条 VERIFIED 天津商机 regression corpus
- 15条官方 Institution Evidence
- 23份正式 Schema/合同
- **40组 deterministic unittest 模块（尚无执行证据）**
- Agnes 两套 benchmark 共28 case，仍未执行

## 当前 P0 Source

IMPLEMENTED：`ccgp_local_notices`、`ccgp_procurement_intent`、`tjmugh_procurement`、`tj_first_central_hospital_procurement`。

PARTIAL：

- `tj_government_procurement` — 天津财政政府采购官方 host/alias 详情
- `tj_government_procurement_center` — `tjgpc.zwfwb.tj.gov.cn` 集采项目详情 + attachment wrapper discovery-only
- `tj_public_resource_exchange` — 当前仅政府采购结果页

## tjgpc 特别边界

已确认：详情 `/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=<UUID>`；医疗样本 `TGPC-2025-A-0164` 正文公开多功能吊塔、呼吸机、中央监护、支气管镜、除颤仪等并显示 DOCX 招标文件名；官方附件机制 `/webInfo/downloadFile.do?fileName=...&fileUrl=...` 被搜索索引解析为真实文档内容。

未确认：医疗项目精确 wrapper URL、crawler runtime bytes/MIME/magic/SHA、原生列表 class id/pagination、全部采购方式。因此 attachment 仍 discovery-only、download_authorized=false。

## 验证

```bash
python -m compileall -q tools/medical_pilot
python -m unittest discover -s tools/medical_pilot -p "test_*.py" -v
```

最新 CI 证据：Run `33230101416` / Job `99041292283`，`runner_id=0 / runner_name="" / steps=[]`。不得写 `PASS`。

## 下一步顺序

1. 反查 `TGPC-2025-A-0164` 等医疗项目的精确 `downloadFile.do` wrapper URL；不得猜 fileUrl。
2. 捕获第一份真实官方附件 bytes，并把任意官方采购附件与医疗附件分开计数。
3. 验证 `tjgpc` 原生列表 class id / pagination，同时继续天津财政 PRIMARY 原生列表/搜索/分页研究。
4. Runner恢复后执行40组 deterministic tests 与 taxonomy corpus audit。
5. deterministic execution 有证据后运行 Agnes 两套 benchmark。
6. 后端 API 稳定后再进入 H5/微信小程序端；未来通过 Skill / Fact API / MCP 接入 Hermes。
