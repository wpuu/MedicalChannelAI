# Beijing stage budget: offline prototype, not connected to production

## Provenance and scope

Local snapshot `de101e434fcba427d0a873be30905d627c775ecc` was created at 2026-10-03 17:28:09 UTC from the PR75 patch applied to main `62299590dd3898e040ccc9db5fda1298d4509d51`. It has the identical Git tree `89464aaa67cc92666fe9d1e855824f483dba94c3` as remote candidate `ca91df269636d8604814d2e744d12587b8fadc82`; it is a local reconstruction, not that remote commit. Readback confirmed PR75 still points to ca91df, and the new isolated branch was absent. No other active local editor/Git process was observed; this is not proof that online writers stopped.

The prototype file `web/pipeline/scripts/collector_stage_budget_prototype.py` was created at 17:31:48 UTC, and `web/pipeline/tests/test_stage_budget_prototype.py` at 17:33:50 UTC on October 3. Both were preserved. Only this offline component, its mock tests, this evidence, and a false deployment mapping for its isolated branch are saved. Runtime entrypoints, acquisition adapters, Cron, Queue triggers, permissions and PR75 are unchanged. This draft is stacked on PR75's branch so its diff contains only this batch.

## Simulated evidence and checks

The existing `regional_bj` stage is invoked with mocked empty searches, each advancing a fake clock by 30 seconds, plus its existing four-second pacing. Ten queries consume **340 simulated seconds**; replay repeats all ten and reaches **680 simulated seconds**. No live search, detail request, model, publication or runtime cache is called. These figures are a deterministic mock scenario, not measured production latency.

The prototype uses a 240-second slice budget with a 15-second checkpoint/return reserve. Each request receives min(90 seconds, remaining work time). In the same mock scenario it returns **PAUSED at 225 simulated seconds**, with six committed query results; the last shortened request times out and remains uncommitted. Resuming the cursor completes the remaining four in **136 simulated seconds**. The ten committed tasks appear once; an interrupted uncommitted request may be retried. PAUSED is not source success or stage completion.

At 17:38 UTC, 95 selected tests passed, including 25 prototype tests and existing native reliability, morning/noon, terminal race and regional runtime tests. A later review tightened binding types (JSON bool must not equal numeric version/count) and added one regression; the final run passed all 96 tests, with zero failures or errors. The test harness blocks socket connect/connect_ex, imports the existing MemoryCache fixtures, and uses fake clocks. Coverage includes duplicate and completed continuations, JSON round trips, frozen cycle/period/stage/plan/task order/expiry, request/admission/exact/late budget boundaries, corrupt cursors, expiry, cancellation before/during/after saving, request and checkpoint failure. The actual existing publish gate rejects the prototype's PAUSED stage. Existing reliability tests retain the last verified snapshot and reject incomplete or stale-cycle publication; this is existing behavior, not runtime integration of this prototype.

Reproducible command from `web/pipeline`:

```bash
python3 - <<'PY'
import socket, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path('tests').resolve()))
def blocked(*args, **kwargs):
    raise AssertionError('LIVE_NETWORK_FORBIDDEN_IN_OFFLINE_TESTS')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
names = ['tests.test_stage_budget_prototype', 'tests.test_collector_native_reliability',
         'test_twice_daily_search', 'test_twice_daily_terminal_race', 'test_vercel_regional_runtime']
result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
print('OFFLINE_TOTAL', result.testsRun, 'FAILURES', len(result.failures), 'ERRORS', len(result.errors))
raise SystemExit(not result.wasSuccessful())
PY
```

## Separate code review and unimplemented boundary

A separate review pass checked all cursor transitions, callback failure paths, exact budget admission, binding validation and runtime imports. It found and fixed bool/int binding equivalence. The SHA-256 checksum detects accidental corruption only; it does not authenticate writers. Stale revision detection assumes the caller supplies the latest checkpoint and serial ownership; it is not a concurrency/CAS guarantee. Ownership checks around saving cannot prevent a stale writer's write during that callback.

Work and checkpoint callbacks must obey deadlines. Socket inactivity timeouts alone do not enforce an absolute total request deadline; checkpoint duration or a callback ignoring its supplied timeout can exceed the reserve. Late work is rejected without advancing its cursor, but this cannot prevent process termination. No production timeout guarantee is claimed.

The task list here models ten fixed search units. Freezing discovered detail tasks, binding verified results to canonical merging, reading/writing an actual durable checkpoint and reliable save-to-enqueue handoff are not implemented. A checkpoint saved before enqueue can strand work; enqueue before checkpoint can duplicate work. Current Queue maxDeliveries=3 is not a guaranteed continuation allowance: slower workloads can require more than three slices. The module is not imported by any runtime entrypoint and cannot recover the live collector.

**Next item requires separate approval:** design and validate bounded, idempotent persistent cursor/continuation ownership and crash recovery across the existing state store and Queue, including stale-write fencing, actual total request deadlines, cursor expiry and complete detail coverage. This expands the cross-system state protocol and is intentionally stopped at design here. No new database/service, migration, credential or permission has been introduced. Morning/noon binding, old-cycle fences, complete validation before publication, and failure retaining the verified snapshot remain untouched.
