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
5. `tools/medical_pilot/coverage_manifest.tianjin.v0.1.json`
6. `tools/medical_pilot/identity_policy.tianjin.v0.1.json`
7. `tools/medical_pilot/product_taxonomy.v0.1.json`
8. `tools/medical_pilot/product_classifier_registry.v0.1.json`

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
12. 普通匹配进入 daily digest；只有 fully-confirmed profile + 高优先级才允许即时提醒。
13. `WON / LOST / NOT_FIT / ARCHIVED` 默认抑制同一 opportunity 的重复通知；活跃项目有 owner 时优先路由 owner。
14. 模型上下文按单商机限制，不把整个候选池放入一次 prompt，也不截断官方 Fact 冒充完整事实。
15. Coverage 当前仍为 `PARTIAL / NOT_EXHAUSTIVE`，不得宣称天津全覆盖。
16. Agnes 2.5 Flash 仍为 `GO_FOR_BENCHMARK`；taxonomy classifier 为 `BENCHMARK_PENDING`，不能驱动正式 Match。
17. 真实官方附件 bytes 捕获仍为0，不能宣称真实 DOCX/XLSX/PDF parser 已验证。
18. GitHub Actions Runner 问题仍存在；没有 Python step 执行证据就不能说 tests PASS。
19. 不自行 merge PR #1。

## 当前主要链路

`Source Registry → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → Institution Evidence → Product Taxonomy → Profile Gate → Match → Query Budget → Priority → Daily Recommendation → Subscription Prefilter → Subscription Evaluation → Notification Route → Latency Ledger → Follow-up → Grounded Model Decision`

## 当前主要能力

- 50条 VERIFIED 天津商机回归 corpus
- 15条官方 Institution Evidence
- Source Registry / Coverage / lifecycle / canonical identity
- Product taxonomy / classifier admission
- Customer + Matching Profile Gate
- Query Budget / model context budget
- Priority Score（经营优先级，不是中标概率）
- Daily Recommendation Top 5
- Continuous Subscription：反向预筛、Match、通知分级、稳定 dedupe key
- Follow-up owner routing / terminal suppression
- Latency Ledger：published/discovered/fetched/verified/matched/queued/delivered
- Follow-up feedback → profile change proposal，默认不得自动修改画像
- DOCX/XLSX parser；PDF Docling backend 尚未真实字节验证
- Agnes 两套 benchmark harness，仍未执行

## 验证

运行：

```bash
python -m compileall -q tools/medical_pilot
python -m unittest discover -s tools/medical_pilot -p "test_*.py" -v
```

GitHub Actions workflow: `.github/workflows/medical-pilot-ci.yml`

当前最新证据仍是 `runner_id=0 / steps=[]`；不得写 `PASS`。

## 下一步顺序

1. 把 Daily/Subscription/Latency 合同接入未来 Fact API 与后台事件调度层。
2. 优先攻克天津政府采购 PRIMARY 原生列表/搜索/分页/生命周期与附件 href。
3. 获取第一份真实官方 DOCX/PDF bytes，跑 Snapshot/SHA/parser locator 全链。
4. Runner恢复后执行全部 deterministic tests 与 taxonomy corpus audit，优先修真实失败。
5. 根据 audit unresolved 扩 deterministic taxonomy，再决定 Agnes 实际承担比例。
6. deterministic execution 有证据后运行 Agnes 两套 benchmark。
7. 后端 API 稳定后再进入 H5/微信小程序端；未来通过 Skill / Fact API / MCP 接入 Hermes。
