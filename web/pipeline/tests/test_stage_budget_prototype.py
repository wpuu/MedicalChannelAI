from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collector_stage_budget_prototype import (
    CursorInvalid, CycleCancelled, StageSlice, _seal,
)
from tests.test_collector_native_reliability import MemoryCache, runtime


class Clock:
    def __init__(self):
        self.t = 0.0
        self.epoch = 1790985600.0

    def advance(self, seconds):
        self.t += seconds

    def wall(self):
        return self.epoch + self.t


class StageBudgetPrototypeTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.owned = True
        self.saved = None
        self.calls = []
        self.tasks = [f"bj:query:{i}" for i in range(10)]

    def engine(self, **changes):
        options = dict(
            cycle_id="prod:2026-10-03:morning:twice-daily-v1",
            stage="regional_bj", task_ids=self.tasks, plan_hash="frozen-plan",
            expires_at=self.clock.epoch + 3600, monotonic=lambda: self.clock.t,
            wall_time=self.clock.wall, owns_cycle=lambda: self.owned,
        )
        options.update(changes)
        return StageSlice(**options)

    def save(self, cursor):
        self.saved = copy.deepcopy(cursor)

    def slow(self, task_id, timeout):
        self.calls.append((task_id, timeout))
        if timeout < 30:
            self.clock.advance(timeout)
            raise TimeoutError("simulated remaining-time timeout")
        self.clock.advance(30)
        return {"verified": task_id}

    def run_slice(self, value=None, **changes):
        revision = changes.pop("expected_revision", 0 if value is None else value["revision"])
        return self.engine().run(
            value, work=self.slow, sleep=self.clock.advance, checkpoint=self.save,
            expected_revision=revision, **changes,
        )

    def test_existing_beijing_stage_exceeds_300_and_repeats_all_queries(self):
        cache = MemoryCache({runtime._regional_records_key("BJ"): []})
        state = {"cycle_as_of": "2026-10-03T00:00:00+00:00", "stages": {}}
        calls = []
        def slow_search(*args, **kwargs):
            calls.append((kwargs["keyword"], kwargs["notice_type"]))
            self.clock.advance(30)
            return []
        with patch.object(runtime, "RegionalCcgpSearchSession", return_value=object()), \
             patch.object(runtime, "fetch_regional_candidates_page", side_effect=slow_search), \
             patch.object(runtime.time, "sleep", side_effect=self.clock.advance), \
             patch.object(runtime, "fetch_ccgp_detail_html", side_effect=AssertionError("no live detail")), \
             patch.object(runtime, "_persist_verified_snapshot_durably", side_effect=AssertionError("no publish")):
            first = runtime._run_regional_market(cache, state, "regional_bj")
            self.assertTrue(first["fallback_required"])
            self.assertEqual(len(calls), 10)
            self.assertEqual(self.clock.t, 340)
            runtime._run_regional_market(cache, state, "regional_bj")
        self.assertEqual(self.clock.t, 680)
        self.assertEqual(calls[:10], calls[10:])
        print("REPRO: existing regional_bj=340 simulated seconds; replay=680, 20 queries")

    def test_slow_search_pauses_and_resumes_without_repeating_committed_work(self):
        first = self.run_slice()
        self.assertEqual(first.action, "PAUSED")
        self.assertEqual(first.processed, 6)
        self.assertEqual(first.elapsed_seconds, 225)
        self.assertEqual(first.cursor["status"], "PAUSED")
        self.assertEqual(self.saved["index"], 6)
        self.assertLess(self.calls[-1][1], 90)
        second = self.run_slice(self.saved)
        self.assertEqual(second.action, "COMPLETE")
        self.assertEqual(second.processed, 4)
        self.assertEqual(second.elapsed_seconds, 136)
        self.assertEqual([r["task_id"] for r in second.cursor["results"]], self.tasks)
        committed = [task for task, timeout in self.calls if timeout >= 30]
        self.assertEqual(committed, self.tasks)
        print("PROTOTYPE: 225s pause + 136s resume; 10 committed queries, no skipped task")

    def test_duplicate_continuation_does_no_work(self):
        first = self.run_slice()
        calls = len(self.calls)
        duplicate = self.engine().run(
            self.saved, work=self.slow, sleep=self.clock.advance,
            checkpoint=self.save, expected_revision=0,
        )
        self.assertEqual(duplicate.action, "STALE_CONTINUATION")
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(duplicate.processed, 0)

    def test_completed_continuation_is_idempotent(self):
        self.run_slice()
        done = self.run_slice(self.saved)
        calls = len(self.calls)
        again = self.run_slice(done.cursor)
        self.assertEqual(again.action, "ALREADY_COMPLETE")
        self.assertEqual(len(self.calls), calls)

    def test_request_timeout_is_capped_by_remaining_budget(self):
        self.run_slice()
        self.assertAlmostEqual(self.calls[-1][1], 17)

    def test_no_request_at_admission_boundary(self):
        e = self.engine(budget_seconds=24, reserve_seconds=15)
        result = e.run(None, work=self.slow, sleep=self.clock.advance, checkpoint=self.save)
        self.assertEqual(result.action, "PAUSED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.clock.t, 0)

    def test_result_at_exact_work_deadline_can_be_checkpointed(self):
        e = self.engine(task_ids=["only"], budget_seconds=49, reserve_seconds=15)
        result = e.run(None, work=self.slow, sleep=self.clock.advance, checkpoint=self.save)
        self.assertEqual(result.action, "COMPLETE")
        self.assertEqual(result.elapsed_seconds, 34)

    def test_late_result_is_not_committed(self):
        def late(task, timeout):
            self.clock.advance(250)
            return "late"
        result = self.engine().run(None, work=late, sleep=self.clock.advance, checkpoint=self.save)
        self.assertEqual(result.action, "PAUSED")
        self.assertEqual(result.cursor["index"], 0)
        self.assertIsNone(self.saved)

    def test_full_request_timeout_is_failure_not_success(self):
        def failed(task, timeout):
            self.clock.advance(timeout)
            raise TimeoutError("source timed out")
        with self.assertRaises(TimeoutError):
            self.engine().run(None, work=failed, sleep=self.clock.advance, checkpoint=self.save)
        self.assertIsNone(self.saved)

    def test_failure_preserves_last_checkpoint(self):
        def fail_second(task, timeout):
            if task.endswith(":1"):
                raise RuntimeError("simulated parse failure")
            return "first verified result"
        with self.assertRaisesRegex(RuntimeError, "parse failure"):
            self.engine().run(None, work=fail_second, sleep=self.clock.advance, checkpoint=self.save)
        self.assertEqual(self.saved["index"], 1)
        self.assertEqual(self.saved["status"], "PAUSED")
        continued = self.run_slice(self.saved)
        self.assertEqual(self.calls[0][0], self.tasks[1])
        self.assertEqual(continued.cursor["results"][0]["result"], "first verified result")

    def test_checkpoint_failure_does_not_allow_next_task(self):
        def fail_save(cursor):
            raise OSError("simulated cache failure")
        with self.assertRaises(OSError):
            self.engine().run(None, work=self.slow, sleep=self.clock.advance, checkpoint=fail_save)
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.saved)

    def test_cancel_before_request_does_no_work(self):
        self.owned = False
        with self.assertRaises(CycleCancelled):
            self.run_slice()
        self.assertEqual(self.calls, [])

    def test_cancel_during_request_does_not_save_result(self):
        def cancel(task, timeout):
            self.owned = False
            return "do not commit"
        with self.assertRaises(CycleCancelled):
            self.engine().run(None, work=cancel, sleep=self.clock.advance, checkpoint=self.save)
        self.assertIsNone(self.saved)

    def test_cancel_after_checkpoint_never_runs_next_task(self):
        def cancel_on_save(cursor):
            self.save(cursor)
            self.owned = False
        with self.assertRaises(CycleCancelled):
            self.engine().run(None, work=self.slow, sleep=self.clock.advance, checkpoint=cancel_on_save)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.saved["status"], "PAUSED")

    def test_corrupt_checksum_and_structural_fields_fail_closed(self):
        cursor = self.engine().cursor(None)
        bad = copy.deepcopy(cursor)
        bad["index"] = 1
        with self.assertRaises(CursorInvalid):
            self.engine().cursor(bad)
        for update in ({"index": True}, {"revision": -1}, {"results": [1]},
                       {"status": "COMPLETE"}, {"status": "SUCCESS"},
                       {"extra": "unknown"}, {"index": 11}, {"index": -1}):
            with self.subTest(update=update), self.assertRaises(CursorInvalid):
                self.engine().cursor(_seal({**cursor, **update}))

    def test_expired_cursor_cannot_restart(self):
        cursor = self.engine().cursor(None)
        self.clock.advance(3600)
        with self.assertRaisesRegex(CursorInvalid, "EXPIRED"):
            self.run_slice(cursor)
        self.assertEqual(self.calls, [])

    def test_expiry_during_request_does_not_commit(self):
        def expires(task, timeout):
            self.clock.advance(3600)
            return "expired"
        with self.assertRaisesRegex(CursorInvalid, "EXPIRED"):
            self.engine().run(None, work=expires, sleep=self.clock.advance, checkpoint=self.save)
        self.assertIsNone(self.saved)

    def test_cycle_period_stage_plan_or_task_order_change_rejects_cursor(self):
        cursor = self.engine().cursor(None)
        for update in (
            {"cycle_id": "prod:2026-10-03:noon:twice-daily-v1"},
            {"stage": "regional_bj_fallback"}, {"plan_hash": "different"},
            {"task_ids": list(reversed(self.tasks))},
            {"expires_at": self.clock.epoch + 7200},
        ):
            with self.subTest(update=update), self.assertRaises(CursorInvalid):
                self.engine(**update).cursor(cursor)

    def test_revision_ahead_rejected(self):
        with self.assertRaisesRegex(CursorInvalid, "AHEAD"):
            self.run_slice(expected_revision=1)

    def test_binding_types_do_not_accept_boolean_as_integer(self):
        cursor = self.engine(task_ids=["only"]).cursor(None)
        for update in ({"version": True}, {"task_count": True}):
            with self.subTest(update=update), self.assertRaises(CursorInvalid):
                self.engine(task_ids=["only"]).cursor(_seal({**cursor, **update}))
        with self.assertRaises(ValueError):
            self.engine(cycle_id=123)

    def test_invalid_limits_and_nonfinite_values(self):
        for update in ({"budget_seconds": 301}, {"reserve_seconds": 240},
                       {"request_timeout": 0}, {"minimum_timeout": 91},
                       {"delay_seconds": -1}, {"budget_seconds": math.nan},
                       {"expires_at": math.inf}, {"task_ids": ["same", "same"]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.engine(**update)

    def test_empty_task_plan_completes_without_requests(self):
        result = self.engine(task_ids=[]).run(
            None, work=self.slow, sleep=self.clock.advance, checkpoint=self.save,
        )
        self.assertEqual(result.action, "COMPLETE")
        self.assertEqual(result.processed, 0)
        self.assertEqual(self.calls, [])

    def test_paused_stage_cannot_satisfy_existing_publish_gate(self):
        result = self.run_slice()
        stages = {stage: {"status": "COMPLETED", "result": {"fallback_required": False}}
                  for stage in runtime.STAGE_ORDER if stage != "publish"}
        stages["regional_bj"] = {"status": result.action, "terminal": False}
        failed, incomplete = runtime._publish_stage_requirements(stages)
        self.assertIn("regional_bj", incomplete)
        self.assertEqual(failed, [])

    def test_checkpoint_roundtrip_retains_tasks_and_revision(self):
        import json
        self.run_slice()
        roundtrip = json.loads(json.dumps(self.saved))
        result = self.run_slice(roundtrip)
        self.assertEqual(result.action, "COMPLETE")
        self.assertEqual(result.cursor["revision"], 10)

    def test_no_request_when_pacing_consumes_remaining_admission_room(self):
        e = self.engine(budget_seconds=25, reserve_seconds=15)
        def delayed_pacing(seconds):
            self.clock.advance(seconds + 2)
        result = e.run(None, work=self.slow, sleep=delayed_pacing, checkpoint=self.save)
        self.assertEqual(result.action, "PAUSED")
        self.assertEqual(self.calls, [])

    def test_checkpoint_callback_cannot_mutate_next_task_state(self):
        def mutate_saved_argument(cursor):
            self.save(cursor)
            cursor["index"] = 10
            cursor["results"].clear()
        result = self.engine().run(None, work=self.slow, sleep=self.clock.advance,
                                   checkpoint=mutate_saved_argument)
        self.assertEqual(result.action, "PAUSED")
        self.assertEqual(result.cursor["index"], 6)
        self.assertEqual(len(result.cursor["results"]), 6)


if __name__ == "__main__":
    unittest.main()
