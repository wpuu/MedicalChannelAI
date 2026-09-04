# MedicalChannelAI current state

Updated: 2026-09-04

## Product state

MedicalChannelAI is a Tianjin-first medical-channel commercial intelligence / sales-assistant pilot for medical devices, IVD and consumables.

Fixed rules:

- **evidence first**: public medical/procurement facts must come from traceable official evidence;
- unsupported critical facts stay empty instead of being guessed;
- models may classify, match, explain and recommend actions, but may not invent hospitals, projects, budgets, dates, contacts, suppliers, brands, customer relationships or win probability;
- public intelligence and customer-private resources are separate layers;
- target hospitals are watch/focus objects only and never add relationship points;
- hospital relationships and product capabilities are used only after customer confirmation;
- customer-private outcomes may support private review, but must not be rewritten as public facts or automatically alter public opportunity ranking.

`production_ready=false`.

## Source-control and deployment boundary

- Active branch: `chatgpt/opportunity-ranking-v2-final`
- Draft PR: `#6` — `v0.4.1: opportunity ranking v2 final`
- Runtime implementation baseline containing the current private outcome-review behavior: `315ce5fd97aab1994cf22c7b22a6fdd30a213713`
- Latest fully code-validated branch HEAD: `e68cff21c2f2b55f70efe4817af685f1c8b68ffc`
- Latest successful Verify: GitHub Actions **#1345 SUCCESS**
- PR base: `main` at `5cf221ad1b96520eecb444051ae902087bb10484`
- PR remains open, Draft and unmerged.
- `web/vercel.json` explicitly disables automatic Vercel deployments for the active PR branch.
- The user explicitly requires **no Preview generation and no Production changes/deployments** until that boundary is changed again.
- Vercel was rechecked after GCP CI migration. The newest visible deployment still points to old commit `ddd965f132343b0885f91e30e13a6b8fc2157afa` (`dpl_nWSXz4iwKcZZQsfd3Aem4XfXVtre`, ERROR). No GCP-CI/private-outcome commits produced a Preview.

Do not merge PR #6, enable branch Preview, call Vercel deploy, or modify/promote Production without explicit product-owner approval.

## Executable validation state

### GCP self-hosted runner is now the active private-repository CI path

Private GitHub-hosted runner attempts after #1281 repeatedly failed before repository execution (`steps=[]`, no runner assignment). The same symptom was observed in another private repository, while a temporary public repository runner probe succeeded on 2026-09-04. Rather than making MedicalChannelAI public, the repository now uses a repository-scoped GCP self-hosted runner:

- runner: `medicalchannelai-gcp-1`
- labels: `self-hosted`, `linux`, `x64`, `medicalchannelai-ci`
- VM OS: Ubuntu 25.10 / x86_64
- system Python used by CI: Python 3.13.7
- Node: 24.20.0
- Verify triggers remain `pull_request` + `workflow_dispatch`; the earlier duplicate branch-push Verify was removed.
- GitHub Actions npm cache upload is disabled; the persistent VM can reuse its own local npm cache.

`actions/setup-python` was removed because it had no Python 3.12 binary for Ubuntu 25.10. The project prebuild already supports `python3` as its first Python runtime candidate.

### Latest real green validation

GitHub Actions `Verify MedicalChannelAI` run **#1345** completed successfully for branch HEAD `e68cff21c2f2b55f70efe4817af685f1c8b68ffc` on the GCP self-hosted runner.

The successful job executed:

- Checkout;
- system Python verification;
- Node 24 setup;
- `npm ci`;
- bundled snapshot refresh;
- **470 Python pipeline/contract tests**;
- full prebuild verification;
- TypeScript `tsc --noEmit`;
- Vite production build;
- verified ranking summary.

The first real GCP run exposed two non-business-code problems and both were corrected before #1345:

1. `actions/setup-python@v5` could not supply Python 3.12 for Ubuntu 25.10, so CI now uses the VM's system `python3`;
2. one reminder contract test still expected a pre-refactor source-code expression even though behavior was correct; the test was updated to assert the equivalent `terminal` + `reminderAllowed` contract.

Current code may therefore be called fully CI-validated at `e68cff2…`. This is build/test validation only; it does **not** constitute current-HEAD Vercel runtime acceptance because Preview remains intentionally disabled.

## Public intelligence architecture

Public regional intelligence is shared by source/region/opportunity version rather than recomputed per customer. Current architecture includes:

- official-source discovery and detail verification;
- canonical VERIFIED fact state;
- correction / termination reconciliation where supported;
- public opportunity ranking with no private relationship/product points;
- shared public snapshot and version/history boundaries;
- customer-private personalization layered after public facts;
- public and private persistence separated by scope.

Current Tianjin source families include CCGP and multiple hospital/institution feeds, including Tianjin Medical University General Hospital, Tianjin Hospital, TEDA Hospital and Tianjin First Central Hospital. Source failures remain fail-closed.

## Incremental collection state

The branch contains the Vercel-native daily-deep + bounded intraday incremental architecture. Important implemented guarantees include:

1. newest same-priority official notices are verified first;
2. selected-detail verification failure blocks partial public snapshot publication;
3. successful partial detail work can remain source-scoped staged for retry;
4. unresolved failed URLs remain behind a source-scoped verification barrier;
5. authoritative deep success clears stale incremental pending/barrier state;
6. the first incremental execution reuses one discovery pass;
7. bounded 48-hour carryover prevents deferred URLs from disappearing forever while preserving fresh-item priority;
8. ledger entries are individually retained/pruned and `last_seen_at` means actual index discovery;
9. actual Queue delivery time drives verification timestamps;
10. cross-China-business-day stale redeliveries are discarded before network fetch;
11. deep at-least-once duplicates are classified instead of retrying forever;
12. first intraday-chain scheduling is recoverable;
13. source attempts are marked only after Queue acceptance;
14. tick cadence preserves the next nominal slot and avoids backlog bursts;
15. deep and incremental mutation paths are serialized;
16. legacy GitHub deep fallback remains once daily plus manual dispatch.

These are code/contract guarantees, not current Production-runtime acceptance while Preview is disabled.

## User-facing business closure

The current pilot loop is:

**discover opportunity → inspect official evidence → personalize with confirmed resources → generate grounded outreach → contact → explicitly record contact → optionally arrange a concrete next action → work due-action queue → track terminal result → private outcome review**.

Established behavior:

- copying outreach, tapping phone or tapping email does not automatically write `CONTACTED`;
- only explicit `已联系，记入跟进` writes CONTACTED;
- after contact, the user may go to `我的跟进` or explicitly arrange a next action;
- reminders are independent from sales stage and new UI reminders require a concrete next action;
- reminder acknowledgement clears the reminder only;
- `我的跟进` prioritizes due → scheduled → other active → monitor → closed items;
- `WON`, `LOST`, `NOT_FIT`, `ARCHIVED` are protected from casual dropdown overwrite and require explicit reopen confirmation;
- `ARCHIVED` is a workflow terminal state but is not counted as a WON/LOST/NOT_FIT outcome.

### Private outcome review

The branch contains a private result-review layer without a new database table or new Vercel Function:

- outcome summary reuses `profile.js?route=outcome-summary`;
- summary reads current-account `private_followups` / `private_followup_events` only;
- it reports WON / LOST / NOT_FIT counts and decided win rate;
- over 5000 terminal records fails closed rather than returning truncated statistics;
- client parsing rejects duplicate reason codes and inconsistent reason totals;
- WON and LOST UI flows require bounded private review factors and explicitly state these are current-user commercial judgments, not hospital/procurement public facts;
- historical free-form/unrecognized records remain `历史未结构化` rather than being guessed;
- NOT_FIT uses its existing structured reason field;
- reopened outcomes stop counting as current terminal outcomes because the summary reads current follow-up state;
- account export includes follow-up event reason/note and account deletion cascades through the private event chain;
- fewer than 5 decided outcomes are treated as too small a sample to infer a business rule;
- private outcome statistics do not write public facts and do not automatically alter public opportunity ranking.

### Known incomplete server invariant

`web/api/private.js` validates NOT_FIT reason server-side, but WON/LOST controlled-review requirements are still primarily UI-enforced. An authenticated caller can currently craft a direct follow-up POST that transitions into WON or LOST without the controlled private review note.

This remains an explicit incomplete item. The intended hardening is:

- require a recognized WON/LOST private review when transitioning into or switching to that terminal outcome;
- allow later same-status free-form notes;
- require a new matching review when switching WON ↔ LOST;
- preserve mutation idempotency, reminder clearing, history and historical public snapshot behavior.

CI is now available to validate this change safely; the next core-code gate is to implement this invariant and rerun the full GCP Verify.

## Grounded AI boundary

The server owns verified public facts used for AI actions. Browser-provided procurement facts are not trusted. Customer-private context is account scoped, server-side sanitized and does not become public fact.

Current-HEAD real same-origin AI POST on Vercel is not re-accepted because current branch Preview is intentionally disabled. Do not infer runtime success from CI compilation.

## Remaining acceptance gates

While the no-Preview boundary remains active:

1. harden server-side WON/LOST transition-review validation in `web/api/private.js`;
2. run the full GCP self-hosted Verify and keep the branch green;
3. continue code/test/data-boundary/business-closure work without making Vercel runtime claims.

When the user explicitly allows Preview again:

1. deploy the exact then-current PR HEAD to Preview only;
2. verify Today / Opportunity Pool / detail / Resources / Followups interactively;
3. run protected Pilot smoke: explicit CONTACTED first, optional next action second;
4. verify reminder acknowledgement preserves sales stage and clears only reminder state;
5. verify private WON/LOST/NOT_FIT outcome review persists and never leaks into public facts;
6. verify terminal reopen preserves history and updates current outcome statistics correctly;
7. verify collector Queue/daily-deep/intraday runtime behavior and snapshot freshness;
8. verify one real same-origin grounded AI POST only if Preview AI configuration is intentionally supplied;
9. inspect custom-domain/Production promotion separately before any production action.

PR #6 must remain Draft until those gates and product-owner acceptance are complete.
