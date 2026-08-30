from __future__ import annotations

import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions import build_today_actions
from tools.medical_pilot.today_actions_dispatch import build_today_actions_agnes_dispatch


def fact_for(item: dict) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": "fact_11111111-2222-3333-4444-555555555555",
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": item["project_name"],
        "source_url": "https://www.ccgp.gov.cn/example/today-actions-dispatch",
    }


class TodayActionsDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = complete_profile()
        self.item = opportunity()
        self.fact = fact_for(self.item)
        self.now = datetime(2026, 8, 29, 8, 5, tzinfo=ZoneInfo("Asia/Shanghai"))

    def test_only_grounded_final_card_requests_enter_shared_dispatch(self) -> None:
        today = build_today_actions(
            profile=self.profile,
            opportunities=[self.item],
            evidence_facts_by_opportunity={self.item["opportunity_id"]: [self.fact]},
        )
        result = build_today_actions_agnes_dispatch(
            profile_id=self.profile["profile_id"],
            today_actions=today,
            now=self.now,
        )
        self.assertEqual(result["model_request_count"], 1)
        self.assertEqual(len(result["task_payloads"]), 1)
        task_id = result["task_payloads"][0]["task_id"]
        self.assertEqual(result["agnes_dispatch_plan"]["items"][0]["task_id"], task_id)
        self.assertEqual(result["agnes_dispatch_plan"]["max_request_starts_per_minute"], 12)
        self.assertTrue(result["agnes_dispatch_plan"]["requires_persistent_global_lease"])
        self.assertEqual(result["task_payloads"][0]["model_input"]["opportunity_id"], self.item["opportunity_id"])

    def test_completed_card_produces_no_new_model_dispatch(self) -> None:
        model_output = {
            "schema_version": "0.1",
            "opportunity_id": self.item["opportunity_id"],
            "action_type": "PREPARE_BID",
            "reason_codes": ["FORMAL_TENDER"],
            "risk_codes": ["COVERAGE_PARTIAL"],
            "supporting_fact_ids": [self.fact["fact_id"]],
            "supporting_profile_paths": [],
            "requires_human_confirmation": True,
        }
        today = build_today_actions(
            profile=self.profile,
            opportunities=[self.item],
            evidence_facts_by_opportunity={self.item["opportunity_id"]: [self.fact]},
            model_outputs_by_opportunity={self.item["opportunity_id"]: model_output},
        )
        result = build_today_actions_agnes_dispatch(
            profile_id=self.profile["profile_id"],
            today_actions=today,
            now=self.now,
        )
        self.assertEqual(result["model_request_count"], 0)
        self.assertEqual(result["task_payloads"], [])
        self.assertEqual(result["agnes_dispatch_plan"]["items"], [])

    def test_dispatch_rejects_request_not_belonging_to_final_card(self) -> None:
        today = build_today_actions(
            profile=self.profile,
            opportunities=[self.item],
            evidence_facts_by_opportunity={self.item["opportunity_id"]: [self.fact]},
        )
        bad = copy.deepcopy(today)
        bad["model_requests"][0]["opportunity_id"] = "opp_aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"
        bad["model_requests"][0]["model_input"]["opportunity_id"] = "opp_aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"
        with self.assertRaises(ValueError):
            build_today_actions_agnes_dispatch(
                profile_id=self.profile["profile_id"],
                today_actions=bad,
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
