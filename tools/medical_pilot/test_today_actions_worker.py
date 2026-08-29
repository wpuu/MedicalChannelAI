from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tools.medical_pilot.agnes_global_lease import initial_lease_state
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions import build_today_actions
from tools.medical_pilot.today_actions_dispatch import build_today_actions_agnes_dispatch
from tools.medical_pilot.today_actions_worker import execute_next_today_actions_task


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


def fact_for(item: dict) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": "fact_11111111-2222-3333-4444-555555555555",
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": item["project_name"],
        "source_url": "https://www.ccgp.gov.cn/example/today-actions-worker",
    }


def build_dispatch(now: datetime) -> tuple[dict, dict, dict]:
    profile = complete_profile()
    item = opportunity()
    fact = fact_for(item)
    today = build_today_actions(
        profile=profile,
        opportunities=[item],
        evidence_facts_by_opportunity={item["opportunity_id"]: [fact]},
    )
    dispatch = build_today_actions_agnes_dispatch(
        profile_id=profile["profile_id"],
        today_actions=today,
        now=now,
    )
    return dispatch, item, fact


class TodayActionsWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan_time = datetime(2026, 8, 30, 8, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.run_time = self.plan_time + timedelta(seconds=10)
        self.finish_time = self.run_time + timedelta(seconds=2)
        self.dispatch, self.item, self.fact = build_dispatch(self.plan_time)
        self.store = MemoryStore(initial_lease_state(now=self.plan_time))

    def valid_output(self, model_input: dict) -> dict:
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

    def test_valid_grounded_output_becomes_ready_and_releases_lease(self) -> None:
        result = execute_next_today_actions_task(
            self.dispatch,
            store=self.store,
            worker_id="worker-a",
            now=self.run_time,
            clock=lambda: self.finish_time,
            model_call=self.valid_output,
        )
        self.assertEqual(result.status, "READY")
        self.assertTrue(result.provider_start_allowed)
        self.assertTrue(result.lease_released)
        self.assertIsNotNone(result.validated_output)
        self.assertEqual(result.rendered_decision["action"], "准备投标评估")
        self.assertEqual(self.store.load()["active_leases"], [])
        self.assertEqual(len(self.store.load()["recent_start_timestamps"]), 1)

    def test_ungrounded_model_reference_is_rejected_and_lease_is_released(self) -> None:
        def bad_output(model_input: dict) -> dict:
            result = self.valid_output(model_input)
            result["supporting_fact_ids"] = ["fact_not_supplied"]
            return result

        result = execute_next_today_actions_task(
            self.dispatch,
            store=self.store,
            worker_id="worker-a",
            now=self.run_time,
            clock=lambda: self.finish_time,
            model_call=bad_output,
        )
        self.assertEqual(result.status, "MODEL_OUTPUT_REJECTED")
        self.assertEqual(result.error_code, "UNGROUNDED_FACT_REFERENCE")
        self.assertTrue(result.lease_released)
        self.assertIsNone(result.rendered_decision)
        self.assertEqual(self.store.load()["active_leases"], [])

    def test_provider_error_still_releases_global_lease(self) -> None:
        def failing_call(_: dict) -> dict:
            raise RuntimeError("simulated provider failure")

        result = execute_next_today_actions_task(
            self.dispatch,
            store=self.store,
            worker_id="worker-a",
            now=self.run_time,
            clock=lambda: self.finish_time,
            model_call=failing_call,
        )
        self.assertEqual(result.status, "PROVIDER_ERROR")
        self.assertEqual(result.error_code, "MODEL_CALL_FAILED")
        self.assertTrue(result.lease_released)
        self.assertEqual(self.store.load()["active_leases"], [])

    def test_tampered_serialized_model_input_is_blocked_before_provider_call(self) -> None:
        bad = copy.deepcopy(self.dispatch)
        bad["task_payloads"][0]["model_input"]["allowed_action_types"].append("MAKE_UP_ACTION")
        calls: list[dict] = []

        def should_not_call(model_input: dict) -> dict:
            calls.append(model_input)
            return self.valid_output(model_input)

        result = execute_next_today_actions_task(
            bad,
            store=self.store,
            worker_id="worker-a",
            now=self.run_time,
            clock=lambda: self.finish_time,
            model_call=should_not_call,
        )
        self.assertEqual(result.status, "PAYLOAD_ERROR")
        self.assertEqual(result.error_code, "MODEL_INPUT_INVALID")
        self.assertEqual(calls, [])
        self.assertTrue(result.lease_released)

    def test_not_before_prevents_provider_call_and_does_not_create_lease(self) -> None:
        calls: list[dict] = []

        def should_not_call(model_input: dict) -> dict:
            calls.append(model_input)
            return self.valid_output(model_input)

        result = execute_next_today_actions_task(
            self.dispatch,
            store=self.store,
            worker_id="worker-a",
            now=self.plan_time,
            clock=lambda: self.plan_time,
            model_call=should_not_call,
        )
        self.assertEqual(result.status, "NOT_CLAIMED")
        self.assertFalse(result.provider_start_allowed)
        self.assertIsNone(result.lease_released)
        self.assertEqual(calls, [])
        self.assertEqual(self.store.load()["active_leases"], [])
        self.assertEqual(self.store.load()["recent_start_timestamps"], [])


if __name__ == "__main__":
    unittest.main()
