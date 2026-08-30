from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.medical_pilot.agnes_task_result import MemoryAgnesTaskResultStore, build_terminal_result
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions_service import build_today_actions_service_cycle


NOW = datetime(2026, 8, 30, 8, 10, tzinfo=ZoneInfo("Asia/Shanghai"))


def fact(item: dict, *, suffix: str = "project", field_name: str = "project_name", field_value: str | None = None) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": f"fact_{suffix}",
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": field_name,
        "field_value": field_value if field_value is not None else item["project_name"],
        "source_url": f"https://www.ccgp.gov.cn/example/service/{suffix}",
    }


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


class TodayActionsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = complete_profile()
        self.item = opportunity()
        self.base_fact = fact(self.item)
        self.evidence = {self.item["opportunity_id"]: [self.base_fact]}
        self.results = MemoryAgnesTaskResultStore()

    def cycle(self, *, evidence=None):
        return build_today_actions_service_cycle(
            profile=self.profile,
            opportunities=[self.item],
            evidence_facts_by_opportunity=evidence or self.evidence,
            result_store=self.results,
            now=NOW,
        )

    def terminal_from_cycle(self, cycle, *, status: str, error_code: str | None = None) -> dict:
        payload = cycle.internal_dispatch["task_payloads"][0]
        model_input = payload["model_input"]
        output = valid_output(model_input) if status == "READY" else None
        rendered = (
            {
                "action": "准备投标评估",
                "reasons": ["项目已进入正式采购阶段"],
                "risks": ["当前区域公开数据覆盖仍为 PARTIAL"],
                "supporting_fact_ids": output["supporting_fact_ids"],
                "supporting_profile_paths": [],
                "requires_human_confirmation": True,
            }
            if output is not None else None
        )
        return build_terminal_result(
            task_id=payload["task_id"],
            opportunity_id=payload["opportunity_id"],
            model_input_sha256=payload["model_input_sha256"],
            status=status,
            completed_at=NOW,
            validated_output=output,
            rendered_decision=rendered,
            error_code=error_code,
        )

    def test_pending_model_work_is_internal_and_public_view_has_no_model_input(self) -> None:
        cycle = self.cycle()
        public = cycle.public_response()
        self.assertNotIn("model_requests", public)
        self.assertEqual(public["model_request_count"], 1)
        self.assertEqual(public["cards"][0]["model_decision_status"], "AWAITING_MODEL")
        self.assertEqual(cycle.internal_dispatch["model_request_count"], 1)
        self.assertIn("model_input", cycle.internal_dispatch["task_payloads"][0])

    def test_ready_terminal_is_reused_and_no_new_dispatch_is_created(self) -> None:
        first = self.cycle()
        terminal = self.terminal_from_cycle(first, status="READY")
        self.assertTrue(self.results.put_if_absent(terminal["task_id"], terminal))

        second = self.cycle()
        public = second.public_response()
        self.assertEqual(second.reused_ready_count, 1)
        self.assertEqual(second.reused_rejected_count, 0)
        self.assertEqual(public["model_request_count"], 0)
        self.assertEqual(public["cards"][0]["model_decision_status"], "READY")
        self.assertEqual(public["cards"][0]["decision"]["action"], "准备投标评估")
        self.assertEqual(second.internal_dispatch["model_request_count"], 0)

    def test_rejected_terminal_remains_rejected_and_is_not_redispatched(self) -> None:
        first = self.cycle()
        terminal = self.terminal_from_cycle(
            first,
            status="MODEL_OUTPUT_REJECTED",
            error_code="UNGROUNDED_FACT_REFERENCE",
        )
        self.assertTrue(self.results.put_if_absent(terminal["task_id"], terminal))

        second = self.cycle()
        public = second.public_response()
        self.assertEqual(second.reused_ready_count, 0)
        self.assertEqual(second.reused_rejected_count, 1)
        self.assertEqual(public["model_request_count"], 0)
        self.assertEqual(public["cards"][0]["model_decision_status"], "MODEL_OUTPUT_REJECTED")
        self.assertEqual(public["cards"][0]["model_block_reason"], "UNGROUNDED_FACT_REFERENCE")
        self.assertEqual(second.internal_dispatch["model_request_count"], 0)

    def test_new_verified_evidence_changes_hash_and_old_terminal_is_not_reused(self) -> None:
        first = self.cycle()
        old_payload = first.internal_dispatch["task_payloads"][0]
        terminal = self.terminal_from_cycle(first, status="READY")
        self.results.put_if_absent(terminal["task_id"], terminal)

        extra = fact(
            self.item,
            suffix="deadline",
            field_name="bid_deadline",
            field_value="2026-09-10T09:00:00+08:00",
        )
        changed = {self.item["opportunity_id"]: [self.base_fact, extra]}
        second = self.cycle(evidence=changed)
        new_payload = second.internal_dispatch["task_payloads"][0]
        self.assertEqual(second.reused_ready_count, 0)
        self.assertNotEqual(old_payload["task_id"], new_payload["task_id"])
        self.assertNotEqual(old_payload["model_input_sha256"], new_payload["model_input_sha256"])
        self.assertEqual(second.public_response()["model_request_count"], 1)
        self.assertEqual(second.public_response()["cards"][0]["model_decision_status"], "AWAITING_MODEL")


if __name__ == "__main__":
    unittest.main()
