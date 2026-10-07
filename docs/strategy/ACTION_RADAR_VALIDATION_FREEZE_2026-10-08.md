# MedicalChannelAI｜Action Radar 阶段裁决：数据新鲜度与相关性 Gate

- 日期：2026-10-08
- 状态：VALIDATION_FREEZE
- 分支：codex/medical-action-relevance-benchmark
- Production：未修改
- 目的：保存 Action Radar 在进入真实客户试验前的证据、阻塞和架构裁决。

## 1. 当前产品关系

Action Radar 不是 MedicalChannelAI 之外的新产品。

MedicalChannelAI 继续承担：
- 官方源采集；
- Evidence First 事实核验；
- 项目生命周期；
- Opportunity Pool；
- Customer Profile；
- Followup；
- Agnes action selector；
- Vercel / Database / Runtime 基础设施。

Action Radar 是其新的商业核心层：

> 大量已核验公开机会 → 客户经营边界 → 相关性 Gate → 时间/生命周期 Gate → 少量行动卡 → Action Selector。

不新建独立仓库。

## 2. P0 数据新鲜度

已定位：
- 旧 self-hosted deep 数据在关键天津源上停留于 2026-09-27；
- Vercel intraday runtime 原先没有 tjzyefy / tjzxfc；
- tjzyefy_intent 历史设计明确为 daily deep only；
- 2026-09-28 二附院仍有开放到 2026-10-09 16:00 的医疗设备调研，旧状态可能漏失。

隔离分支：
- codex/medical-action-p0-runtime-source-parity

当前设计：
- tjzyefy market research：Vercel deep + intraday；
- tjzxfc market research：Vercel deep + intraday；
- tjzyefy_intent：Vercel daily deep only；
- 三源 canonical cache 全部映射到 collector namespace v2；
- publish merge 保持 fail-closed；
- 新增 persistent automation evidence，记录：
  - deep trigger；
  - deep complete；
  - intraday chain schedule；
  - tick delivery；
  - selected source；
  - source scan；
  - last intraday snapshot。

最新验收：
- Preview deployment: dpl_BoeRMLnjm6cVJ7yT4ibjRzANqLZ1
- target: preview / null
- Python tests: 771 PASS
- Vite build: PASS
- Production: NO

仍缺：
- 下一次真实 Production Cron 的自动链验收。
- 不能用数据库快照时间反推自动刷新成功，因为历史上存在人工/其他 AI 刷新数据。

## 3. Agnes relevance benchmark

设计：
- 15 cases × 3 personas = 45 classifications；
- labels:
  - DIRECT_MATCH
  - POSSIBLE_MATCH_NEEDS_CONFIRMATION
  - NOT_MATCH
- Expected labels 不发送给模型；
- 模型不能创建新产品/资格/日期/金额。

真实 GitHub Actions benchmark：
- 45/45 request 均 AGNES_HTTP_401；
- 原始版本错误地表现成 0%；
- benchmark runner 已修正为 BLOCKED_PROVIDER_AUTH / benchmark_pass=None。

Production 独立探针：
- 公开 VERIFIED opportunity；
- POST production /api/ai/analyze；
- HTTP 200；
- decision_source = SHARED_GROUNDED_AI_PUBLIC_FACTS_ONLY。

裁决：
**Production Agnes 当前有效；GitHub Actions AGNES_API_KEYS Secret 失效或不同步。**
因此不能根据 CI 401 判断 Agnes 分类能力。

## 4. Deterministic Gate v0

设计集：
- 45 / 45 exact；
- hard-negative FP = 0%；
- direct recall = 100%。

冻结后第一套真实 production holdout：
- 21 opportunities × 3 profiles = 63 classifications；
- exact accuracy = 88.9%；
- hard-negative FP = 4.1%；
- direct recall = 77.8%；
- 7 failures。

失败归因为：
1. 买方/使用场景错误匹配：食品药品/市场监管实验室 ≠ 医院临床渠道；
2. 设备 vs 耗材语义混淆；
3. 标题存在直接产品，但 product_items 不完整；
4. 精确别名与邻近产品混在同一级；
5. 泛科室/泛耗材只能判 POSSIBLE。

## 5. Structural Gate v1

v1 新增：
- allowed buyer scope；
- direct aliases；
- possible aliases；
- related categories；
- broader title/category signal；
- 更保守的 BROAD_CATEGORY 规则。

结果：

### 设计集
45 decisions：
- exact = 100%
- hard-negative FP = 0%
- direct recall = 100%
- possible→direct overclaim = 0

### 第一套旧 holdout 回归
63 decisions：
- exact = 100%
- hard-negative FP = 0%
- direct recall = 100%
- overclaim = 0

### 第二套 post-freeze production holdout
20 opportunities × 3 profiles = 60 decisions：
- exact = 95.0%
- hard-negative FP = 0.0%
- direct recall = 100.0%
- possible→direct overclaim = 0
- failures = 3

三个失败：
- J08/C：微生物基因测序系统 → 应 POSSIBLE，v1 NOT_MATCH；
- J14/A：染色体扫描/制片/染片 → 应 POSSIBLE，v1 NOT_MATCH；
- J20/A：切片柜等 → 应 POSSIBLE，v1 NOT_MATCH。

共同特征：
**都不是确定性直接匹配；都是需要行业语义理解的邻近机会。**

## 6. 架构裁决

不继续把确定性别名表扩成一个难维护的“医疗词典”。

采用 Hybrid Relevance Gate：

### Layer 0｜Evidence Gate
只允许 VERIFIED 官方事实。

### Layer 1｜Buyer / Use-case Scope
确定性排除明确不属于客户市场的买方与使用场景。

例：
- 医院临床；
- CDC；
- 市场监管/药检；
- 科研；
必须由客户画像明确选择，不能假设所有医疗相关单位都属于客户市场。

### Layer 2｜Deterministic High-Precision Match
处理：
- 精确产品；
- 客户明确品类；
- 已确认别名；
- 产品形态（设备/耗材/试剂/服务）；
- 明确 hard negative。

输出：
- DIRECT_MATCH；
- POSSIBLE_MATCH_NEEDS_CONFIRMATION；
- HARD_NOT_MATCH；
- UNRESOLVED_SEMANTIC。

### Layer 3｜Agnes Ambiguity Review
只处理 UNRESOLVED_SEMANTIC。

典型：
- 微生物基因测序 vs 检验设备；
- 染色体/染片 vs 病理设备；
- 切片柜 vs 病理相关设备；
- 设备维保 vs 设备经销能力；
- 宽泛科室/耗材标题。

Agnes 不能把 HARD_NOT_MATCH 翻回相关，也不能扩大 Customer Profile。

### Layer 4｜Existing Action Selector
只有 relevance 通过后才进入现有 action code selector。

## 7. 为什么这个结构优于“All Agnes”

- 明确无关信息不耗模型调用；
- 明确产品匹配不需要 LLM 决策；
- AI 只处理真正需要语义判断的少数边界；
- GitHub/Agnes API 暂时异常时，基础过滤仍可工作；
- 更容易解释“为什么推送/为什么不推”；
- 更适合免费/低成本 Agnes 作为信息差放大器，而不是单点依赖。

## 8. 当前禁止项

在以下两项通过前：
1. P0 Production 自动 freshness 验收；
2. Agnes ambiguity benchmark 使用有效测试凭据完成；

禁止：
- 对真实客户宣称“实时每日雷达”；
- 启动 7 天付费 Pilot；
- 把 relevance Gate 合入 Production；
- 新建独立产品仓库；
- 用旧 GitHub Secret 的 401 结果评价 Agnes 能力。

## 9. 下一步

1. 下一次 Production Cron 后读取 automation evidence，确认：
   - deep trigger；
   - deep complete；
   - chain scheduled；
   - tick delivered；
   - source scanned；
   - intraday snapshot refreshed。
2. 同步/更新 GitHub Actions Agnes Secret 后，只跑 ambiguity cases，而不是再对全部机会调用 Agnes。
3. 统计真实 Opportunity Pool 在 Hybrid Gate 下：
   - hard excluded；
   - deterministic direct；
   - deterministic possible；
   - AI review；
   - final pushed；
   以此估算每天实际 Agnes 调用量和客户看到的信息量。
4. 两项通过后再进入 3 个真实医疗渠道客户的 7 天小额付费验证。
