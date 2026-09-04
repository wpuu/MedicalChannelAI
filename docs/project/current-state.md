# MedicalChannelAI current state

Updated: 2026-09-04

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
- Latest fully code-validated executable/runtime HEAD: `325dd59cd4e6c9c243516b6d248b742a9be98cef`
- Latest successful full validation: GitHub Actions **Verify #1452 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` disables automatic Vercel deployments for this branch.
- User boundary remains: **no Preview generation, no Production changes/deployments, no merge** until explicitly changed.
- Latest observed Vercel deployment remains historical commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` / `dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre` (ERROR); no current source-expansion work is deployed.

## Executable validation state

MedicalChannelAI remains private and uses repository-scoped GCP self-hosted runner `medicalchannelai-gcp-1` with labels `self-hosted`, `linux`, `x64`, `medicalchannelai-ci`.

Verify **#1452** completed successfully for executable HEAD `325dd59cd4e6c9c243516b6d248b742a9be98cef` and executed:

- system Python 3.13.7 and Node 24.20.0;
- `npm ci` and bundled snapshot refresh;
- **558 Python pipeline/contract tests — all PASS**;
- serverless entrypoint checks **11/12**;
- verified snapshot / medical scope / private profile / AI / runtime boundary checks;
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
- lifecycle currently supported: `MARKET_RESEARCH`

Validated behavior:

- broad official market-research discovery with strict detail medical-scope verification;
- hospital identity alone never makes a record relevant;
- non-medical facility/IT research is unsupported rather than published;
- title and official publication date must agree;
- exact deadline time is stored only when official text publishes it; otherwise date-only remains date-only;
- true verification/network failures fail closed;
- minimum detail interval 3 seconds;
- 30-day / max-20 daily-deep wiring feeds unified snapshot and verified data commit;
- intentionally not in intraday scheduler.

Adapter Fast #1434 / Full #1435 passed; daily-deep integration Fast #1437 / Full #1438 passed.

## Official early-signal source: 天津中医药大学第二附属医院 (`tjzyefy`)

Official source:

- domain: `www.tjzyefy.com`
- announcement index: `https://www.tjzyefy.com/xwgg/ggtz/`
- supported lifecycle in this adapter: `MARKET_RESEARCH`

Implemented and validated files include discovery, strict detail parser, standalone sync and dedicated tests.

### Medical recall and grounding boundary

The initial adapter only admitted titles containing generic markers such as `医疗设备` / `医用耗材` / `试剂`. Real official pages showed this would miss valid medical-channel opportunities such as `高分辨液质联用系统三年期维保项目`.

The corrected implementation therefore:

- still requires a research notice and explicitly excludes `采购意向公告`;
- uses the shared medical-channel taxonomy at discovery time rather than a few generic words;
- extends the shared laboratory scope with `液质联用` / `液相色谱` / `色谱` while preserving the rule that the hospital name itself is not relevance evidence;
- keeps strict official detail verification for hospital identity, title, publication date, product/service object and registration window;
- does not invent a generic `医疗设备` category for an LC-MS maintenance notice whose title does not state that category;
- keeps `product_categories=[]` when the official page only proves specific equipment/service objects;
- rejects procurement-intent notices rather than relabeling them as market research;
- preserves date-only deadlines without invented times;
- retries only transient fetch failures and uses a minimum 3-second detail interval;
- remains outside the intraday scheduler.

The corrected adapter passed Fast Verify #1449 and Full Verify #1450 with 556 tests. Daily-deep wiring then passed Fast #1451 and **Full #1452 with 558 tests**.

### `tjzyefy` daily-deep wiring

The PR version of `.github/workflows/tianjin-medical-refresh.yml` now runs the source with:

- one shared authoritative China-time refresh clock;
- **30-day lookback**;
- **max 20 candidates**;
- **minimum 3-second delay**;
- safe first-run behavior when no prior `tianjin_live_tjzyefy_records.json` exists;
- unified public snapshot input;
- verified live-record/report data commit.

**Important runtime boundary:** PR #6 is unmerged. GitHub scheduled workflows execute from the default branch, so the `tjzxfc` and `tjzyefy` daily-deep definitions are **code-validated but are not yet active main-branch schedules**. No claim is made that either new source is already being collected every day.

## Procurement-intent boundary

The same `tjzyefy` official announcement stream contains `采购意向公告`, including medical-equipment purchase intentions. These can occur earlier than supplier-facing market research, but they are intentionally **not supported yet**.

Reason: the current pipeline does not yet have a separately validated procurement-intent actionability contract. Simply mapping such records to `MARKET_RESEARCH` would misstate the official lifecycle, and treating a no-registration-window intent as a normal immediate opportunity could over-rank it. The next architecture step is to determine whether existing `PRE_MARKET_SIGNAL` semantics can safely represent procurement intent or whether a distinct lifecycle/action mode is required.

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
- `tjzxfc` and `tjzyefy` are not silently added to intraday collection.

## Business-closure loop

Current pilot loop remains:

**discover opportunity → official evidence → confirmed private resource match → grounded outreach → explicit contact record → optional concrete next action → due-action queue → terminal result → private outcome review**.

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
4. run protected CONTACTED → optional next-action → reminder acknowledgement flow;
5. verify private WON/LOST/NOT_FIT review persistence/export and no public leakage;
6. verify collector Queue / daily-deep / intraday runtime behavior and snapshot freshness;
7. verify `tjzxfc` / `tjzyefy` real network parsing on an allowed runtime before claiming those sources operational;
8. run one same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
9. inspect custom-domain/Production promotion separately before any Production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
