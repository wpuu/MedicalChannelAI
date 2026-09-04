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
- hospital relationships and product capabilities are used only after customer confirmation;
- customer-private outcomes may support private review, but must not be rewritten as public facts or automatically alter public opportunity ranking.

`production_ready=false`.

## Current source-control and deployment boundary

- Active branch: `chatgpt/opportunity-ranking-v2-final`
- Draft PR: `#6` — `v0.4.1: opportunity ranking v2 final`
- Latest fully code-validated runtime HEAD: `1ccc219e13fc215b1bea25dbfc0016b1d366a935`
- Current unvalidated runtime candidate HEAD: `bacdc0fa9e1b711acb901a262e81358aea22650b`
- Documentation-only commits may exist above the runtime candidate; they must not be confused with a newer runtime validation point.
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` explicitly disables automatic Vercel deployments for the active PR branch.
- The user explicitly requires **no Preview generation and no Production changes/deployments** until that boundary is changed again.
- Vercel was rechecked after the private outcome-review work. No deployment exists for the new result-review commits; the newest visible branch deployment still points to old commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` and is not current-HEAD validation.
- The reachable custom demo/production surfaces must not be treated as containing current branch changes.

Do not merge PR #6, enable the branch Preview, call Vercel deploy, or modify/promote Production without explicit product-owner approval.

## Executable validation state

### Last known green code validation

GitHub Actions `Verify MedicalChannelAI` run **#1281** completed successfully for runtime HEAD `1ccc219e13fc215b1bea25dbfc0016b1d366a935`.

That successful job includes:

- full prebuild verification;
- Python pipeline/contract regression suite;
- TypeScript `tsc --noEmit`;
- Vite production build;
- verified ranking summary.

This is the latest code point that may be called fully CI-validated.

### Current runtime candidate is not yet executable-validated

Runtime candidate `bacdc0fa9e1b711acb901a262e81358aea22650b` contains the newer private outcome-review / terminal-state work described below.

Observed GitHub Actions runs after the last green point — including **#1297, #1299, #1303, #1307 and #1327**, plus explicit reruns — failed before executing repository steps. The jobs showed `steps=[]` and no assigned runner (`runner_id=0` where exposed). Therefore:

- those failures are **not evidence that the code tests failed**;
- they are also **not evidence that the current runtime candidate passed**;
- no Checkout / Python / Node / TypeScript / Vite step actually ran in those attempts;
- the current runtime candidate remains **pending executable CI validation**.

Do not upgrade `bacdc0f…` to a validated head until a real Verify run executes the repository steps and succeeds.

Preview generation remains intentionally disabled, so even a future CI green result will not by itself prove Vercel runtime behavior.

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

Important implemented guarantees include:

1. same-priority incremental candidates verify newest official notices first;
2. any selected-detail verification failure blocks public snapshot publication for that source scan;
3. successful detail work may remain internally staged so retry does not re-hit already verified official pages;
4. unresolved failed detail URLs remain behind a source-scoped pending verification barrier and cannot leak through another source's later publish;
5. deep authoritative success clears stale incremental pending records/barriers;
6. first incremental execution reuses one discovery pass rather than fetching the same official index twice;
7. a bounded 48-hour carryover backlog prevents deferred URLs from disappearing forever when capped index windows move forward;
8. carryover receives only bounded detail capacity so fresh notices remain dominant;
9. ledger entries are individually retained/pruned instead of growing forever with a hot cache key;
10. `last_seen_at` means actual index discovery, not detail retry time;
11. actual Queue delivery time, not enqueue trigger time, drives real verification timestamps;
12. cross-China-business-day incremental source redeliveries are discarded before network fetch;
13. deep at-least-once duplicate messages are classified as completed/superseded/stale/unsafe instead of retrying forever after a legitimate lease release;
14. initial intraday-chain scheduling is recoverable through Queue redelivery if the first tick enqueue fails;
15. incremental source attempts are marked only after Queue acceptance;
16. tick cadence preserves the next nominal ten-minute slot under small Queue delivery jitter and skips backlog bursts after material delay;
17. deep and incremental mutation paths are serialized and deep remains authoritative reconciliation;
18. the legacy GitHub deep fallback is reduced to one automatic daily run plus manual dispatch.

No Preview/runtime claims should be made for this architecture until Preview execution is explicitly allowed again and the runtime path is exercised.

## User-facing business closure

The branch covers the main pilot loop:

**discover opportunity → inspect official evidence → personalize with confirmed resources → generate grounded outreach → contact → explicitly record contact → optionally arrange a concrete next action → work due-action queue → track terminal result → private outcome review**.

Established closure behavior:

- outreach drawer shows verified public contact information together with the grounded draft;
- phone dialing uses safe telephone normalization, including extension handling;
- public phone/email actions and copying outreach text do not automatically claim the customer was contacted;
- only the explicit `已联系，记入跟进` action writes `CONTACTED`;
- after contact is explicitly recorded, the drawer offers `先去我的跟进` or `安排下一步` rather than forcing navigation;
- arranging a next action preserves the current sales stage and stores private `remind_at + 下次行动`;
- reminders are independent from sales stage;
- every new UI-created reminder requires a concrete next action, with common presets to reduce input cost;
- due reminder acknowledgement clears the reminder only, not the underlying sales stage;
- `我的跟进` prioritizes due items, then future scheduled items, then other active/monitor/closed records;
- private structured notes are displayed semantically (`下次行动` / `未成交复盘（私有）`) while old generic reminder notes do not occupy the action view.

### Private terminal outcome review — current runtime candidate

The newer runtime candidate adds a private result-review layer without adding a database table or a new Vercel Function:

- outcome summary reuses the existing `profile.js` serverless function via `profile?route=outcome-summary`;
- summary reads only current-account `private_followups` / `private_followup_events` rows and never reads public opportunity facts to infer why a result happened;
- `WON / LOST / NOT_FIT` counts and decided win rate are available in `我的跟进` as a non-blocking private card;
- the summary fails closed instead of returning truncated statistics if the terminal-result index exceeds the bounded 5000-record limit;
- `LOST` requires a bounded private loss-reason selection and explicitly states that it is the user's commercial judgment, not a hospital/procurement public fact;
- `WON` now requires a bounded private win-review factor through an explicit confirmation modal; the selected factor is saved atomically with `WON` through the existing follow-up event/note path;
- historical WON/LOST records whose reason cannot be safely reconstructed are counted as `历史未结构化` rather than guessed;
- outcome parsing recognizes only fixed private prefixes / bounded labels and does not mine arbitrary free-form notes for supposed causes;
- `NOT_FIT` continues to use its existing structured reason field;
- terminal states `WON / LOST / NOT_FIT / ARCHIVED` are protected from casual dropdown overwrite; reopening requires an explicit `更正结果 / 重新打开` flow and a second confirmation, then records a new `REVIEWING` event while preserving old history;
- account export already includes follow-up event `reason`/notes, and account deletion cascades through the same private follow-up/event ownership chain;
- the result-review card treats fewer than **5 decided outcomes** as insufficient to infer a business pattern; larger samples still generate only an artificial-review prompt, never a causal claim;
- private outcome statistics do **not** write into public facts and do **not** automatically modify public opportunity ranking.

This private outcome-review implementation is currently **pending real CI execution** because GitHub Actions did not obtain a runner after `#1281`.

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

While the no-Preview boundary remains active:

1. obtain a real GitHub Actions runner and execute the full Verify workflow against the current runtime candidate or a descendant containing the same runtime code;
2. fix any actual test/type/build regression found by that real run;
3. only after a real success may the latest fully code-validated runtime HEAD advance beyond `1ccc219…`;
4. continue code/test/data-boundary/business-closure work without making Vercel runtime claims.

When the user explicitly allows Preview again, the runtime acceptance should include:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively;
3. run the protected Pilot smoke against Preview, proving explicit CONTACTED first and optional next-action reminder second;
4. verify due-reminder acknowledgement preserves sales stage and removes the item from the due-action queue;
5. verify private WON/LOST/NOT_FIT outcome review persists across session/export and never leaks into public facts;
6. verify terminal-result reopen preserves history while removing the item from current terminal statistics;
7. verify collector runtime/queue/deep-to-incremental behavior and snapshot freshness on real Vercel runtime state;
8. verify one real same-origin grounded AI POST only if Preview runtime AI configuration is intentionally supplied;
9. inspect custom-domain/Production promotion path separately before any production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
