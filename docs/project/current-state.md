# MedicalChannelAI current state

Updated: 2026-09-04

## Product state

MedicalChannelAI is a Tianjin-first medical-channel commercial intelligence / sales-assistant pilot for medical devices, IVD and consumables.

Fixed rules:

- **evidence first**: public medical/procurement facts must come from traceable official evidence;
- unsupported critical facts stay empty instead of being guessed;
- models may classify, match, explain and recommend actions, but may not invent hospitals, projects, budgets, dates, contacts, suppliers, brands, customer relationships or win probability;
- public intelligence and customer-private resources are separate layers;
- target hospitals mean customer watch/focus only and never add relationship points;
- hospital relationships and product capabilities are used only after customer confirmation.

`production_ready=false`.

## Current source-control and deployment boundary

- Active branch: `chatgpt/opportunity-ranking-v2-final`
- Draft PR: `#6` — `v0.4.1: opportunity ranking v2 final`
- Latest fully code-validated HEAD: `59248d06a2bb6f4153a5d45575beb51a2593bacd`
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR is open, Draft, unmerged and mergeable.
- `web/vercel.json` explicitly disables automatic Vercel deployments for the active PR branch.
- The user explicitly requires **no Preview generation and no Production changes/deployments** until that boundary is changed again.
- Vercel was rechecked after the CRM/reminder work. No new deployment exists for this branch; the newest Vercel deployment still points to old commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` and is not current-HEAD validation.
- The reachable custom demo/production surfaces must not be treated as containing current branch changes.

Do not merge PR #6, enable the branch Preview, call Vercel deploy, or modify/promote Production without explicit product-owner approval.

## Current executable validation evidence

GitHub Actions `Verify MedicalChannelAI` run **#1259** completed successfully for HEAD `59248d06a2bb6f4153a5d45575beb51a2593bacd`.

The successful job includes:

- full prebuild verification;
- Python pipeline/contract regression suite;
- TypeScript `tsc --noEmit`;
- Vite production build;
- verified ranking summary.

This proves the latest code validation point compiles and passes repository CI. It does **not** prove current-HEAD Vercel runtime behavior, because Preview generation is intentionally disabled.

Historical Vercel Preview evidence from older commits remains useful only as historical runtime evidence and must not be represented as current-HEAD acceptance.

## Public intelligence architecture

Public regional intelligence is shared by source/region/opportunity version rather than recomputed per customer. Current architecture includes:

- official-source discovery and detail verification;
- canonical VERIFIED fact state;
- correction / termination reconciliation where supported;
- public opportunity ranking with no private relationship/product points;
- shared public snapshot and version/history boundaries;
- customer-private personalization layered after public facts;
- public and private persistence separated by scope.

Current Tianjin official-source families include CCGP and multiple hospital/institution feeds, including Tianjin Medical University General Hospital, Tianjin Hospital, TEDA Hospital and Tianjin First Central Hospital feeds. Source failures remain fail-closed.

## Incremental collection state

The active branch contains the Vercel-native daily-deep + bounded intraday incremental architecture, but it is **not accepted as running Production infrastructure** while current-HEAD runtime Preview acceptance is intentionally deferred.

Important implemented guarantees:

1. same-priority incremental candidates verify newest official notices first;
2. any selected-detail verification failure blocks public snapshot publication for that source scan;
3. successful detail work may remain internally staged so retry does not re-hit already verified official pages;
4. a bounded 48-hour carryover backlog prevents deferred URLs from disappearing forever when capped index windows move forward;
5. carryover receives only bounded detail capacity so fresh notices remain dominant;
6. ledger entries are individually retained/pruned instead of growing forever with a hot cache key;
7. `last_seen_at` means actual index discovery, not detail retry time;
8. recent canonical deep verification may reconcile incremental ledger only when metadata/fingerprint and time ordering are safe;
9. stale canonical verification cannot erase newer FAILED/UNVERIFIED or changed-index state;
10. deep and incremental mutation paths are serialized and deep remains authoritative reconciliation;
11. the legacy GitHub deep fallback is reduced to one automatic daily run plus manual dispatch.

No Preview/runtime claims should be made for this architecture until Preview execution is explicitly allowed again and the runtime path is exercised.

## User-facing business closure

The current branch now covers the main pilot loop:

**discover opportunity → inspect official evidence → personalize with confirmed resources → generate grounded outreach → contact → record follow-up → schedule next action/reminder → track result → record private loss reason**.

Recent closure work:

- outreach drawer shows verified public contact information together with the grounded draft;
- phone dialing uses the existing safe telephone normalization, including extension handling;
- public phone/email actions do not automatically claim the customer was contacted;
- copying outreach text does not mutate CRM state;
- only the explicit `已联系，记入跟进` action writes `CONTACTED`;
- after explicit confirmation, the user is taken to `我的跟进`;
- reminders are independent from sales stage: e.g. `CONTACTED + future reminder` remains `CONTACTED`;
- `MONITOR` remains a normal `持续观察` sales stage rather than being the only way to have a reminder;
- non-terminal stages may preserve reminders;
- terminal results `WON / LOST / NOT_FIT / ARCHIVED` clear/reject future reminders and do not offer a new-reminder action;
- due reminder acknowledgement clears the reminder only, not the underlying sales stage;
- reminder creation can optionally capture a private `下一步行动`, and due-reminder UI surfaces it directly as `下一步：…`;
- `LOST` now requires a private review reason selection instead of recording only an empty `未成交` state;
- loss-review copy explicitly states that the reason is the current user's private commercial judgment, not a hospital/procurement public fact;
- the existing follow-up event/note path is reused, so these CRM improvements require no database schema migration;
- `NotFitModal` persistence copy now reflects actual API-mode server persistence rather than incorrectly claiming local-only storage.

The reminder-stage migration requires no database schema migration because `remind_at` already exists independently on private follow-up state.

## Grounded AI boundary

The server owns verified public facts used for AI actions. Browser-provided procurement facts are not trusted. Customer-private context is account scoped, server-side sanitized and does not become public fact.

The server/runtime guards include:

- verified opportunity lookup;
- runtime deadline/actionability checks;
- stale/invalid snapshot automation guards;
- provider/model/key details kept server-side;
- output grounding checks;
- no inference of private relationship from public contacts or target hospitals.

Current-HEAD real same-origin AI POST on a Vercel runtime is **not re-accepted**, because current branch Preview is intentionally disabled. Do not infer runtime success from CI compilation.

## Remaining acceptance gates

While the no-Preview boundary remains active, continue code/test/data-boundary/business-closure work only.

When the user explicitly allows Preview again, the next runtime acceptance should include:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively;
3. run the protected Pilot smoke against the Preview, updated to prove a non-MONITOR stage such as `CONTACTED` can retain a reminder;
4. verify due-reminder acknowledgement preserves the sales stage and surfaces the saved next action;
5. verify private loss-review data persists across session/export without leaking into public facts;
6. verify collector runtime/queue/deep-to-incremental behavior and snapshot freshness on real Vercel runtime state;
7. verify a real same-origin grounded AI POST only if Preview runtime AI configuration is intentionally supplied;
8. inspect custom-domain/Production promotion path separately before any production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
