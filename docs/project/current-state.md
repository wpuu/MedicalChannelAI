# MedicalChannelAI current state

Updated: 2026-08-31

## Product state

MedicalChannelAI is a medical-channel commercial intelligence / sales-agent pilot for medical devices, IVD and consumables. The first pilot region is Tianjin.

The fixed product rule is **evidence first**:

- procurement facts must come from traceable official-source evidence;
- unsupported critical facts stay empty instead of being guessed;
- models may classify, match, explain and recommend actions, but they may not invent hospitals, projects, budgets, dates, contacts, suppliers, brands, model numbers, customer relationships or win probability;
- customer-owned resources are explicitly separated from public procurement facts.

`production_ready=false`.

## User-facing deployment boundary

- Custom demo URL: `https://medicalai.qd.je/` is reachable.
- `web/` is the current H5 product implementation.
- The product flow is **zero-config first**: users can see verified public opportunities before entering customer resources.
- Today Actions exposes at most **5 priority cards** while retaining the total actionable-opportunity count separately.
- `我的资源` is optional personalization. Product capabilities, hospital relationships and cooperation policies are stored locally in the current trial and are never presented as hospital/public facts.
- `我的跟进` and local reminder lifecycle are usable in the verified trial.
- The custom domain being reachable does **not** mean the newest branch commits are already promoted there. Production/custom-domain promotion remains separate from branch/Preview validation.

## Source and evidence pipeline on the active branch

Active branch: `chatgpt/m1-evidence-pipeline-v1`

Draft PR: `#3` — `M1: evidence-first Tianjin pipeline and grounded AI trial`

Main base remains `6221925212bbb663793d7e0305e2b98f440c0513`. Do not treat the active branch as merged production state.

Implemented on the branch:

1. canonical evidence/fact validation with fail-closed critical facts;
2. CCGP discovery-only search adapter;
3. verified CCGP detail adapters for public tender and competitive consultation notices;
4. correction / termination event reconciliation;
5. Tianjin Medical University General Hospital market-research discovery + verified detail source;
6. deterministic Today Actions public snapshot generation with Top5 output;
7. pipeline-generated `web/public/data/today-actions.public.json` consumed by the verified trial;
8. runtime deadline protection so stale static snapshots cannot keep expired projects actionable;
9. `LATE_WINDOW` handling when registration/file acquisition has closed but bid/response deadline is still future;
10. optional customer-resource personalization without changing the public fact base;
11. grounded on-demand AI analysis through same-origin `/api/ai/analyze`;
12. local follow-up persistence and reminders;
13. dual-source Tianjin refresh orchestration for CCGP + hospital market research;
14. optional externally refreshed verified-snapshot loading, with fail-closed remote-source behavior.

## Grounded AI boundary

The browser sends an opportunity ID and, only when present, user-entered customer context.

The server function:

- retrieves verified public facts by opportunity ID from the configured verified snapshot source;
- uses the bundled snapshot by default and can optionally use an HTTPS remote snapshot;
- does not silently fall back to the bundled snapshot if a configured remote snapshot fails;
- rejects browser-supplied fake procurement facts;
- sanitizes customer context and labels it as self-reported/customer-owned context;
- keeps provider/model/API key details server-side;
- enforces same-origin access and a warm-instance request limit;
- independently recalculates `OPEN`, `LATE_WINDOW` or `CLOSED` from official deadlines at request time;
- refuses AI analysis after the actionable window is closed;
- invalidates AI caches when customer context or the runtime window changes.

Preview POST execution with a real configured Agnes key is still unverified. Do not claim AI runtime success until a real POST returns a grounded result.

## Executable validation evidence

Latest fully verified Vercel Preview commit:

`00bc0d6bfc0ecffb106cc8b0c40b34f3202c26d6`

Deployment:

`dpl_7wzRnZfgvi29sHn34poykwVkAyTf`

That Vercel build log proves all of the following for that commit:

- Pipeline tests: **60 / 60 PASS**;
- AI boundary checks: **PASS**;
- prebuild verification: **PASS**;
- `tsc --noEmit`: **PASS**;
- Vite production build: **PASS**;
- one Node.js server function was packaged in the Preview.

This verified point already includes runtime deadline/late-window hardening, AI-window enforcement, dual-source automatic-refresh architecture and the Pipeline Top5 implementation.

Current PR HEAD is newer than that verified point. At the time of this update it includes additional dedicated Top5 regression coverage plus dynamic verified-snapshot fail-closed checks. Those newest commits are **implemented but still require a newer successful Preview** before being called executable-validated.

GitHub Actions runner execution remains unverified. Repository Actions and scheduled refresh must not be represented as PASS until an actual workflow run receives a runner and completes successfully.

## Automatic refresh architecture

Implemented but **not currently running in production**:

- CCGP query plan: `pipeline/data/tianjin_query_plan.json`;
- durable CCGP state: `pipeline/data/tianjin_live_ccgp_records.json`;
- durable hospital-source state: `pipeline/data/tianjin_live_tjmugh_records.json`;
- CCGP plan orchestrator: `pipeline/scripts/sync_tianjin_plan.py`;
- hospital-source sync: `pipeline/scripts/sync_tjmugh_market_research.py`;
- publisher: `pipeline/scripts/publish_web_snapshot.py`;
- workflow: `.github/workflows/tianjin-medical-refresh.yml`.

The refresh layer:

- locks the Pilot to Tianjin;
- uses multiple medical-channel CCGP keywords;
- deduplicates official detail URLs before detail verification;
- retains minimum request delays and performs no rate-limit bypass;
- runs the old-project correction/termination watch only once after all CCGP keywords;
- blocks CCGP publication if all discovery queries fail;
- blocks CCGP publication when candidates are discovered but every selected detail fails verification;
- blocks the hospital-source refresh if its official index fails;
- blocks the hospital-source refresh when candidates are selected but every selected detail fails verification;
- publishes only after both source refresh stages and the regression suite succeed.

The workflow is scheduled in code for 08:20 China time daily and 16:20 China time on weekdays. Scheduled GitHub workflows only operate from the default branch, and current runner availability remains unverified, so this remains **IMPLEMENTED_NOT_RUNNING** until after merge and a successful real run.

The default frontend deployment still uses the bundled snapshot. Optional external snapshot support is an optimization path, not proof that an external public data store has been configured.

## Current blockers / next gates

1. Obtain a successful Vercel Preview for the current PR HEAD, including the newest Top5 and verified-snapshot checks.
2. Verify Preview Today / Followups / Resources behavior with an executable browser path.
3. Verify a real same-origin POST to `/api/ai/analyze` with server-side Agnes runtime configuration, without exposing the key/model to the browser.
4. Execute the Tianjin refresh workflow successfully on a real runner and inspect both source sync reports before calling automatic refresh active.
5. Only after those gates, request product-owner approval before merging PR #3 or promoting to the custom domain.

Do not merge or mark `production_ready=true` merely because the custom domain opens.
