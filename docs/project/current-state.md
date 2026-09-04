# MedicalChannelAI current state

Updated: 2026-09-04

## Product state

MedicalChannelAI is a Tianjin-first medical-channel commercial intelligence / sales-assistant pilot for medical devices, IVD and consumables.

Fixed rules:

- public medical/procurement facts require traceable official evidence; unsupported critical facts remain empty;
- models may classify, match, explain and recommend actions, but may not invent hospitals, projects, budgets, dates, contacts, suppliers, brands, relationships or win probability;
- public intelligence and customer-private resources are separate layers;
- target hospitals are watch/focus objects only and never add relationship points;
- hospital relationships and product capabilities are used only after customer confirmation;
- private outcomes may support current-account review but never become public facts or automatically alter public ranking.

`production_ready=false`.

## Source-control and deployment boundary

- Active branch: `chatgpt/opportunity-ranking-v2-final`
- Draft PR: `#6` — `v0.4.1: opportunity ranking v2 final`
- Latest fully code-validated executable/runtime HEAD: `968cb674c6d543bba0f0bbef00aa4b444a314e88`
- Latest successful full validation: GitHub Actions **Verify #1426 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` disables automatic Vercel deployments for this branch.
- User boundary remains: **no Preview generation, no Production changes/deployments, no merge** until explicitly changed.
- Latest observed Vercel deployment remains historical commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` / `dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre` (ERROR); the current performance/CRM work produced no Preview.

## Executable validation state

### Active CI path: GCP self-hosted runner

MedicalChannelAI remains private and uses the repository-scoped GCP self-hosted runner after private GitHub-hosted jobs repeatedly failed before Checkout.

- runner: `medicalchannelai-gcp-1`
- labels: `self-hosted`, `linux`, `x64`, `medicalchannelai-ci`
- VM: Ubuntu 25.10 / x86_64
- system Python: 3.13.7
- Node: 24.20.0
- Verify triggers: `pull_request` + `workflow_dispatch`
- duplicate branch-push Verify removed;
- npm Actions cache upload disabled; persistent VM local cache is used instead.

The GCP instance is **CI infrastructure only**. It is not in the user request path and therefore does not by itself make China user access slower.

### Latest green validation

Verify **#1426** completed successfully for `968cb674c6d543bba0f0bbef00aa4b444a314e88` and executed:

- Checkout;
- system Python verification;
- Node 24 setup;
- `npm ci`;
- bundled snapshot refresh;
- **510 Python pipeline/contract tests — all PASS**;
- serverless entrypoint checks (`11/12` configured slots);
- verified snapshot / medical-channel / private-profile / AI-boundary / runtime checks;
- full prebuild;
- TypeScript `tsc --noEmit`;
- Vite production build;
- ranking summary.

This is code/build validation only. It does **not** constitute current-HEAD Vercel runtime acceptance because Preview is intentionally disabled.

## China-access / runtime latency work

The current optimization principle is to reduce cross-border round trips before changing regions. Current Neon is on **AWS `us-east-2` (Ohio)**. `vercel.json` does not force a Function region. Do not move only Vercel Functions to Asia while the database remains in Ohio; that can turn one user-side cross-border hop into repeated Function-to-database cross-region hops. Any future regional change should be based on measured China TTFB/P95 and preferably move the dynamic API and database together.

Validated performance work now includes:

- `/today` customer-private profile reads reduced from four SQL queries to **one bounded aggregate query**;
- `/today` follow-up + recommendation feedback + `today_limit` reads reduced from three SQL queries to **one query**; the Today private-data path is roughly reduced from ~7 DB round trips to ~2;
- private and public schema bootstrap use schema-version fast paths; full DDL/migration runs only when the schema version changes and is serialized;
- public history materialization is side storage scheduled with Vercel `waitUntil()` on Vercel runtime, so it no longer blocks the main `/today` response; same-snapshot duplicate materialization is suppressed within a warm instance;
- detail page initial opportunity and follow-up reads are parallel rather than serial;
- public fact-version history on detail is **on demand**, not fetched on every detail open;
- confirmed follow-up mutations use a bounded one-shot server-confirmed response reuse path, avoiding immediate redundant GETs on Today/detail;
- Today runtime status and due reminders are auxiliary/non-blocking; the main Today data no longer waits for `/reminders`;
- login/register has a **10-second, one-shot, in-memory-only authenticated-user handoff** so the same SPA navigation does not immediately repeat `/auth/me`; refresh/new tab/cross-tab flows remain server-authoritative;
- `viteSingleFile()` was removed, restoring normal hashed JS/CSS assets and Vercel `/assets/*` immutable caching;
- secondary routes are lazy-loaded; Login is lazy-loaded while Today remains eager;
- Runtime Trial / Static Snapshot / Mock service implementations are deferred and do not statically ride the real Pilot service path;
- demo reset dependencies are requested only on the non-API reset action; `localCustomerProfile` builds as its own deferred chunk;
- `aiDecisionApi` is no longer part of the authenticated Pilot Today initial bundle; public-demo cache hydration loads it only in demo mode, and real Pilot loads it only after explicit AI analysis;
- `OutreachDrawer` is no longer part of Today initial delivery; it loads only after the user explicitly opens the communication-draft action;
- NotFit/Remind remain eager inside Today intentionally to avoid over-fragmenting common CRM actions into too many small static requests.

### Production build delivery result

Historical single-file build:

- `index.html`: **659.76 kB**, gzip **192.66 kB**.

Full Verify #1426 production build:

- `index.html`: **0.62 kB**, gzip **0.38 kB**;
- CSS: **41.30 kB**, gzip **8.09 kB**;
- main JS: **358.43 kB**, gzip **115.16 kB**;
- `aiDecisionApi`: **5.43 kB**, gzip **2.66 kB**;
- Login: **6.58 kB**, gzip **2.68 kB**;
- `localCustomerProfile`: **7.99 kB**, gzip **3.11 kB**;
- OutreachDrawer: **12.16 kB**, gzip **4.72 kB**;
- Opportunity Pool: **18.45 kB**, gzip **6.97 kB**;
- Followed: **20.95 kB**, gzip **7.37 kB**;
- Pilot Resources: **23.18 kB**, gzip **6.76 kB**;
- Opportunity Detail: **50.45 kB**, gzip **15.88 kB**;
- Radar: **57.59 kB**, gzip **17.29 kB**.

Progressive main-bundle reduction:

- first split build #1402: `415.64 kB / gzip 132.15 kB`;
- #1413: `382.56 kB / gzip 122.48 kB`;
- #1418: `375.20 kB / gzip 119.58 kB`;
- #1423 (AI client on demand): `370.34 kB / gzip 118.27 kB`;
- #1426 (Outreach on demand): **`358.43 kB / gzip 115.16 kB`**.

The Vite report still correctly notes that `localFollowupStore` cannot be isolated by the AppLayout dynamic import alone because it is also statically referenced from other lazy route/service modules. No claim is made that this module itself became a separate chunk.

## Not yet implemented

The proposed **Today light response / full Opportunity Pool response split** is still not implemented. The current core route lives in the large `web/api/private.js`; the GitHub contents write API replaces the whole file, and earlier connector reads could be truncated, so the change was deliberately not forced through a risky whole-file rewrite. It also should not be implemented as an extra Vercel Function merely to avoid the edit, because the project currently uses 11/12 configured serverless slots and an extra proxy would add latency rather than remove it.

After #1426, further tiny Today chunk splitting is intentionally paused. The next performance target is the **response payload / backend path**, not another modal-sized client split.

## Public intelligence and collector boundary

Public regional intelligence is shared/versioned independently from customer-private context. Existing guarantees include official-source discovery/detail verification, canonical VERIFIED facts, correction/termination reconciliation, public ranking without private relationship/product points, source-scoped incremental staging/barriers, 48-hour bounded carryover, ledger retention, actual Queue delivery clocks, stale cross-China-day rejection, deep/incremental serialization, and once-daily legacy deep fallback.

These remain code/contract guarantees, not current Production-runtime acceptance while Preview is disabled.

## User-facing business closure

Current pilot loop:

**discover opportunity → official evidence → confirmed private resource match → grounded outreach → explicit contact record → optional concrete next action → due-action queue → terminal result → private outcome review**.

Established behavior:

- copying outreach / tapping phone / tapping email never auto-writes `CONTACTED`;
- only explicit `已联系，记入跟进` records contact;
- reminders are independent from sales stage and require a concrete next action;
- reminder acknowledgement clears reminder only;
- `我的跟进` prioritizes due → scheduled → active → monitor → closed;
- WON / LOST / NOT_FIT / ARCHIVED require explicit reopen confirmation;
- ARCHIVED is workflow-terminal but excluded from WON/LOST/NOT_FIT statistics.

## Private outcome review

The current branch includes current-account private result review without adding a new database table or Vercel Function:

- `profile.js?route=outcome-summary` reads current-account `private_followups` / `private_followup_events` only;
- reports WON / LOST / NOT_FIT counts and decided win rate;
- >5000 terminal records fail closed;
- client rejects duplicate reason codes and inconsistent reason totals;
- WON / LOST require bounded private review factors and clearly label them current-user commercial judgments, not hospital/procurement facts;
- historical free-form/unrecognized records remain unclassified rather than guessed;
- NOT_FIT keeps structured reason;
- reopened outcomes leave current terminal statistics while old history is preserved;
- export/delete lifecycle includes outcome events;
- fewer than 5 decided outcomes do not generate a claimed business rule;
- private outcome statistics do not alter public facts/ranking.

`web/api/private.js` also enforces controlled WON/LOST transition review server-side before event/status mutation while preserving idempotency and same-terminal free-form note behavior.

## Remaining acceptance gates

While no-Preview remains active, continue only code/test/data-boundary/business-closure work without making Vercel runtime claims.

When the user explicitly allows Preview again:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively from China and record TTFB/P95 and user-perceived loading;
3. run protected Pilot smoke: explicit CONTACTED first, optional next action second;
4. verify reminder acknowledgement preserves sales stage and clears only reminder state;
5. verify private WON/LOST/NOT_FIT review persistence/export and no public leakage;
6. verify real API rejects direct WON/LOST terminal writes without controlled review;
7. verify terminal reopen preserves history and current statistics;
8. verify collector Queue/daily-deep/intraday runtime behavior and snapshot freshness;
9. verify one real same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
10. inspect custom-domain/Production promotion separately before any Production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
