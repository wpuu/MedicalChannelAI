# MedicalChannelAI current state

Updated: 2026-11-06（Asia/Shanghai）

## 当前本地 P0 工作状态

- 工作树：`/workspace/MedicalChannelAI-p0`；原工作树保持不动。
- 分支：`codex/p0-reliability-contracts`。
- 起始 HEAD：`3216fd940dabfa7714383b6436908f9b72ff8a9c`（`3216fd9`）。
- 最终可执行代码 / 验证 HEAD：`afc19c5b87d0753a5e5ff6cf919f7b5a1fd84d27`（`afc19c5`）；前置合同提交为 `e62c2a9`。后续状态文档提交不改变该版本已验证的可执行代码。
- 权威规则：[行动雷达验收合同](action-radar-acceptance-contract.md)。Gold Set 15 例已改为规则冒烟稿，缺证用例不计 PASS。
- 当前阶段：**LOCAL_CODE_VALIDATED_NOT_DEPLOYED**。本轮 P0 本地实现、聚焦回归、完整构建及独立终审完成；无剩余本地阻塞。
- 当前验证环境：Node `24.19.0`、Python `3.12.14`。本轮实际输出为 810 个 Python 测试全部 PASS，不沿用下方历史 CI 数字。
- `production_ready=false`。未进行 Preview/Production 部署、合并、域名或凭据变更；本轮没有实时生产验收结论。

本轮实现边界：三源（`tjzyefy`、`tjzyefy_intent`、`tjzxfc`）runtime parity；单源失败隔离、日内 tick 独立兜底及过期 RUNNING 恢复；pending/barrier 保守清理；已提交快照与源级 freshness health；发布前校验及权威唯一提交；公开 AI 的 30 小时服务器新鲜度门禁；EdgeOne 固定 origin；空完整池与提醒 ACK；基线测试时钟稳定。

追加修复了总医院当前公告的真实解析故障：官方索引与 11 月 5 日详情各一次只读 GET 均为 HTTP 200，失败原因是项目以 `1、2、3、` 编号，旧解析器只识别括号编号。已冻结官方原文，新增 5 个回归；完整原文与 fixture 解析事实一致，保留 3 条原文产品和官方报名截止 `2026-11-09 17:00 +08:00`。本轮未手工写入生产商机，也未验证持续调度恢复。

本轮不实施相关性/资格门禁、项目生命周期串联、历史跟进与画像重构或商业交付。规则合同不等于这些能力已经实现，代码测试也不等于来源持续在线或客户续费价值已经成立。

本轮本地验证记录（对应上述代码 HEAD）：

| 项目 | 本轮状态 |
|---|---|
| 聚焦 P0 回归 | PASS；36 个 runtime/queue 行为测试及 publication、AI、source health、proxy 等聚焦检查通过 |
| 完整 Python pipeline tests | PASS；810 个全部通过 |
| JS 合约检查 / prebuild | PASS；全部检查通过，serverless entrypoints 11/12 |
| TypeScript / Vite build | PASS；`npm run build` exit 0，main JS gzip 115.40 KiB |
| 最终变更复核 | PASS；独立终审无剩余阻塞 |
| Preview / Production 运行验收 | NOT_PERFORMED；本轮禁止部署 |

源级过期阈值当前配置为医院源 24 小时、CCGP/区域源 48 小时；这些是已通过代码检查的工程初始值，仍待实际运行节奏与来源行为验收，不代表线上新鲜度已恢复。整体公开 AI 的 30 小时快照门禁与源级阈值是不同检查。

Gold Set / Agnes relevance benchmark 未执行，相关性和资格门禁未实现，付费探索及续费验证未开始；本轮 PASS 不覆盖这些事项。

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
