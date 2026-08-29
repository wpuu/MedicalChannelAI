from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tools.medical_pilot.agnes_global_lease import initial_lease_state
from tools.medical_pilot.agnes_task_result import MemoryAgnesTaskResultStore
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


def fact_for(item: dict, *, suffix: str = "base", field_name: str = "project_name", field_value: str | None = None) -> dict:
    value = field_value if field_value is not None else item["project_name"]
    return {
        "schema_version": "0.1",
        "fact_id": f"fact_{suffix}",
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": field_name,
        "field_value": value,
        "source_url": f"https://www.ccgp.gov.cn/example/today-actions-worker/{suffix}",
    }


def build_dispatch(now: datetime, *, facts: list[dict] | None = None) -> tuple[dict, dict, list[dict]]:
    profile = complete_profile()
    item = opportunity()
    rows = facts or [fact_for(item)]
    today = build_today_actions(
        profile=profile,
        opportunities=[item],
        evidence_facts_by_opportunity={item["opportunity_id"]: rows},
    )
    dispatch = build_today_actions_agnes_dispatch(
        profile_id=profile["profile_id"],
        today_actions=today,
        now=now,
    )
    return dispatch, item, rows


class TodayActionsWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan_time = datetime(2026, 8, 30, 8, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.run_time = self.plan_time + timedelta(seconds=10)
        self.finish_time = self.run_time + timedelta(seconds=2)
        self.dispatch, self.item, self.facts = build_dispatch(self.plan_time)
        self.store = MemoryStore(initial_lease_state(now=self.plan_time))
        self.result_store = MemoryAgnesTaskResultStore()

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

    def execute(self, *, dispatch: dict | None = None, model_call=None, now: datetime | None = None):
        return execute_next_today_actions_task(
            dispatch or self.dispatch,
            store=self.store,
            result_store=self.result_store,
            worker_id="worker-a",
            now=now or self.run_time,
            clock=lambda: self.finish_time,
            model_call=model_call or self.valid_output,
        )

    def test_valid_grounded_output_becomes_ready_and_releases_lease(self) -> None:
        result = self.execute()
        self.assertEqual(result.status, "READY")
        self.assertTrue(result.provider_start_allowed)
        self.assertTrue(result.lease_released)
        self.assertFalse(result.terminal_result_reused)
        self.assertIsNotNone(result.validated_output)
        self.assertEqual(result.rendered_decision["action"], "准备投标评估")
        self.assertEqual(self.store.load()["active_leases"], [])
        self.assertEqual(len(self.store.load()["recent_start_timestamps"]), 1)
        self.assertIsNotNone(self.result_store.get(result.task_id))

    def test_ungrounded_model_reference_is_rejected_and_persisted_terminal(self) -> None:
        def bad_output(model_input: dict) -> dict:
            result = self.valid_output(model_input)
            result["supporting_fact_ids"] = ["fact_not_supplied"]
            return result

        result = self.execute(model_call=bad_output)
        self.assertEqual(result.status, "MODEL_OUTPUT_REJECTED")
        self.assertEqual(result.error_code, "UNGROUNDED_FACT_REFERENCE")
        self.assertTrue(result.lease_released)
        self.assertIsNone(result.rendered_decision)
        terminal = self.result_store.get(result.task_id)
        self.assertEqual(terminal["status"], "MODEL_OUTPUT_REJECTED")

    def test_provider_error_releases_lease_but_is_not_terminal(self) -> None:
        def failing_call(_: dict) -> dict:
            raise RuntimeError("simulated provider failure")

        result = self.execute(model_call=failing_call)
        self.assertEqual(result.status, "PROVIDER_ERROR")
        self.assertEqual(result.error_code, "MODEL_CALL_FAILED")
        self.assertTrue(result.lease_released)
        self.assertIsNone(self.result_store.get(result.task_id))
        self.assertEqual(self.store.load()["active_leases"], [])

    def test_tampered_serialized_model_input_is_blocked_before_lease_or_provider(self) -> None:
        bad = copy.deepcopy(self.dispatch)
        bad["task_payloads"][0]["model_input"]["allowed_action_types"].append("MAKE_UP_ACTION")
        calls: list[dict] = []

        def should_not_call(model_input: dict) -> dict:
            calls.append(model_input)
            return self.valid_output(model_input)

        with self.assertRaises(ValueError):
            self.execute(dispatch=bad, model_call=should_not_call)
        self.assertEqual(calls, [])
        self.assertEqual(self.store.load()["recent_start_timestamps"], [])
        self.assertEqual(self.store.load()["active_leases"], [])

    def test_tampered_declared_hash_is_blocked_before_lease_or_provider(self) -> None:
        bad = copy.deepcopy(self.dispatch)
        bad["task_payloads"][0]["model_input_sha256"] = "0" * 64
        calls: list[dict] = []
        with self.assertRaises(ValueError):
            self.execute(dispatch=bad, model_call=lambda payload: calls.append(payload) or self.valid_output(payload))
        self.assertEqual(calls, [])
        self.assertEqual(self.store.load()["recent_start_timestamps"], [])

    def test_not_before_prevents_provider_call_and_does_not_create_lease(self) -> None:
        calls: list[dict] = []
        result = self.execute(
            now=self.plan_time,
            model_call=lambda payload: calls.append(payload) or self.valid_output(payload),
        )
        self.assertEqual(result.status, "NOT_CLAIMED")
        self.assertFalse(result.provider_start_allowed)
        self.assertIsNone(result.lease_released)
        self.assertEqual(calls, [])
        self.assertEqual(self.store.load()["active_leases"], [])
        self.assertEqual(self.store.load()["recent_start_timestamps"], [])

    def test_same_dispatch_is_model_called_exactly_once_and_second_run_consumes_no_start(self) -> None:
        calls: list[dict] = []

        def counted(model_input: dict) -> dict:
            calls.append(model_input)
            return self.valid_output(model_input)

        first = self.execute(model_call=counted)
        starts_after_first = list(self.store.load()["recent_start_timestamps"])
        second = self.execute(model_call=counted, now=self.run_time + timedelta(seconds=20))
        self.assertEqual(first.status, "READY")
        self.assertEqual(second.status, "ALREADY_COMPLETED")
        self.assertTrue(second.terminal_result_reused)
        self.assertFalse(second.provider_start_allowed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.load()["recent_start_timestamps"], starts_after_first)

    def test_new_verified_fact_changes_task_hash_and_can_run_as_new_task(self) -> None:
        first_calls: list[dict] = []
        first = self.execute(model_call=lambda payload: first_calls.append(payload) or self.valid_output(payload))
        self.assertEqual(first.status, "READY")

        extra = fact_for(
            self.item,
            suffix="deadline",
            field_name="bid_deadline",
            field_value="2026-09-10T09:00:00+08:00",
        )
        changed_dispatch, _, _ = build_dispatch(self.plan_time, facts=[self.facts[0], extra])
        self.assertNotEqual(
            self.dispatch["task_payloads"][0]["task_id"],
            changed_dispatch["task_payloads"][0]["task_id"],
        )
        self.assertNotEqual(
            self.dispatch["task_payloads"][0]["model_input_sha256"],
            changed_dispatch["task_payloads"][0]["model_input_sha256"],
        )

        second_calls: list[dict] = []
        second_time = self.run_time + timedelta(seconds=20)
        second_finish = second_time + timedelta(seconds=2)
        result = execute_next_today_actions_task(
            changed_dispatch,
            store=self.store,
            result_store=self.result_store,
            worker_id="worker-a",
            now=second_time,
            clock=lambda: second_finish,
            model_call=lambda payload: second_calls.append(payload) or self.valid_output(payload),
        )
        self.assertEqual(result.status, "READY")
        self.assertEqual(len(second_calls), 1)
        self.assertEqual(len(self.store.load()["recent_start_timestamps"]), 2)


if __name__ == "__main__":
    unittest.main()
