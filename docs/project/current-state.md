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
- Latest fully code-validated executable/runtime HEAD: `d344e1169484152fb408e985d55885b72b76ff75`
- Latest successful full validation: GitHub Actions **Verify #1438 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` disables automatic Vercel deployments for this branch.
- User boundary remains: **no Preview generation, no Production changes/deployments, no merge** until explicitly changed.
- Latest observed Vercel deployment remains historical commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` / `dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre` (ERROR); no current performance/CRM/tjzxfc work is deployed.

## Executable validation state

MedicalChannelAI remains private and uses the repository-scoped GCP self-hosted runner:

- runner: `medicalchannelai-gcp-1`
- labels: `self-hosted`, `linux`, `x64`, `medicalchannelai-ci`
- system Python: 3.13.7
- Node: 24.20.0
- GCP runner is CI/collector infrastructure only and is not in the end-user request path.

Verify **#1438** completed successfully for `d344e1169484152fb408e985d55885b72b76ff75` and executed:

- Checkout and system Python verification;
- Node 24 / `npm ci`;
- bundled snapshot refresh;
- **535 Python pipeline/contract tests — all PASS**;
- serverless entrypoint checks **11/12**;
- verified snapshot / medical-channel / private-profile / AI / runtime boundary checks;
- full prebuild;
- TypeScript `tsc --noEmit`;
- Vite production build;
- ranking summary.

This is code/build validation only. Preview is intentionally disabled, so no current-HEAD Vercel runtime acceptance is claimed.

## China-access / Today performance

Validated work includes:

- Today customer-private profile reads reduced from four SQL queries to one bounded aggregate query;
- Today follow-up + recommendation feedback + `today_limit` reads reduced from three SQL queries to one query; private Today path is roughly ~7 DB round trips → ~2;
- private/public schema bootstrap use version fast paths;
- public history materialization is after-response side storage;
- detail initial opportunity/follow-up reads are parallel and public history is on demand;
- confirmed follow-up mutations use bounded one-shot server-confirmed response reuse;
- Today runtime status/reminders are auxiliary and non-blocking;
- login/register uses a 10-second one-shot in-memory auth handoff while refresh/new-tab stays server-authoritative;
- normal hashed assets and immutable caching restored; secondary routes/Login/demo-only services are deferred;
- AI client and OutreachDrawer are on demand;
- normal `/api/today` omits the full `opportunity_pool` while preserving Top-N cards and `opportunity_pool_count`;
- `/api/opportunity-pool/today` explicitly requests the complete pool through the **same** private Function using `include_pool=1`; no extra Function slot or DB request was introduced;
- separate primary/full-pool service delegates prevent short mutation reuse state from being mistaken for the full pool.

The Today response split reduces serialization and cross-border response bytes. `_privateCore.js` still constructs/personalizes the full pool before projection, so no additional DB/CPU reduction is claimed from this split.

### #1438 production build

- `index.html`: **0.62 / gzip 0.38 kB**
- CSS: **41.30 / gzip 8.09 kB**
- main JS: **358.88 / gzip 115.27 kB**
- AI client: **5.43 / gzip 2.66 kB**
- OutreachDrawer: **12.16 / gzip 4.72 kB**
- Opportunity Pool: **18.45 / gzip 6.97 kB**
- Opportunity Detail: **50.45 / gzip 15.89 kB**
- Radar: **57.59 / gzip 17.29 kB**

No frontend bundle increase came from the new Python collector source or daily-deep workflow integration.

## New official early-signal source: 天津市中心妇产科医院 (`tjzxfc`)

The branch now contains a verified-adapter implementation for the official hospital domain `www.tjzxfc.cn` and procurement/notice index `https://www.tjzxfc.cn/ywgk/zbgg/index.shtml`.

Implemented files:

- `web/pipeline/medical_channel_pipeline/tjzxfc_discovery.py`
- `web/pipeline/medical_channel_pipeline/tjzxfc_market_research.py`
- `web/pipeline/scripts/sync_tjzxfc_market_research.py`
- dedicated discovery/detail/sync tests.

Boundary rules:

- index discovery may admit official market-research candidates without prematurely guessing medical scope;
- detail verification must prove medical-channel relevance from the project title, extracted equipment/product names or explicit medical department/category evidence;
- hospital identity alone is never enough;
- generic facility/IT/meeting-room research is rejected rather than entering public opportunity facts;
- title and official publication-date identity must agree;
- exact deadline time is stored only if published; date-only deadlines remain date-only;
- unsupported non-medical research is recorded as unsupported rather than making the whole hospital-source refresh fail;
- true network, title/date or supported-detail verification failures remain fail closed;
- minimum detail delay is 3 seconds.

The original adapter feature was introduced at `7283ac65f3194b30cbb26252d577711f75907c88`; Fast Verify #1434 and Full Verify #1435 validated the adapter itself. Full #1438 additionally validates its daily-deep integration.

## Daily-deep integration

The PR version of `.github/workflows/tianjin-medical-refresh.yml` now:

- runs on the already validated `medicalchannelai-gcp-1` self-hosted labels rather than private `ubuntu-latest` hosted capacity;
- uses system `python3`, avoiding the known Ubuntu 25.10 `setup-python` compatibility problem;
- runs `sync_tjzxfc_market_research.py` with a **30-day lookback, max 20 candidates and 3-second minimum delay**;
- safely handles the first run when no `tianjin_live_tjzxfc_records.json` exists;
- feeds verified `tjzxfc` records into `publish_web_snapshot.py`;
- includes the live records and sync report in the verified data commit;
- keeps the existing once-daily schedule only.

**Important runtime boundary:** PR #6 is still Draft and unmerged. GitHub scheduled workflows execute from the default branch, so this new daily-deep definition is **code-validated but not yet the active main-branch schedule**. No claim is made that `tjzxfc` is already being collected every day.

`tjzxfc` is intentionally **not** in the intraday incremental scheduler. Tests lock this boundary. Higher-frequency collection should only be considered after real runtime evidence shows daily deep is insufficient and the source can tolerate the extra load.

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
- current intraday sources remain explicitly bounded and `tjzxfc` is not silently added.

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
7. verify `tjzxfc` real network parsing on an allowed runtime before claiming that source operational;
8. run one same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
9. inspect custom-domain/Production promotion separately before any Production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
