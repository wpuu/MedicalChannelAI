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
- Latest fully code-validated executable/runtime HEAD: `72a9ffd3d368fdd11b671f0ceb381d62b0d5e86c`
- Latest successful full validation: GitHub Actions **Verify #1431 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` disables automatic Vercel deployments for this branch.
- User boundary remains: **no Preview generation, no Production changes/deployments, no merge** until explicitly changed.
- Latest observed Vercel deployment remains historical commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` / `dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre` (ERROR); current performance/CRM work produced no Preview.

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

The GCP instance is CI infrastructure only. It is not in the user request path and therefore does not by itself make China user access slower.

### Latest green validation

Verify **#1431** completed successfully for `72a9ffd3d368fdd11b671f0ceb381d62b0d5e86c` and executed:

- Checkout;
- system Python verification;
- Node 24 setup;
- `npm ci`;
- bundled snapshot refresh;
- **515 Python pipeline/contract tests — all PASS**;
- serverless entrypoint checks (`11/12` configured slots);
- verified snapshot / medical-channel / private-profile / AI-boundary / runtime checks;
- full prebuild;
- TypeScript `tsc --noEmit`;
- Vite production build;
- ranking summary.

Verify #1429 was a real Fast Verify failure after the private router core was moved: seven static contract tests still inspected `web/api/private.js`. They were corrected to inspect the actual unchanged core at `web/api/_privateCore.js`, without removing or weakening their assertions. Verify #1430 then passed Fast Verify, and #1431 passed the complete Full Verify.

This remains code/build validation only. It does not constitute current-HEAD Vercel runtime acceptance because Preview is intentionally disabled.

## China-access / runtime latency work

The current optimization principle is to reduce cross-border round trips and bytes before changing regions. Current Neon is on AWS `us-east-2` (Ohio). `vercel.json` does not force a Function region. Do not move only Vercel Functions to Asia while the database remains in Ohio; that can turn one user-side cross-border hop into repeated Function-to-database cross-region hops. Any future regional change should be based on measured China TTFB/P95 and preferably move the dynamic API and database together.

Validated performance work includes:

- `/today` customer-private profile reads reduced from four SQL queries to one bounded aggregate query;
- `/today` follow-up + recommendation feedback + `today_limit` reads reduced from three SQL queries to one query; the Today private-data path is roughly reduced from ~7 DB round trips to ~2;
- private and public schema bootstrap use schema-version fast paths; full DDL/migration runs only when the schema version changes and is serialized;
- public history materialization is side storage scheduled with Vercel `waitUntil()` on Vercel runtime, so it no longer blocks the main `/today` response; same-snapshot duplicate materialization is suppressed within a warm instance;
- detail page initial opportunity and follow-up reads are parallel rather than serial;
- public fact-version history on detail is on demand, not fetched on every detail open;
- confirmed follow-up mutations use a bounded one-shot server-confirmed response reuse path, avoiding immediate redundant GETs on Today/detail;
- Today runtime status and due reminders are auxiliary/non-blocking; the main Today data no longer waits for `/reminders`;
- login/register has a 10-second, one-shot, in-memory-only authenticated-user handoff so the same SPA navigation does not immediately repeat `/auth/me`; refresh/new tab/cross-tab flows remain server-authoritative;
- `viteSingleFile()` was removed, restoring normal hashed JS/CSS assets and Vercel `/assets/*` immutable caching;
- secondary routes are lazy-loaded; Login is lazy-loaded while Today remains eager;
- Runtime Trial / Static Snapshot / Mock service implementations are deferred and do not statically ride the real Pilot service path;
- demo reset dependencies are requested only on the non-API reset action; `localCustomerProfile` builds as its own deferred chunk;
- `aiDecisionApi` is no longer part of the authenticated Pilot Today initial bundle; real Pilot loads it only after explicit AI analysis;
- `OutreachDrawer` is no longer part of Today initial delivery; it loads only after the user explicitly opens the communication-draft action;
- NotFit/Remind remain eager inside Today intentionally to avoid over-fragmenting common CRM actions into too many small static requests;
- **Today light response is implemented:** normal authenticated `/api/today` no longer sends the full `opportunity_pool`; it still returns the configured Top-N Today cards plus `opportunity_pool_count` and the other Today metadata;
- **Opportunity Pool keeps the full response explicitly:** `/api/opportunity-pool/today` rewrites to the same existing `/api/private?route=today&include_pool=1` Function. No new Vercel Function or DB request is introduced;
- the real Pilot service keeps separate primary and full-pool delegates, so the short one-shot Today mutation reuse state cannot be mistaken for a complete Opportunity Pool response.

### Today light-response implementation boundary

The original business router was moved byte-for-byte from `web/api/private.js` into the internal module `web/api/_privateCore.js`. At the split point the internal file reuses the original Git blob exactly; the business SQL, authentication, follow-up, reminder, feedback and outcome rules were not hand-rewritten.

`web/api/private.js` is now a thin entry adapter. For default `GET route=today` it removes only `opportunity_pool` from the successful `TODAY_ACTIONS` payload. `include_pool=1`, PUT requests, all other private routes and error payloads pass through unchanged.

This first stage reduces response serialization/network bytes, which is especially relevant to a China client crossing borders. **It does not yet reduce the server-side work used to construct/personalize the full pool**: `_privateCore.js` still builds `decoratedPool` before the thin adapter projects the response. Therefore no CPU/DB latency reduction is claimed from this split yet, and no China TTFB/P95 improvement is claimed before a real permitted Preview measurement.

### Production build delivery result

Historical single-file build:

- `index.html`: 659.76 kB, gzip 192.66 kB.

Full Verify #1431 production build:

- `index.html`: **0.62 kB**, gzip **0.38 kB**;
- CSS: **41.30 kB**, gzip **8.09 kB**;
- main JS: **358.88 kB**, gzip **115.27 kB**;
- `aiDecisionApi`: **5.43 kB**, gzip **2.66 kB**;
- Login: **6.58 kB**, gzip **2.69 kB**;
- `localCustomerProfile`: **7.99 kB**, gzip **3.11 kB**;
- OutreachDrawer: **12.16 kB**, gzip **4.72 kB**;
- Opportunity Pool: **18.45 kB**, gzip **6.97 kB**;
- Followed: **20.95 kB**, gzip **7.37 kB**;
- Pilot Resources: **23.18 kB**, gzip **6.76 kB**;
- Opportunity Detail: **50.45 kB**, gzip **15.89 kB**;
- Radar: **57.59 kB**, gzip **17.29 kB**.

Progressive main-bundle result:

- #1402: `415.64 / gzip 132.15 kB`;
- #1413: `382.56 / gzip 122.48 kB`;
- #1418: `375.20 / gzip 119.58 kB`;
- #1423: `370.34 / gzip 118.27 kB`;
- #1426: `358.43 / gzip 115.16 kB`;
- #1431: **`358.88 / gzip 115.27 kB`** after adding the isolated full-pool delegate.

The light-response service wrapper costs only about 0.45 kB raw / 0.11 kB gzip in the main bundle relative to #1426. The Vite report still correctly notes that `localFollowupStore` cannot be isolated by the AppLayout dynamic import alone because it is also statically referenced from other lazy route/service modules.

## Next performance boundary

Further tiny Today chunk splitting remains intentionally paused. The next high-value backend step, if pursued without Preview, is to determine whether the private core can avoid constructing/personalizing full-pool-only response material for the default Today request while preserving ranking, recommendation-feedback summary, counts and all private-state boundaries. That would be a server-compute optimization, distinct from the now-validated response-byte split.

Do not claim runtime benefit until such a change is code-validated and later measured on an explicitly permitted Preview.

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

`web/api/_privateCore.js` enforces controlled WON/LOST transition review server-side before event/status mutation while preserving idempotency and same-terminal free-form note behavior.

## Remaining acceptance gates

While no-Preview remains active, continue only code/test/data-boundary/business-closure work without making Vercel runtime claims.

When the user explicitly allows Preview again:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively from China and record TTFB/P95, response sizes and user-perceived loading;
3. verify normal Today omits the full pool while Opportunity Pool receives all current opportunities from the same private Function;
4. run protected Pilot smoke: explicit CONTACTED first, optional next action second;
5. verify reminder acknowledgement preserves sales stage and clears only reminder state;
6. verify private WON/LOST/NOT_FIT review persistence/export and no public leakage;
7. verify real API rejects direct WON/LOST terminal writes without controlled review;
8. verify terminal reopen preserves history and current statistics;
9. verify collector Queue/daily-deep/intraday runtime behavior and snapshot freshness;
10. verify one real same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
11. inspect custom-domain/Production promotion separately before any Production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
