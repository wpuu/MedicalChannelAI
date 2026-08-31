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
- The current product flow is **zero-config first**: users can see verified public opportunities before entering customer resources.
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
5. official Tianjin Medical University General Hospital market-research source adapter;
6. deterministic Today Actions public snapshot generation;
7. pipeline-generated `web/public/data/today-actions.public.json` consumed by the verified trial;
8. runtime deadline protection in the browser so stale static snapshots cannot keep expired projects actionable;
9. `LATE_WINDOW` handling when registration/file acquisition has closed but bid/response deadline is still future;
10. optional customer-resource personalization without changing the public fact base;
11. grounded on-demand AI analysis through same-origin `/api/ai/analyze`;
12. local follow-up persistence and reminders;
13. guarded Tianjin plan-level refresh orchestration and a scheduled-refresh workflow definition.

## Grounded AI boundary

The browser sends an opportunity ID and, only when present, user-entered customer context.

The server function:

- retrieves the verified public facts from its bundled verified snapshot by opportunity ID;
- rejects browser-supplied fake procurement facts;
- sanitizes customer context and labels it as self-reported/customer-owned context;
- keeps provider/model/API key details server-side;
- enforces same-origin access and a warm-instance request limit;
- independently recalculates `OPEN`, `LATE_WINDOW` or `CLOSED` from official deadlines at request time;
- refuses AI analysis after the actionable window is closed;
- invalidates AI caches when customer context or the runtime window changes.

Preview POST execution with a real configured Agnes key is still unverified. Do not claim AI runtime success until a real POST returns a grounded result.

## Executable validation evidence

Last fully verified Vercel Preview commit:

`49f7623b4f1ac11dc042ae4165b3b5d666bfe580`

Deployment:

`dpl_7Bebs6XXLYmDL2Tb8JLpohkHkLft`

That Vercel build log proves all of the following for that commit:

- Pipeline tests: **34 / 34 PASS**;
- AI boundary checks: **PASS**;
- prebuild verification: **PASS**;
- `tsc --noEmit`: **PASS**;
- Vite production build: **PASS**;
- one Node.js server function was packaged in the Preview.

Commits after `49f7623...` add runtime-deadline/AI-window hardening, late-window UI and the automatic-refresh architecture. Those newer commits are **implemented but not yet executable-validated** because Vercel Hobby build-rate-limit is blocking newer Preview builds.

GitHub Actions has also historically failed before runner assignment. Repository Actions must not be represented as PASS until an actual workflow run receives a runner and completes successfully.

## Automatic refresh architecture

Implemented but **not currently running in production**:

- query plan: `pipeline/data/tianjin_query_plan.json`;
- durable CCGP state: `pipeline/data/tianjin_live_ccgp_records.json`;
- plan orchestrator: `pipeline/scripts/sync_tianjin_plan.py`;
- publisher: `pipeline/scripts/publish_web_snapshot.py`;
- workflow: `.github/workflows/tianjin-medical-refresh.yml`.

The orchestrator:

- locks the Pilot to Tianjin;
- uses multiple medical-channel keywords;
- deduplicates official detail URLs before detail verification;
- retains a minimum request delay and performs no rate-limit bypass;
- runs the old-project correction/termination watch only once after all keywords;
- blocks publication if all discovery queries fail;
- also blocks publication when candidates are discovered but every selected detail fails verification.

The workflow is scheduled in code for 08:20 China time daily and 16:20 China time on weekdays. Scheduled GitHub workflows only operate from the default branch, and current runner availability remains unverified, so this must be described as **IMPLEMENTED_NOT_RUNNING** until after merge and a successful real run.

## Current blockers / next gates

1. Obtain a newest-branch Vercel Preview that is not rejected by the Hobby build-rate-limit.
2. Confirm the expanded Pipeline tests, AI boundary checks, TypeScript check and Vite build all pass on that newest commit.
3. Verify Preview routes/UI for Today, My Followups and My Resources.
4. Verify a real same-origin POST to `/api/ai/analyze` with server-side Agnes runtime configuration, without exposing the key/model to the browser.
5. Execute the Tianjin refresh workflow successfully on a real runner and inspect its sync report before calling automatic refresh active.
6. Only after those gates, request product-owner approval before merging PR #3 or promoting to the custom domain.

Do not merge or mark `production_ready=true` merely because the custom domain opens.
