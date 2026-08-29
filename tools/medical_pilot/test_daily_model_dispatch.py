from __future__ import annotations

import unittest
from datetime import datetime, timezone

from tools.medical_pilot.daily_model_dispatch import build_daily_agnes_dispatch_plan


class DailyModelDispatchTests(unittest.TestCase):
    def test_daily_model_candidates_are_staggered_and_preserve_count(self) -> None:
        now = datetime(2026, 8, 31, 0, 10, tzinfo=timezone.utc)
        daily_plan = {
            "mode": "INTERACTIVE_DAILY",
            "model_candidate_ids": [
                "opp_11111111-1111-1111-1111-111111111111",
                "opp_22222222-2222-2222-2222-222222222222",
                "opp_33333333-3333-3333-3333-333333333333",
            ],
        }
        result = build_daily_agnes_dispatch_plan(profile_id="mprof_demo", daily_plan=daily_plan, now=now)
        self.assertEqual(result["source_model_candidate_count"], 3)
        plan = result["agnes_dispatch_plan"]
        self.assertEqual(len(plan["items"]), 3)
        self.assertTrue(all(item["task_type"] == "DAILY_TOP5_EXPLANATION" for item in plan["items"]))
        starts = [datetime.fromisoformat(item["not_before"]) for item in plan["items"]]
        self.assertGreater((starts[1] - starts[0]).total_seconds(), 4)
        self.assertGreater((starts[2] - starts[1]).total_seconds(), 4)

    def test_duplicate_model_candidate_ids_fail_closed(self) -> None:
        now = datetime(2026, 8, 31, 0, 10, tzinfo=timezone.utc)
        daily_plan = {
            "mode": "INTERACTIVE_DAILY",
            "model_candidate_ids": ["opp_x", "opp_x"],
        }
        with self.assertRaises(ValueError):
            build_daily_agnes_dispatch_plan(profile_id="mprof_demo", daily_plan=daily_plan, now=now)

    def test_empty_model_candidate_list_creates_empty_dispatch_without_network(self) -> None:
        now = datetime(2026, 8, 31, 0, 10, tzinfo=timezone.utc)
        result = build_daily_agnes_dispatch_plan(
            profile_id="mprof_demo",
            daily_plan={"mode": "INTERACTIVE_DAILY", "model_candidate_ids": []},
            now=now,
        )
        self.assertEqual(result["source_model_candidate_count"], 0)
        self.assertEqual(result["agnes_dispatch_plan"]["items"], [])


if __name__ == "__main__":
    unittest.main()
