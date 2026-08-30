from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.medical_pilot.agnes_global_lease import (
    SQLiteAgnesLeaseStore,
    acquire_global_lease,
    evaluate_lease,
    initial_lease_state,
    release_global_lease,
)


NOW = datetime(2026, 8, 29, 8, 0, 0, tzinfo=timezone.utc)


def item(task_id: str, *, not_before: datetime = NOW) -> dict:
    return {
        "task_id": task_id,
        "task_type": "DAILY_TOP5_EXPLANATION",
        "not_before": not_before.isoformat(),
        "requires_global_lease": True,
    }


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


class AgnesGlobalLeaseTests(unittest.TestCase):
    def test_first_task_gets_global_lease_and_reserves_start(self) -> None:
        state = initial_lease_state(now=NOW)
        decision, next_state = evaluate_lease(state, dispatch_item=item("task-a"), worker_id="worker-1", now=NOW)
        self.assertEqual(decision.status, "GRANTED")
        self.assertTrue(decision.lease_id.startswith("agl_"))
        self.assertEqual(decision.active_in_flight, 1)
        self.assertEqual(decision.starts_last_60_seconds, 1)
        self.assertEqual(next_state["revision"], 1)
        self.assertEqual(len(next_state["active_leases"]), 1)

    def test_not_before_is_enforced_before_rate_capacity(self) -> None:
        future = NOW + timedelta(seconds=30)
        decision, next_state = evaluate_lease(
            initial_lease_state(now=NOW),
            dispatch_item=item("task-future", not_before=future),
            worker_id="worker-1",
            now=NOW,
        )
        self.assertEqual(decision.status, "DEFERRED_NOT_BEFORE")
        self.assertEqual(decision.retry_after, future.isoformat())
        self.assertIsNone(next_state)

    def test_same_task_cannot_have_two_active_leases(self) -> None:
        state = initial_lease_state(now=NOW)
        first, state = evaluate_lease(state, dispatch_item=item("task-a"), worker_id="worker-1", now=NOW)
        self.assertEqual(first.status, "GRANTED")
        duplicate, next_state = evaluate_lease(
            state,
            dispatch_item=item("task-a", not_before=NOW),
            worker_id="worker-2",
            now=NOW + timedelta(seconds=6),
        )
        self.assertEqual(duplicate.status, "DEFERRED_DUPLICATE_ACTIVE")
        self.assertIsNone(next_state)

    def test_minimum_global_start_spacing_is_enforced(self) -> None:
        state = initial_lease_state(now=NOW)
        _, state = evaluate_lease(state, dispatch_item=item("task-a"), worker_id="worker-1", now=NOW)
        decision, next_state = evaluate_lease(
            state,
            dispatch_item=item("task-b"),
            worker_id="worker-2",
            now=NOW + timedelta(seconds=4),
        )
        self.assertEqual(decision.status, "DEFERRED_SPACING")
        self.assertEqual(decision.retry_after, (NOW + timedelta(seconds=5)).isoformat())
        self.assertIsNone(next_state)

    def test_max_two_in_flight_is_enforced(self) -> None:
        state = initial_lease_state(now=NOW)
        _, state = evaluate_lease(state, dispatch_item=item("task-a"), worker_id="worker-1", now=NOW)
        _, state = evaluate_lease(
            state,
            dispatch_item=item("task-b"),
            worker_id="worker-2",
            now=NOW + timedelta(seconds=5),
        )
        decision, next_state = evaluate_lease(
            state,
            dispatch_item=item("task-c"),
            worker_id="worker-3",
            now=NOW + timedelta(seconds=10),
        )
        self.assertEqual(decision.status, "DEFERRED_IN_FLIGHT")
        self.assertEqual(decision.active_in_flight, 2)
        self.assertIsNone(next_state)

    def test_rpm_limit_is_enforced_even_when_old_leases_are_released(self) -> None:
        state = initial_lease_state(now=NOW)
        state["recent_start_timestamps"] = [
            (NOW - timedelta(seconds=55 - index * 4)).isoformat() for index in range(12)
        ]
        state["recent_start_timestamps"].sort()
        state["last_start_at"] = (NOW - timedelta(seconds=5)).isoformat()
        decision, next_state = evaluate_lease(state, dispatch_item=item("task-rpm"), worker_id="worker-1", now=NOW)
        self.assertEqual(decision.status, "DEFERRED_RPM")
        self.assertEqual(decision.starts_last_60_seconds, 12)
        self.assertIsNone(next_state)

    def test_expired_lease_is_cleaned_but_start_history_remains(self) -> None:
        state = initial_lease_state(now=NOW)
        state["active_leases"] = [
            {
                "lease_id": "agl_" + "a" * 64,
                "task_id": "old-task",
                "worker_id": "dead-worker",
                "acquired_at": (NOW - timedelta(minutes=3)).isoformat(),
                "expires_at": (NOW - timedelta(seconds=1)).isoformat(),
            }
        ]
        state["recent_start_timestamps"] = [(NOW - timedelta(seconds=30)).isoformat()]
        state["last_start_at"] = (NOW - timedelta(seconds=30)).isoformat()
        decision, next_state = evaluate_lease(state, dispatch_item=item("new-task"), worker_id="worker-1", now=NOW)
        self.assertEqual(decision.status, "GRANTED")
        self.assertEqual(decision.active_in_flight, 1)
        self.assertEqual(decision.starts_last_60_seconds, 2)
        self.assertEqual(len(next_state["active_leases"]), 1)
        self.assertEqual(next_state["active_leases"][0]["task_id"], "new-task")

    def test_release_requires_same_worker_and_does_not_erase_rpm_history(self) -> None:
        store = MemoryStore(initial_lease_state(now=NOW))
        granted = acquire_global_lease(store, dispatch_item=item("task-a"), worker_id="worker-1", now=NOW)
        self.assertEqual(granted.status, "GRANTED")
        self.assertFalse(release_global_lease(store, lease_id=granted.lease_id, worker_id="worker-2", now=NOW + timedelta(seconds=1)))
        self.assertTrue(release_global_lease(store, lease_id=granted.lease_id, worker_id="worker-1", now=NOW + timedelta(seconds=1)))
        state = store.load()
        self.assertEqual(state["active_leases"], [])
        self.assertEqual(len(state["recent_start_timestamps"]), 1)

    def test_sqlite_reference_store_persists_and_cas_coordinates_processes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agnes-lease.sqlite3"
            store_a = SQLiteAgnesLeaseStore(path, now=NOW)
            store_b = SQLiteAgnesLeaseStore(path, now=NOW)
            first = acquire_global_lease(store_a, dispatch_item=item("task-a"), worker_id="worker-a", now=NOW)
            self.assertEqual(first.status, "GRANTED")
            second = acquire_global_lease(
                store_b,
                dispatch_item=item("task-b"),
                worker_id="worker-b",
                now=NOW + timedelta(seconds=1),
            )
            self.assertEqual(second.status, "DEFERRED_SPACING")
            self.assertEqual(store_b.load()["revision"], 1)


if __name__ == "__main__":
    unittest.main()
