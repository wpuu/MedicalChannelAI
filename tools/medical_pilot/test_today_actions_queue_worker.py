from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tools.medical_pilot.agnes_dispatch_queue import MemoryAgnesDispatchQueue, queue_today_actions_dispatch
from tools.medical_pilot.agnes_global_lease import initial_lease_state
from tools.medical_pilot.agnes_task_result import MemoryAgnesTaskResultStore
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions import build_today_actions
from tools.medical_pilot.today_actions_dispatch import build_today_actions_agnes_dispatch
from tools.medical_pilot.today_actions_queue_worker import execute_next_queued_today_actions_task


NOW = datetime(2026, 8, 30, 8, 10, tzinfo=ZoneInfo("Asia/Shanghai"))


class MemoryLeaseStore:
    def __init__(self) -> None:
        self.state = initial_lease_state(now=NOW)

    def load(self):
        return copy.deepcopy(self.state)

    def compare_and_swap(self, expected_revision: int, new_state: dict) -> bool:
        if self.state["revision"] != expected_revision:
            return False
        self.state = copy.deepcopy(new_state)
        return True


def dispatch_for(*, opportunity_id: str, fact_id: str, plan_time: datetime) -> dict:
    profile = complete_profile()
    item = opportunity()
    item["opportunity_id"] = opportunity_id
    fact = {
        "schema_version": "0.1",
        "fact_id": fact_id,
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": item["project_name"],
        "source_url": f"https://www.ccgp.gov.cn/example/queue-worker/{fact_id}",
    }
    today = build_today_actions(
        profile=profile,
        opportunities=[item],
        evidence_facts_by_opportunity={opportunity_id: [fact]},
    )
    return build_today_actions_agnes_dispatch(
        profile_id=profile["profile_id"],
        today_actions=today,
        now=plan_time,
    )


def valid_output(model_input: dict) -> dict:
    return {
        "schema_version": "0.1",
        "opportunity_id": model_input["opportunity_id"],
        "action_type": "PREPARE_BID",
        "reason_codes": ["FORMAL_TENDER"],
        "risk_codes": ["COVERAGE_PARTIAL"],
        "supporting_fact_ids": [model_input["grounded_facts"][0]["fact_id"]],
        "supporting_profile_paths": [],
        "requires_human_confirmation": True,
    }


class TodayActionsQueueWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queue = MemoryAgnesDispatchQueue()
        self.leases = MemoryLeaseStore()
        self.results = MemoryAgnesTaskResultStore()

    def test_ready_task_is_removed_from_queue(self) -> None:
        dispatch = dispatch_for(
            opportunity_id="opp_11111111-1111-1111-1111-111111111111",
            fact_id="fact_ready",
            plan_time=NOW - timedelta(seconds=20),
        )
        queue_today_actions_dispatch(self.queue, dispatch, enqueued_at=NOW - timedelta(seconds=20))
        result = execute_next_queued_today_actions_task(
            queue=self.queue,
            lease_store=self.leases,
            result_store=self.results,
            worker_id="worker-a",
            now=NOW,
            model_call=valid_output,
            clock=lambda: NOW + timedelta(seconds=1),
        )
        self.assertEqual(result.status, "READY")
        self.assertEqual(self.queue.list_pending(limit=10), [])

    def test_provider_error_stays_queued_for_retry(self) -> None:
        dispatch = dispatch_for(
            opportunity_id="opp_22222222-2222-2222-2222-222222222222",
            fact_id="fact_retry",
            plan_time=NOW - timedelta(seconds=20),
        )
        queue_today_actions_dispatch(self.queue, dispatch, enqueued_at=NOW - timedelta(seconds=20))

        def fail(_: dict) -> dict:
            error = RuntimeError("temporary")
            error.error_class = "HTTP_5XX"
            raise error

        result = execute_next_queued_today_actions_task(
            queue=self.queue,
            lease_store=self.leases,
            result_store=self.results,
            worker_id="worker-a",
            now=NOW,
            model_call=fail,
            clock=lambda: NOW + timedelta(seconds=1),
        )
        self.assertEqual(result.status, "PROVIDER_ERROR")
        self.assertEqual(result.error_code, "HTTP_5XX")
        self.assertEqual(len(self.queue.list_pending(limit=10)), 1)

    def test_future_high_priority_does_not_block_due_lower_priority(self) -> None:
        future = dispatch_for(
            opportunity_id="opp_33333333-3333-3333-3333-333333333333",
            fact_id="fact_future",
            plan_time=NOW + timedelta(minutes=10),
        )
        due = dispatch_for(
            opportunity_id="opp_44444444-4444-4444-4444-444444444444",
            fact_id="fact_due",
            plan_time=NOW - timedelta(seconds=20),
        )
        # Make future task higher priority than the due one; due filtering must still win.
        future["agnes_dispatch_plan"]["items"][0]["priority"] = 0
        due["agnes_dispatch_plan"]["items"][0]["priority"] = 5
        queue_today_actions_dispatch(self.queue, future, enqueued_at=NOW - timedelta(minutes=1))
        queue_today_actions_dispatch(self.queue, due, enqueued_at=NOW - timedelta(minutes=1))

        calls: list[str] = []

        def call(model_input: dict) -> dict:
            calls.append(model_input["opportunity_id"])
            return valid_output(model_input)

        result = execute_next_queued_today_actions_task(
            queue=self.queue,
            lease_store=self.leases,
            result_store=self.results,
            worker_id="worker-a",
            now=NOW,
            model_call=call,
            clock=lambda: NOW + timedelta(seconds=1),
        )
        self.assertEqual(result.status, "READY")
        self.assertEqual(calls, ["opp_44444444-4444-4444-4444-444444444444"])
        remaining = self.queue.list_pending(limit=10)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["opportunity_id"], "opp_33333333-3333-3333-3333-333333333333")

    def test_no_due_task_returns_retry_time_without_provider_call(self) -> None:
        dispatch = dispatch_for(
            opportunity_id="opp_55555555-5555-5555-5555-555555555555",
            fact_id="fact_future_only",
            plan_time=NOW + timedelta(minutes=5),
        )
        queue_today_actions_dispatch(self.queue, dispatch, enqueued_at=NOW)
        calls: list[dict] = []
        result = execute_next_queued_today_actions_task(
            queue=self.queue,
            lease_store=self.leases,
            result_store=self.results,
            worker_id="worker-a",
            now=NOW,
            model_call=lambda payload: calls.append(payload) or valid_output(payload),
        )
        self.assertEqual(result.status, "NOT_CLAIMED")
        self.assertEqual(result.error_code, "QUEUE_NO_DUE_TASK")
        self.assertIsNotNone(result.retry_after)
        self.assertEqual(calls, [])

    def test_terminal_replay_is_removed_without_second_model_call(self) -> None:
        dispatch = dispatch_for(
            opportunity_id="opp_66666666-6666-6666-6666-666666666666",
            fact_id="fact_terminal",
            plan_time=NOW - timedelta(seconds=20),
        )
        queue_today_actions_dispatch(self.queue, dispatch, enqueued_at=NOW - timedelta(seconds=20))
        calls: list[dict] = []
        first = execute_next_queued_today_actions_task(
            queue=self.queue,
            lease_store=self.leases,
            result_store=self.results,
            worker_id="worker-a",
            now=NOW,
            model_call=lambda payload: calls.append(payload) or valid_output(payload),
            clock=lambda: NOW + timedelta(seconds=1),
        )
        self.assertEqual(first.status, "READY")
        self.assertEqual(len(calls), 1)

        # Simulate a stale/replayed queue row after a terminal result already exists.
        queue_today_actions_dispatch(self.queue, dispatch, enqueued_at=NOW + timedelta(seconds=10))
        second = execute_next_queued_today_actions_task(
            queue=self.queue,
            lease_store=self.leases,
            result_store=self.results,
            worker_id="worker-a",
            now=NOW + timedelta(seconds=20),
            model_call=lambda payload: calls.append(payload) or valid_output(payload),
            clock=lambda: NOW + timedelta(seconds=21),
        )
        self.assertEqual(second.status, "ALREADY_COMPLETED")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.queue.list_pending(limit=10), [])


if __name__ == "__main__":
    unittest.main()
