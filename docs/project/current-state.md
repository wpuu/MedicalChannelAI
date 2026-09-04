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
