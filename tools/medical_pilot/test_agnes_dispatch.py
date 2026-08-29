from __future__ import annotations

import unittest
from datetime import datetime, timezone

from tools.medical_pilot.agnes_dispatch import build_agnes_dispatch_plan, retry_delay_seconds


class AgnesDispatchTests(unittest.TestCase):
    def test_priorities_and_start_times_are_staggered(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, 0, tzinfo=timezone.utc)
        tasks = [
            {"task_id": "bench-1", "task_type": "BENCHMARK", "requested_at": "2026-08-31T01:00:00+00:00"},
            {"task_id": "deep-1", "task_type": "INTERACTIVE_DEEP_DIVE", "requested_at": "2026-08-31T01:00:00+00:00"},
            {"task_id": "daily-1", "task_type": "DAILY_TOP5_EXPLANATION", "requested_at": "2026-08-31T01:00:00+00:00"},
        ]
        plan = build_agnes_dispatch_plan(tasks, now=now)
        items = plan["items"]
        self.assertEqual([item["task_id"] for item in items], ["deep-1", "daily-1", "bench-1"])
        starts = [datetime.fromisoformat(item["not_before"]) for item in items]
        self.assertGreater((starts[1] - starts[0]).total_seconds(), 4)
        self.assertGreater((starts[2] - starts[1]).total_seconds(), 4)
        self.assertTrue(all(item["requires_global_lease"] for item in items))
        self.assertTrue(plan["requires_persistent_global_lease"])

    def test_same_batch_is_deterministic(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, 0, tzinfo=timezone.utc)
        tasks = [
            {"task_id": "a", "task_type": "TAXONOMY_CLASSIFICATION", "requested_at": "2026-08-31T01:00:00Z"},
            {"task_id": "b", "task_type": "TAXONOMY_CLASSIFICATION", "requested_at": "2026-08-31T01:00:00Z"},
        ]
        self.assertEqual(build_agnes_dispatch_plan(tasks, now=now), build_agnes_dispatch_plan(tasks, now=now))

    def test_benchmark_cannot_jump_ahead_of_interactive_work(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, 0, tzinfo=timezone.utc)
        tasks = [
            {"task_id": "benchmark-old", "task_type": "BENCHMARK", "requested_at": "2026-08-30T00:00:00Z"},
            {"task_id": "urgent-new", "task_type": "URGENT_ACTION_EXPLANATION", "requested_at": "2026-08-31T01:00:00Z"},
        ]
        plan = build_agnes_dispatch_plan(tasks, now=now)
        self.assertEqual(plan["items"][0]["task_id"], "urgent-new")

    def test_duplicate_or_unknown_tasks_fail_closed(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            build_agnes_dispatch_plan([
                {"task_id": "x", "task_type": "BENCHMARK", "requested_at": "2026-08-31T01:00:00Z"},
                {"task_id": "x", "task_type": "BENCHMARK", "requested_at": "2026-08-31T01:00:00Z"},
            ], now=now)
        with self.assertRaises(ValueError):
            build_agnes_dispatch_plan([
                {"task_id": "x", "task_type": "FREEFORM", "requested_at": "2026-08-31T01:00:00Z"},
            ], now=now)

    def test_429_backoff_is_longer_than_5xx_and_is_stable(self) -> None:
        a = retry_delay_seconds(task_id="task-1", error_class="HTTP_429", attempt=0)
        b = retry_delay_seconds(task_id="task-1", error_class="HTTP_429", attempt=0)
        c = retry_delay_seconds(task_id="task-1", error_class="HTTP_5XX", attempt=0)
        self.assertEqual(a, b)
        self.assertGreaterEqual(a, 60)
        self.assertGreater(a, c)


if __name__ == "__main__":
    unittest.main()
