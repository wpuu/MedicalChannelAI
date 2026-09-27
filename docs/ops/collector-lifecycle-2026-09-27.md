# Vercel collector lifecycle: leases, recovery, budgets, read path

Date: 2026-09-27. Scope: `web/collector_runtime.py`, `web/collector_queue.py`,
`web/collector_namespace.py`, `web/api/collector-run.py`,
`web/api/_verifiedSnapshot.js`, `web/api/_publicIntelligenceDb.js`,
`web/src/services/runtimeStatusApi.ts`.

## Why

Behavioral reproduction against the previous code showed four coupled defects:

1. A stage killed by the platform at `maxDuration` (300 s) stayed `RUNNING`
   forever. `_activate_cycle` treated any `RUNNING` marker as a live cycle, so
   every later daily cron answered `409 COLLECTOR_CYCLE_ALREADY_RUNNING`.
2. `started_at` was written from the **cycle clock** (`cycle_as_of`), not the
   wall clock, so every "is it stale yet" computation was wrong by however long
   the cycle had been running.
3. Same-day recovery used hard-coded cycle ids (`recovery-v3`, `recovery-v6`).
   The queue rejects a reused idempotency key for 24 h, and the lease was
   written **before** the send, so a rejected send leaked a lease.
4. Five hand-written bypass flags (`regional_stale_migration_replay`,
   `regional_timeout_split_replay`, `publish_cache_migration_retry`,
   `tjfch_policy_recovery_retry`, `regional_cache_replay`) each patched one past
   incident and made retry accounting unreadable.

On the serving side, `loadVerifiedSnapshot()` pulled the full ~1.5 MB payload
from Postgres on **every** request, and the browser status validator did not
know the `DATABASE` source mode, which paused AI automation for all users while
the snapshot was fresh.

## Semantics now

### Stage lease (wall clock)

- Every `RUNNING` stage entry carries `started_at` and `lease_expires_at`
  (`started_at + STAGE_LEASE_SECONDS`). Both come from `_now_utc()`, never from
  the cycle clock. `run_stage(stage, now=<cycle clock>, wall_now=<real clock>)`.
- `STAGE_LEASE_SECONDS = QUEUE_FUNCTION_MAX_DURATION_SECONDS (300) + 15 s`
  skew grace. The 300 must equal `functions["api/collector-queue.py"].maxDuration`
  in `web/vercel.json`; a test enforces it. Change both together.
- A new delivery that finds a `RUNNING` stage with an **unexpired** lease gets
  `409 COLLECTOR_STAGE_LEASE_HELD:<stage>:<expires_at>`. The queue consumer
  waits in-process when the lease has ≤ 45 s left, otherwise it raises so the
  queue retries after `retryAfterSeconds`.
- A `RUNNING` stage with an **expired** lease is recorded as
  `FAILED / COLLECTOR_STAGE_TIMEOUT` and normal retry accounting applies
  (`MAX_STAGE_ATTEMPTS_PER_DAY = 2`).
- `started_at` doubles as the lease fencing token: a stage outcome is written
  into the **latest** collector state (MCAI-GCP-RETIRE-024) and only if the
  stage record still carries this worker's `started_at`; otherwise the write is
  rejected with `COLLECTOR_STAGE_LEASE_LOST:<stage>` and the delivery is
  acknowledged, because the newer owner drives the chain.
- A `COMPLETED` stage whose canonical Runtime Cache output vanished
  (`_stage_output_keys`) is re-run with a fresh attempt budget
  (`replay_reason = COLLECTOR_STAGE_OUTPUT_MISSING:<key>`), instead of failing
  publish with `COLLECTOR_CANONICAL_STATE_INCOMPLETE`.

### Cycle start (`/api/collector-run`)

- A new cycle is blocked **only** by a stage whose lease is still live
  (`cycle_has_live_running_stage`). A ghost `RUNNING` marker or yesterday's state
  never blocks the daily cron.
- First trigger of a Shanghai date → `prod:{date}`. A later same-day trigger
  while today's publish is not `COMPLETED` → `prod:{date}:recovery-{n}` with
  `n = recovery_attempts + 1`, persisted in collector state **before** the queue
  send, capped by `MAX_RECOVERY_CYCLES_PER_DAY = 3` (`409 COLLECTOR_RECOVERY_LIMIT`).
  Recovery resets `attempt_count` of every non-`COMPLETED` stage to 0 and keeps a
  compact `previous_attempts` history.
- Publish already `COMPLETED` today → `409 COLLECTOR_CYCLE_ALREADY_COMPLETED_TODAY`.
- Send raised `DuplicateIdempotencyKeyError` → `409 COLLECTOR_CYCLE_ALREADY_QUEUED`
  (the lease belongs to the in-flight cycle). Any other send failure deletes the
  lease we just wrote and returns 503, so the next trigger is not locked out.

### Time budget inside a stage

- `STAGE_BUDGET_SECONDS = 240` of source I/O per worker invocation, checked
  cooperatively. Politeness sleeps go through `_sleep()` and never exceed the
  remaining budget.
- Budget exhausted **during detail verification** → the records verified so far
  are committed and the stage `COMPLETED` with `deferred_candidate_count > 0`
  (the next cycle observes the rest). Exhausted before any detail →
  `FAILED COLLECTOR_STAGE_BUDGET_EXHAUSTED:<stage>:detail`.
- Budget exhausted **during discovery** →
  `FAILED COLLECTOR_STAGE_BUDGET_EXHAUSTED:<stage>:<phase>`.
- Per-request socket timeout inside the runtime is
  `SOURCE_REQUEST_TIMEOUT_SECONDS = 20` (search + detail). The GitHub-runner
  sync scripts keep their longer defaults.

### Publish

- Regression gate before the durable publish: baseline = `opportunity_pool_count`
  served by `/api/status` (fallback: bundled `today-actions.public.json`). A new
  pool smaller than `COLLECTOR_PUBLISH_MIN_POOL_RATIO` (default 0.7) × baseline
  fails the stage with `PUBLISH_REGRESSION_POOL_SHRUNK:<new><<min>`. Set the env
  var to `0` to bypass deliberately. The publish result records
  `regression_gate.contributing_source_hosts` for diagnosis.
- Publish target is derived from the deployment: production →
  `https://{VERCEL_PROJECT_PRODUCTION_URL}/api/public-snapshot`; preview →
  the deployment's own `VERCEL_URL` (with `x-vercel-protection-bypass` from
  `VERCEL_AUTOMATION_BYPASS_SECRET` when set). A non-production deployment
  cannot publish to production unless `COLLECTOR_ALLOW_NON_PRODUCTION_PUBLISH=1`.
- The collector no longer writes the serving Runtime Cache key itself. The Node
  `/api/public-snapshot` PUT handler owns it (Postgres insert, then the
  monotonic, rollback-protected Runtime Cache publish).

### Read path (`/api/status`, `/api/public-snapshot` GET, today actions)

- `loadVerifiedSnapshot()` probes only `(snapshot_hash, snapshot_as_of)` from
  `public_verified_snapshots`, memoizes the validated payload per warm instance,
  re-probes at most every 60 s, fetches the payload by hash only when the head
  changes (trying the Runtime Cache published key first), and keeps serving the
  last known durable revision if Postgres is briefly unreachable.
- `/api/status` exposes `snapshot.payload_origin` in `DATABASE` mode:
  `MEMO | HEAD_PROBE | RUNTIME_CACHE | DATABASE | MEMO_STALE`. Seeing mostly
  `MEMO`/`HEAD_PROBE` in production means the per-request egress fix is active.
- The browser accepts every server `source_mode` (now including `DATABASE`);
  `scripts/check-runtime-status.mjs` and
  `pipeline/tests/test_runtime_status_ui_contract.py` derive the list from the
  server source so it cannot drift again.

### Deep-cycle stage list

`ccgp → event1..6 → tjmugh → tjnothop → teda → tjfch → tjzxfc → tjzyefy →
tjzyefy_intent → regional_{bj,he,ln,jl,hl}(+_fallback) → publish` (25 stages).

`tjzxfc` (天津市中心妇产科医院 院内比选/调研), `tjzyefy` (天津中医药大学第二附属医院
院内调研) and `tjzyefy_intent` (同院 采购意向公告) were added on 2026-09-27 so a
Vercel publish carries the same Tianjin early signals (PRE_MARKET_SIGNAL /
PROCUREMENT_INTENT cards, the data behind 采购意向跟进) as the GitHub refresh.
They run through one spec-driven runner (`OfficialSiteSource` /
`_run_official_site_stage`) that reuses the verified sync scripts' discovery,
parsers, unsupported-notice codes and retry rule, with the 30-day / 20-candidate
window of the workflow. Publish now requires their canonical keys too
(`COLLECTOR_CANONICAL_STATE_INCOMPLETE:tjzxfc,...` names what is missing). The
intraday incremental chain does not scan these three sources yet.

## Operating notes

- To recover a broken day: wait until the failing stage's `lease_expires_at`
  has passed (≤ 5.25 min after it started), then call the authenticated
  `/api/collector-run`. Expect `cycle_id = prod:{date}:recovery-{n}`.
- `COLLECTOR_STAGE_TIMEOUT` in `/api/collector-status` means the worker was
  killed by the platform; look at `deferred_candidate_count` and the budget
  codes before raising `maxDuration`.
- `web/pyproject.toml` pins `vercel`, `vercel-cache`, `vercel-queue`. Bump them
  together and re-run `python3 -m unittest discover -s tests` from
  `web/pipeline`.

## Tests

- `web/pipeline/tests/test_collector_lifecycle_behavior.py` runs the real
  modules against `tests/_stubs/vercel` (in-memory Runtime Cache + queue with
  idempotency keys): full cycle, platform kill → next-day cron accepted,
  same-day recovery ids/limits, send failure releases the lease, duplicate
  delivery under a live lease, output-loss replay, budget deferral, regression
  gate, publish target resolution, `vercel.json` ↔ constant parity.
- `web/scripts/check-verified-snapshot.mjs` and `check-runtime-status.mjs`
  cover the memo/head-probe read path with an injected durable store.

Follow-ups deliberately **not** in this change: moving canonical collector
state out of Runtime Cache into Postgres (S-1 in the audit), adding the three
official-site sources to the intraday incremental chain, and deciding which of
the two publishers (GitHub runner vs Vercel collector) is retired.
