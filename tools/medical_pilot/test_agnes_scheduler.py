from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from tools.medical_pilot.agnes_dispatch import build_agnes_dispatch_plan
from tools.medical_pilot.agnes_global_lease import initial_lease_state
from tools.medical_pilot.agnes_scheduler import claim_next_agnes_task


NOW = datetime(2026, 8, 29, 8, 0, 0, tzinfo=timezone.utc)


class MemoryStore:
    def __init__(self, state: dict) -> None:
        self.state = copy.deepcopy(state)

    def load(self) -> dict:
        return copy.deepcopy(self.state)

    def compare_and_swap(self, expected_revision: int, new_state: dict) -> bool:
        if self.state["revision"] != expected_revision:
            return False
        self.state = copy.deepcopy(new_state)
        return True


def plan(now: datetime = NOW) -> dict:
    return build_agnes_dispatch_plan(
        [
            {"task_id": "daily-a", "task_type": "DAILY_TOP5_EXPLANATION", "requested_at": now.isoformat()},
            {"task_id": "deep-a", "task_type": "INTERACTIVE_DEEP_DIVE", "requested_at": now.isoformat()},
        ],
        now=now,
    )


class AgnesSchedulerTests(unittest.TestCase):
    def test_no_task_is_claimed_before_not_before(self) -> None:
        dispatch = plan()
        store = MemoryStore(initial_lease_state(now=NOW))
        result = claim_next_agnes_task(dispatch, store=store, worker_id="worker-a", now=NOW)
        self.assertEqual(result["status"], "NO_DUE_TASK")
        self.assertFalse(result["provider_start_allowed"])
        self.assertIsNotNone(result["retry_after"])

    def test_highest_priority_due_task_claims_only_after_global_lease(self) -> None:
        dispatch = plan()
        due_time = max(datetime.fromisoformat(row["not_before"]) for row in dispatch["items"]) + timedelta(seconds=1)
        store = MemoryStore(initial_lease_state(now=NOW))
        result = claim_next_agnes_task(dispatch, store=store, worker_id="worker-a", now=due_time)
        self.assertEqual(result["status"], "CLAIMED")
        self.assertTrue(result["provider_start_allowed"])
        self.assertEqual(result["task"]["task_type"], "INTERACTIVE_DEEP_DIVE")
        self.assertEqual(result["lease_decision"]["status"], "GRANTED")
        self.assertTrue(result["lease_decision"]["lease_id"].startswith("agl_"))

    def test_second_worker_cannot_start_during_global_spacing_window(self) -> None:
        dispatch = plan()
        due_time = max(datetime.fromisoformat(row["not_before"]) for row in dispatch["items"]) + timedelta(seconds=1)
        store = MemoryStore(initial_lease_state(now=NOW))
        first = claim_next_agnes_task(dispatch, store=store, worker_id="worker-a", now=due_time)
        self.assertTrue(first["provider_start_allowed"])
        second = claim_next_agnes_task(
            dispatch,
            store=store,
            worker_id="worker-b",
            now=due_time + timedelta(seconds=1),
        )
        self.assertEqual(second["status"], "GLOBAL_CAPACITY_DEFERRED")
        self.assertFalse(second["provider_start_allowed"])
        self.assertEqual(second["lease_decision"]["status"], "DEFERRED_SPACING")

    def test_duplicate_active_task_is_skipped_for_other_due_task(self) -> None:
        dispatch = plan()
        due_time = max(datetime.fromisoformat(row["not_before"]) for row in dispatch["items"]) + timedelta(seconds=1)
        store = MemoryStore(initial_lease_state(now=NOW))
        first = claim_next_agnes_task(dispatch, store=store, worker_id="worker-a", now=due_time)
        self.assertEqual(first["task"]["task_type"], "INTERACTIVE_DEEP_DIVE")
        second_time = due_time + timedelta(seconds=6)
        second = claim_next_agnes_task(dispatch, store=store, worker_id="worker-b", now=second_time)
        self.assertEqual(second["status"], "CLAIMED")
        self.assertEqual(second["task"]["task_type"], "DAILY_TOP5_EXPLANATION")

    def test_plan_without_persistent_lease_invariant_is_rejected(self) -> None:
        dispatch = plan()
        dispatch["requires_persistent_global_lease"] = False
        with self.assertRaises(ValueError):
            claim_next_agnes_task(
                dispatch,
                store=MemoryStore(initial_lease_state(now=NOW)),
                worker_id="worker-a",
                now=NOW + timedelta(minutes=1),
            )


if __name__ == "__main__":
    unittest.main()
