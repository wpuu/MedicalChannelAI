# MedicalChannelAI current state

Updated: 2026-11-06（Asia/Shanghai）

## 当前新版 Preview 隔离周期（运行中）

- 代码 `2cc47ce5cae29f8eed57b411e647ccc356372719`，[Preview](https://medicalchannelai-p1uolbsrn-rerisse7-1717s-projects.vercel.app) `dpl_8oRuWziEBXmq1wKfVxZTSUosErYG` READY；周期标识 `mcai-p0-20261106-a`。
- 新独立数据库/受限角色 `mcai_p0_epoch_20261106a`，原测试分支 `br-cold-tooth-a5clhljh`；旧部署及旧库保留作对照。新周期缓存、消息/幂等键和发布/触发凭据与旧周期分开，数据库连接前校验指定库名。
- 889个Python测试、全部JS合约、TypeScript、Vite通过。启动前新库0快照、采集状态为空；旧cron凭据403、旧发布凭据401；新角色不能读旧快照或在旧库建表。
- 北京时间12:11启动真实Queue，非202即验收通过。[本轮运行报告](preview-epoch-cycle-2026-11-06.md)仍为进行中；最终权威发布、SQL精确时间和浏览器结果待补齐。
- 已观察到非空事件watch8个项目，其第一批核验失败后六个事件阶段降级；其他医院来源继续。TEDA403一次即降级；北京受限后fallback直接依赖降级，河北当前也限流。不能记为全部来源恢复。
- `production_ready=false`，不合并、不提升Production，不修改域名/DNS/EdgeOne。旧周期46条/6项浏览器及旧微秒重放结果仅属于上一阶段，不作为本轮完整运行证据。

## 上轮来源故障处理与精度修复（e48990c，历史记录）

- 最新可执行代码：`be87e5f34e088b7d39c381d5855030694b27d568`；[Preview](https://medicalchannelai-ix8zm70ut-rerisse7-1717s-projects.vercel.app) `dpl_F9c2jc8uJuiPELzoHY8rxGZc7aRH` READY，精确版本已读回。工作树/分支不变，原工作树干净。
- [本轮修复与验收报告](source-recovery-precision-2026-11-06.md)及[冻结证据](validation/source-recovery-2026-11-06/manifest.json)是本轮依据；下方47条/878测试/34浏览器项属于上一阶段，保留历史绑定。
- 完整构建884个Python测试、全部JS合约、TypeScript、Vite通过；本轮浏览器6项通过，4次自动AI缓存读取被测试护栏阻断，未发AI请求。
- 已修区域安全诊断、限流后查询止损、依赖终局降级后的fallback无效重试、明确拒绝访问的一次降级、数据库/缓存微秒版本比较和旧行相同payload重放修复。
- 云端对真实46条快照做相同内容重放，SQL时间与JSON微秒精确相等；早1微秒回退和同刻冲突均409拒绝，权威/普通GET/浏览器/冻结payload同SHA `45709c27420c7e856b69fd8b168237b12f3a71664bf982c68f8e825db1ef0488`。没有构造新测试版本或改事实/健康时钟，未批量迁移历史行。
- TEDA正常访问仍403；辽宁本轮真实本地请求限流，最终代码1次查询即止。程序侧修复不表示外部来源恢复，也不能解释昨天未保存明细的失败。
- 北京时间11:30旧部署a3f94bd自动tick及发布已实际观察；47→46是吉林一条项目当日09:30投标截止后退出池。持续调度未验收，新版完整Queue周期未触发；旧部署消息仍按旧代码处理，需后续处理旧消费者和版本隔离。
- `production_ready=false`。Production于2026-11-06T03:46:56.710Z只读复核仍`3216fd9`/`dpl_4LPKoTdusrvbExXuzbMKtnyiT86C` READY，SSO不变；本轮临时访问已撤销。未合并、提升Production或改域名/DNS/EdgeOne。

## 上轮真实采集与发布验收（6a1ec6c，历史记录）

- 工作树 `/workspace/MedicalChannelAI-p0`，分支 `codex/p0-reliability-contracts`；原工作树保持干净。
- 最新可执行/UI代码 `4575fa4e7721a234d74dd87e35163631019ec2c9`，对应 [UI Preview](https://medicalchannelai-j4ktac1cu-rerisse7-1717s-projects.vercel.app)，`dpl_7QNPqMxE5oehX52mEoZgjYzua2Vm`；READY；当前部署浏览器34/34通过，保持部署保护。
- 完整采集发布由 `a3f94bdd45ec1442c2031b46f640e8ca7a52be03` / `dpl_CCdUVJdpao3rse7QbczHVxvLsx8y` 实际执行；新 UI 未重新采集或手工发布。后续文档提交不改变这两个代码/部署绑定。
- 阶段：**LIVE_PUBLICATION_VERIFIED_WITH_DEGRADED_SOURCES**。`production_ready=false`；12/14来源成功，不能称全部来源恢复或持续调度通过。
- 当前依据：[验收合同](action-radar-acceptance-contract.md)、[本轮真实采集及发布报告](live-source-publication-acceptance-2026-11-06.md)、[冻结证据清单](validation/live-source-2026-11-06/manifest.json)。[此前受控验收](preview-acceptance-2026-11-06.md)保留079fa2e版本的45项HTTP及18/9/5项浏览器记录，不充当本轮新版本实测。
- 用户授权继续 Preview 三源与完整发布验收；未合并、部署/提升 Production，未改域名、DNS、EdgeOne、生产凭据或生产数据。

本轮真实页面及运行又修复：官方入口空壳检查、GB2312无损解码、妇产泛调研及正文用途解析、独立现场调研时间和跨端窗口关闭、未完成详情的 staging/barrier、硬停恢复事实丢失、二附院实际药品检验服务模板、增量失败安全诊断、原生 Queue 最大投递3次，以及市县地区造成11条记录漏显。之前的P0权威写入/读回、AI30小时门禁、账户隔离及固定可信代理继续通过回归。

| 验证 | 结果与边界 |
|---|---|
| 最新完整构建 | PASS；878个Python测试、全部JS合约/Prebuild、TypeScript、Vite；主JS gzip116.00kB |
| 三源真实deep | 调研8条事实；意向2条事实+1条不支持；妇产1条事实+4条设施类排除；三源deferred/staging/barrier均0，不等于净新增数 |
| 完整Queue周期 | 25阶段：22完成、3降级；3降级阶段对应TEDA/辽宁两个逻辑来源；触发响应至发布约44分44秒 |
| 权威发布 | canonical总数964、当前池47、Today5、事件0；durable确认、cache READY、active cycle释放、无人工qa_fixture |
| 数据一致性 | producer、Neon完整JSON、强制authority GET三SHA一致：`2ef3e305844ace80b056222993f4a6fc1fdc9cc5e5a1655eeda0088d8f146ee1` |
| 最终普通浏览器 | 普通GET首次CDN HIT/Age1，完整SHA一致；34/34检查、地区逐ID/依据链接、11条恢复、跟进刷新、390px四页通过；23次自动cache_only由测试护栏阻断，未发AI请求 |
| 首次普通浏览器 | 普通CDN GET相同SHA；发现真实11条漏显bug，已修复；首次脚本2处分母断言错误另记，不计产品故障 |
| 地区服务回归 | 原47条完整payload不变；ALL47/TJ8/BJ10/HL10/HE10/JL9/LN0；哈尔滨首卡保持HL；新UI浏览器34/34通过 |
| 真实降级 | TEDA官方403；辽宁详情核验聚合gate失败、原因明细缺失；辽宁fallback缺上游结果仍无效重试 |
| Production对照 | 仍为`dpl_4LPKoTdusrvbExXuzbMKtnyiT86C` / `3216fd9` / READY；SSO设置不变 |

唯一测试目标为独立Neon分支 `br-cold-tooth-a5clhljh` 的 `mcai_p0_acceptance_final`。权威逻辑时钟 `2026-11-06T01:43:03.095559+08:00`，实际发布 `2026-11-05T18:27:47.698032Z`。payload与哈希完整一致；SQL timestamptz列因Postgres.js/JavaScript Date截到毫秒，相差559微秒，不能称SQL列微秒精确相等。模型key为空，前一a3真实503仅验证降级提示；最终UI复验未再发AI请求。临时验收访问已撤销；Production与SSO于2026-11-05T18:46:26.401Z再次只读确认不变。

仍待推进：TEDA合法入口恢复、辽宁安全失败明细及依赖降级时跳过无效重试；版本时钟精度统一；来源分页/详情预算补齐和连续水位回补；非空事件链、持续自动tick、真实模型、国内P95及客户相关性/资格。已登记 `2026-11-06 11:30+08` 首个tick，尚未观察执行。CCGP仅扫描11月4日至6日；北京29候选只核验所选10条，其余是否医疗/有效未知。47条当前池不代表47条客户合格商机，964不代表本轮新增。

源级24/48小时、AI30小时阈值仍是工程初值；Gold Set15例仍是缺证规则冒烟稿。建议先修来源故障和依赖重试，再设计每源独立提交＋显式覆盖/水位，随后实施产品子项匹配与资格三态；不以单个健康标签或测试数代替产品/商业验收。

## 历史记录（截至 2026-09-04；以下不表示当前状态）

以下原文保留历史架构、CI 和源接入背景。历史分支、PR、runner、快照日期、部署状态及 PASS 只适用于其对应记录，未在本轮重新查询远端，不得解释为当前本地工作树或线上状态。旧 `checkpoint.json` 报告 #1457/558 测试，下方原文报告 #1472/581 测试；二者作为历史快照分别保留，不拿其中任何数字替代本轮验证。

## Product and safety boundary

MedicalChannelAI is a Tianjin-first medical-channel commercial intelligence / sales-assistant pilot for medical devices, IVD and consumables.

Fixed rules:

- public medical/procurement facts require traceable official evidence; unsupported critical facts fail closed;
- models may classify, match, explain and recommend actions, but may not invent hospitals, projects, budgets, dates, contacts, suppliers, brands, relationships or win probability;
- public intelligence and customer-private resources are separate layers;
- target hospitals are watch/focus objects only and never add relationship points;
- hospital relationships and product capabilities are used only after customer confirmation;
- private outcomes may support current-account review but never become public facts or automatically alter public ranking.

`production_ready=false`.

## Source-control and deployment boundary

- Active branch: `chatgpt/opportunity-ranking-v2-final`
- Draft PR: `#6` — `v0.4.1: opportunity ranking v2 final`
- Latest fully code-validated executable/runtime HEAD: `3663507b13dc57ca8d8179c51ae5b94303e936da`
- Latest successful full validation: GitHub Actions **Verify #1472 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` disables automatic Vercel deployments for this branch.
- User boundary remains: **no Preview generation, no Production changes/deployments, no merge** until explicitly changed.
- Latest observed Vercel deployment remains historical commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` / `dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre` (ERROR); no current source-expansion work is deployed.

## Latest executable validation

MedicalChannelAI remains private and uses repository-scoped GCP self-hosted runner `medicalchannelai-gcp-1` with labels `self-hosted`, `linux`, `x64`, `medicalchannelai-ci`.

Verify **#1472** completed successfully for `3663507b13dc57ca8d8179c51ae5b94303e936da` and executed:

- system Python **3.13.7** and Node **24.20.0**;
- `npm ci` and bundled snapshot refresh;
- **581 Python pipeline/contract tests — all PASS**;
- serverless entrypoint checks **11/12**;
- verified snapshot / medical scope / private profile / AI / runtime / collector boundaries;
- full prebuild;
- TypeScript `tsc --noEmit`;
- Vite production build;
- ranking summary.

Production build remains unchanged:

- `index.html`: **0.62 / gzip 0.38 kB**
- CSS: **41.30 / gzip 8.09 kB**
- main JS: **358.88 / gzip 115.27 kB**
- AI client: **5.43 / gzip 2.66 kB**
- OutreachDrawer: **12.16 / gzip 4.72 kB**
- Opportunity Pool: **18.45 / gzip 6.97 kB**
- Opportunity Detail: **50.45 / gzip 15.89 kB**
- Radar: **57.59 / gzip 17.29 kB**

The bundled ranking snapshot used by CI is still the historical verified snapshot dated `2026-09-03T13:31:21.991132+08:00` with 19 opportunities. The new procurement-intent source is code-validated, but CI does not perform its live network collection and therefore does not prove live intent data is already present in the snapshot.

This is code/build validation only. Preview is intentionally disabled, so no current-HEAD Vercel runtime acceptance or China TTFB/P95 claim is made.

## China-access / Today performance

Validated work remains:

- Today private profile and private-state reads are bounded/aggregated, reducing the main private data path from roughly ~7 DB round trips to ~2;
- schema bootstrap uses version fast paths;
- public history materialization is after-response side storage;
- detail initial reads are parallel and public history is on demand;
- follow-up mutations use bounded one-shot server-confirmed response reuse;
- Today runtime status/reminders are auxiliary and non-blocking;
- login/register uses a short one-shot in-memory auth handoff while refresh/new-tab remains server-authoritative;
- hashed assets and lazy secondary routes are restored;
- AI client and OutreachDrawer are on demand;
- normal `/api/today` omits full `opportunity_pool` while preserving Top-N and `opportunity_pool_count`;
- `/api/opportunity-pool/today` requests the full pool through the same private Function with `include_pool=1` and no extra Function slot.

The Today response split reduces response serialization/network bytes only. `_privateCore.js` still constructs/personalizes the full pool before projection, so no further DB/CPU reduction is claimed.

## Official early-signal source: 天津市中心妇产科医院 (`tjzxfc`)

Official source:

- domain: `www.tjzxfc.cn`
- index: `https://www.tjzxfc.cn/ywgk/zbgg/index.shtml`
- lifecycle: `MARKET_RESEARCH`

Validated behavior:

- broad official market-research discovery with strict detail medical-scope verification;
- hospital identity alone never makes a record relevant;
- non-medical facility/IT research is unsupported rather than published;
- title and official publication date must agree;
- exact deadline time is stored only when official text publishes it; otherwise date-only remains date-only;
- true verification/network failures fail closed;
- minimum detail interval 3 seconds;
- PR daily-deep wiring uses 30-day lookback / max 20 candidates / 3-second minimum delay;
- intentionally not in intraday scheduler.

Adapter Fast #1434 / Full #1435 passed; daily-deep integration Fast #1437 / Full #1438 passed.

## Official source: 天津中医药大学第二附属医院 (`tjzyefy`) — market research

Official source:

- domain: `www.tjzyefy.com`
- announcement index: `https://www.tjzyefy.com/xwgg/ggtz/`
- lifecycle: `MARKET_RESEARCH`

Validated behavior includes:

- research notice discovery excludes procurement-intent notices;
- shared medical-channel taxonomy is used rather than only a few generic title words;
- `液质联用` / `液相色谱` / `色谱` are supported medical-channel signals;
- strict official detail verification for hospital identity, title, publication date, product/service object and registration window;
- a generic `医疗设备` category is not invented for a specific LC-MS maintenance notice whose title does not state that category;
- date-only deadlines stay date-only;
- only transient network failures are retried;
- minimum detail interval 3 seconds;
- PR daily-deep wiring uses 30-day lookback / max 20 candidates / 3-second minimum delay;
- intentionally not in intraday scheduler.

Corrected adapter passed Fast #1449 / Full #1450; market-research daily-deep passed Fast #1451 / Full #1452 and was reconfirmed by later full validations.

## Official source: 天津中医药大学第二附属医院 — procurement intent

The same official announcement stream also contains medical `采购意向公告`. This is now represented by a separate validated lifecycle rather than being relabelled as market research.

### Lifecycle and ranking semantics

- canonical lifecycle: `PROCUREMENT_INTENT`
- public recommendation mode: `PRE_MARKET_SIGNAL`
- `INTERVENTION_STAGE`: **12/25**
- no published registration/bid deadline means `DEADLINE_URGENCY=0`
- `model_decision_status=AWAITING_MODEL`, allowing an explicit advance-layout analysis without implying a formal tender is open
- ordinary `MARKET_RESEARCH` keeps the existing `PUBLIC_OPPORTUNITY` / **25/25** intervention-stage contract

This prevents a supplier-consultation intent from being ranked as if registration or bidding were already open.

### Discovery and evidence boundary

Procurement-intent discovery is deliberately broad across official `采购意向公告` titles, because medically valid titles such as `脉动真空灭菌器等设备采购项目` may not contain the generic phrase `医疗设备`.

The detail layer then decides scope using the actual procurement object. It verifies:

- official hospital domain and same-host index/detail identity;
- hospital identity;
- title identity;
- official publication date;
- explicit `采购意向公告` semantics;
- supplier/service-provider consultation wording;
- specific product/service objects;
- medical-channel relevance independent of hospital identity.

Non-medical procurement intents are `unsupported`, not public opportunities and not source-fatal errors. True verification/network failures remain fail closed.

The shared medical scope was narrowly extended with `流式细胞仪` and `灭菌器`; generic words such as `干燥箱` were intentionally not added solely because a hospital published them.

### Timing and contact grounding

- no registration deadline/date is invented;
- no bid deadline is invented;
- official expected procurement wording such as a month or month range is **not converted to an exact date**;
- such month/range language is recorded only through `EXPECTED_PROCUREMENT_MONTH_WINDOW_UNSTRUCTURED` while the official source remains auditable;
- public contact is used only when the official page explicitly publishes it.

### Sync and daily-deep

The procurement-intent feed has a separate fail-closed sync path:

- default 30-day lookback;
- max 20 candidates;
- minimum 3-second detail delay;
- only transient network/408/425/429/5xx failures retry;
- non-medical intent = unsupported;
- unresolved supported/unknown detail failure blocks publish unless an older VERIFIED record covers the same opportunity;
- separate live records/report files;
- records feed the unified public snapshot;
- intentionally not in intraday scheduler.

The PR daily-deep definition includes this source on the existing self-hosted GCP runner.

Validation progression:

- procurement-intent actionability Fast #1461 passed;
- discovery/detail parser Fast #1467 passed;
- sync Fast #1469 passed;
- daily-deep integration Fast #1471 passed;
- **Full Verify #1472 passed with 581 tests**.

## Daily-deep runtime boundary

The PR version of `.github/workflows/tianjin-medical-refresh.yml` includes `tjzxfc`, `tjzyefy` market research and `tjzyefy` procurement intent, all on the self-hosted runner with a shared China-time refresh clock.

**Important:** PR #6 remains unmerged. GitHub scheduled workflows execute from the default branch, so these new daily-deep definitions are **code-validated but not active default-branch schedules**. No claim is made that the new sources are already being collected every day or that current Production contains them.

## Public intelligence / collector invariants

Existing guarantees remain:

- official-source discovery/detail verification and canonical VERIFIED facts;
- correction/termination reconciliation;
- public ranking without private relationship/product points;
- source-scoped incremental staging/barriers;
- bounded carryover and ledger retention;
- actual Queue delivery clock and stale cross-China-day rejection;
- deep/incremental serialization;
- one official discovery pass per runtime scan;
- unresolved verification barrier;
- once-daily legacy deep fallback definition;
- `tjzxfc`, `tjzyefy` market research and `tjzyefy` procurement intent are not silently added to intraday collection.

## Business-closure loop

Current pilot loop remains:

**discover opportunity/early signal → official evidence → confirmed private resource match → grounded outreach → explicit contact record → optional concrete next action → due-action queue → terminal result → private outcome review**.

Key private-state guarantees remain:

- copying outreach / tapping phone / tapping email never auto-writes `CONTACTED`;
- only explicit `已联系，记入跟进` records contact;
- reminders are independent from sales stage and require a concrete next action;
- reminder acknowledgement clears reminder only;
- WON / LOST / NOT_FIT / ARCHIVED require explicit reopen confirmation;
- ARCHIVED is workflow-terminal but excluded from outcome statistics;
- WON/LOST terminal transitions require controlled private review server-side;
- private outcome statistics remain current-account-only and do not alter public facts/ranking.

## Remaining acceptance gates

While no-Preview remains active, continue only code/test/data-boundary/business-closure work without making Vercel runtime claims.

When the user explicitly allows Preview again:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively from China and record TTFB/P95, response sizes and perceived loading;
3. verify normal Today omits the full pool while Opportunity Pool receives all current opportunities from the same Function;
4. verify `PRE_MARKET_SIGNAL` UI clearly communicates “采购意向/提前布局” rather than formal open tender;
5. run protected CONTACTED → optional next-action → reminder acknowledgement flow;
6. verify private WON/LOST/NOT_FIT review persistence/export and no public leakage;
7. verify collector Queue / daily-deep / intraday runtime behavior and snapshot freshness;
8. verify `tjzxfc` / `tjzyefy` real network parsing on an allowed runtime before claiming those sources operational;
9. run one same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
10. inspect custom-domain/Production promotion separately before any Production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
