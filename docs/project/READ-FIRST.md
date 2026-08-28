# MedicalChannelAI — READ FIRST

## 仓库身份

- Repository: `wpuu/MedicalChannelAI`
- 主分支: `main`
- 当前开发分支: `dev/tianjin-pilot-v0.1`
- 当前阶段: `M1_FACT_PIPELINE`
- `production_ready=false`

本仓库独立开发医疗渠道经营 AI / 医疗商业情报 Agent。天津是首个 Pilot，后续目标可扩展到全国医疗器械、IVD、耗材渠道商及厂家一线销售。

## 不可违反的最高规则

1. **模型不得创造采购事实。** 医院/采购人、项目名、预算、日期、截止时间、生命周期、中标供应商/金额、官方品牌/型号/数量/价格、来源 URL 必须来自 Evidence。
2. 官方事实必须可以回到原始公开来源，保留 Snapshot SHA-256 与 Evidence locator/hash。
3. 抓取失败、来源不可用、字段缺失、官方信息冲突时必须显式降级；不得用模型补全。
4. 项目按 lifecycle 聚合，不把单篇旧公告长期当作当前状态。
5. `VERIFIED` 新终止可覆盖旧 `VERIFIED` 招标；`UNVERIFIED` 新事件不得覆盖已验证状态。
6. 采购意向如果只公开到月份，如 `2026-05`，不得伪造成 `2026-05-01`。
7. 客户经营画像条件不足时，只能提供候选结果并继续追问；不得生成高可信个性化推荐。
8. Coverage 必须如实表达。当前天津 Pilot 为 `PARTIAL / NOT_EXHAUSTIVE`，不得宣称天津全覆盖。
9. Agnes 2.5 Flash 当前为 `GO_FOR_BENCHMARK`，尚未完成生产准确率验收；它只能做分类、匹配、追问、解释和行动建议，不能成为官方事实权威。

## 当前 P0 数据源

已实现：

- `ccgp_local_notices` — 中国政府采购网地方采购公告
- `ccgp_procurement_intent` — 中国政府采购意向
- `tjmugh_procurement` — 天津医科大学总医院市场调研/院内比选
- `tj_first_central_hospital_procurement` — 天津市第一中心医院院内比选/测试企业征集

尚未实现：

- `tj_public_resource_exchange`
- `tj_government_procurement`

## 当前关键能力

- Runtime Source Registry URL gate
- bounded exact-host HTTP fetch
- raw snapshot + SHA-256
- Evidence Fact
- CCGP TENDER / AMENDMENT / TERMINATION / AWARD lifecycle parsing
- deterministic LifecycleLinker
- official award supplier/amount
- official award product/brand/model/quantity/unit price
- procurement intent month precision
- hospital early market research / internal selection
- attachment allowlist + host/MIME/size/SHA-256 gates
- SourceHealth / Coverage Manifest
- CustomerProfile recommendation gate

## 验证

运行：

```bash
python -m compileall -q tools/medical_pilot
python -m unittest discover -s tools/medical_pilot -p "test_*.py" -v
```

GitHub Actions workflow: `.github/workflows/medical-pilot-ci.yml`

不得在 CI 没有实际执行前写 `PASS`。

## 下一步顺序

1. 确认新仓库 CI 真正执行并修完回归错误。
2. 实现 `tj_public_resource_exchange` Adapter。
3. 研究 `tj_government_procurement` 与 CCGP 的重复率和发布时间差，再决定独立 Adapter / 去重策略。
4. 加入真实附件 fixtures，并接 Docling/专用 Office parser。
5. 扩展到至少 50 条 VERIFIED 天津样本。
6. 用固定答案集跑 Agnes 2.5 Flash benchmark。
7. 事实 API 字段稳定后再开发给首批渠道客户演示的 H5/Web。
8. 后续通过 Skill / Fact API / MCP 接入 Hermes；本仓库仍保持医疗产品主代码独立。
