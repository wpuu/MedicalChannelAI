# MedicalChannelAI 当前状态

日期：2026-08-28  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE`  
生产就绪：**false**

## 1. 当前产品目标

首个 Pilot 只证明：能否持续、可追溯地发现天津区域公开医疗商业信号，并在模型不能创造事实的前提下，结合客户真实经营条件生成可执行的销售行动建议。

产品不是医疗诊断系统；当前聚焦医疗器械、IVD、耗材的渠道经营与厂家销售场景。

## 2. 已迁入独立仓库的事实底座

- 5 个 JSON Schema：SourceRegistry / Opportunity / ProcurementEvent / EvidenceFact / CustomerProfile
- 4 个运行时 P0 Source
- 7 条真实天津 regression fixtures
- bounded collector + Snapshot SHA-256
- Evidence Fact 生成
- Procurement Intent 解析
- CCGP lifecycle 解析
- deterministic LifecycleLinker
- 中标供应商/金额与官方产品/品牌/型号/数量/单价解析
- 天津医科大学总医院早期市场调研解析
- 天津第一中心医院院内比选/测试企业征集解析
- 附件白名单、host/MIME/size/hash 安全链
- SourceHealth / Coverage 聚合
- CLI 单 URL evidence-backed 输出
- 8 组 deterministic unittest

## 3. 当前真实 fixture

1. 天津市胸科医院检验科设备租赁 — 573万元 / TENDER
2. 天津医院 SPECT/CT — TERMINATED
3. 天津市泰达医院 DR — 250万元 / TENDER
4. 天津中医药大学第一附属医院光电同步脑活动检测仪 — 390万元 / PROCUREMENT_INTENT / `2026-05` 月精度
5. 天津医科大学 GMP 实验室核心设备 — 873.27万元 / AWARD / 供应商 + 东富龙品牌型号表
6. 天津市第一中心医院手术无影灯 — INTERNAL_SELECTION / 1.98万元
7. 天津市第一中心医院医疗器械精细化管理 — MARKET_RESEARCH / 测试企业征集

## 4. 当前 Coverage

运行时已实现：

- `ccgp_local_notices`
- `ccgp_procurement_intent`
- `tjmugh_procurement`
- `tj_first_central_hospital_procurement`

必需但未实现：

- `tj_public_resource_exchange`
- `tj_government_procurement`

因此当前状态必须保持：

- `coverage_status = PARTIAL`
- `exhaustiveness_claim = NOT_EXHAUSTIVE`

## 5. Agnes 2.5 Flash

状态：`GO_FOR_BENCHMARK`

尚未完成真实 API 医疗准确率生产验收。

允许：

- 医疗产品分类
- 取得文档后的辅助结构化
- 客户能力/商机匹配
- 缺失条件追问
- 确定性评分解释
- 销售行动建议

禁止成为事实权威：

- 采购人/医院
- 项目名
- 预算
- 日期/截止时间
- 生命周期状态
- 中标供应商/金额
- 官方产品品牌型号数量价格
- 来源 URL

## 6. 当前迁移验证状态

代码、Schema、fixtures 和测试已经迁入 `wpuu/MedicalChannelAI` 的 `dev/tianjin-pilot-v0.1`。

**仍需以新仓库 GitHub Actions 的实际运行结果为准。**

迁移前 Upan 的 CI 存在 runner 未分配问题，因此不能继承任何 PASS 结论。

## 7. 下一步

1. 打开 Draft PR 并确认新仓库 Medical Pilot CI 真正执行。
2. 如果有 assertion/import 错误，先修到 deterministic tests 全绿。
3. 实现天津公共资源 Adapter。
4. 做天津政府采购原始站 vs CCGP 去重/时效差研究。
5. 加真实附件样本与 PDF/DOCX/XLSX 解析。
6. 扩到 >=50 VERIFIED 天津样本。
7. 跑 Agnes 2.5 Flash benchmark。
8. 最后才进入 H5/Web 演示端。
