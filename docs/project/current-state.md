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
- Latest fully code-validated runtime/test HEAD: `b4b41579d70648167566175c307df0a1a49f79b7`
- Latest successful Verify: GitHub Actions **#1351 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` disables automatic Vercel deployments for this branch.
- User boundary remains: **no Preview generation, no Production changes/deployments, no merge** until explicitly changed.
- Latest observed Vercel deployment remains old commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` / `dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre` (ERROR); no GCP-CI/private-outcome commit produced a Preview.

## Executable validation state

### Active CI path: GCP self-hosted runner

Private GitHub-hosted runner attempts repeatedly failed before Checkout (`steps=[]`, no runner assignment). The same symptom occurred in another private repository while a temporary public runner probe succeeded. MedicalChannelAI therefore remains private and now uses:

- runner: `medicalchannelai-gcp-1`
- labels: `self-hosted`, `linux`, `x64`, `medicalchannelai-ci`
- VM: Ubuntu 25.10 / x86_64
- system Python: 3.13.7
- Node: 24.20.0
- Verify triggers: `pull_request` + `workflow_dispatch`
- duplicate branch-push Verify removed;
- npm Actions cache upload disabled; persistent VM local cache is used instead.

`actions/setup-python` was removed because Ubuntu 25.10 had no matching Python 3.12 toolcache build; project prebuild already supports system `python3`.

### Latest green validation

Verify **#1351** completed successfully for `b4b41579d70648167566175c307df0a1a49f79b7` and executed:

- Checkout;
- system Python verification;
- Node 24 setup;
- `npm ci`;
- bundled snapshot refresh;
- **475 Python pipeline/contract tests — all PASS**;
- serverless entrypoint checks;
- verified snapshot / medical-channel / private-profile / AI-boundary / runtime checks;
- full prebuild;
- TypeScript `tsc --noEmit`;
- Vite production build;
- ranking summary.

This is code/build validation only. It does **not** constitute current-HEAD Vercel runtime acceptance because Preview is intentionally disabled.

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

The current branch includes private result review without adding a database table or Vercel Function:

- `profile.js?route=outcome-summary` reads current-account `private_followups` / `private_followup_events` only;
- reports WON / LOST / NOT_FIT counts and decided win rate;
- >5000 terminal records fail closed;
- client rejects duplicate reason codes and inconsistent reason totals;
- WON / LOST UI require bounded private review factors and clearly label them current-user commercial judgments, not hospital/procurement facts;
- historical free-form/unrecognized records remain `历史未结构化` rather than guessed;
- NOT_FIT keeps structured reason;
- reopened outcomes leave current terminal statistics while old history is preserved;
- export/delete lifecycle includes outcome events;
- fewer than 5 decided outcomes do not generate a claimed business rule;
- private outcome statistics do not alter public facts/ranking.

### Server-side WON/LOST transition invariant — completed

`web/api/private.js` now enforces the controlled review server-side, not only in UI:

- entering WON requires an exact recognized `成交复盘（当前用户判断）：...` factor;
- entering LOST requires an exact recognized `未成交原因（当前用户判断）：...` factor;
- the current follow-up row is selected `FOR UPDATE` with its status before the guard runs;
- same-status WON→WON or LOST→LOST later free-form notes remain allowed;
- switching WON↔LOST requires a new controlled review matching the new outcome;
- invalid direct terminal transition returns `400 FOLLOWUP_OUTCOME_REVIEW_REQUIRED`;
- the guard runs before event insertion/status update, so transaction rollback prevents a partial terminal write;
- existing mutation-id idempotency short-circuits before the guard and remains intact.

New contract file: `web/pipeline/tests/test_private_outcome_transition_guard.py`.

Verify #1351 confirms all five new server-guard tests plus the entire 475-test suite, TypeScript and Vite build pass.

## Grounded AI boundary

The server owns verified public facts used for AI actions. Browser-provided procurement facts are not trusted. Customer-private context is account scoped and must not become public fact.

Current-HEAD real same-origin AI POST on Vercel is not re-accepted because branch Preview remains disabled.

## Remaining acceptance gates

While no-Preview remains active, continue code/test/data-boundary/business-closure work without making Vercel runtime claims.

When the user explicitly allows Preview again:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively;
3. run protected Pilot smoke: explicit CONTACTED first, optional next action second;
4. verify reminder acknowledgement preserves sales stage and clears only reminder state;
5. verify private WON/LOST/NOT_FIT review persistence/export and no public leakage;
6. verify real API rejects direct WON/LOST terminal writes without controlled review;
7. verify terminal reopen preserves history and current statistics;
8. verify collector Queue/daily-deep/intraday runtime behavior and snapshot freshness;
9. verify one real same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
10. inspect custom-domain/Production promotion separately before any Production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
