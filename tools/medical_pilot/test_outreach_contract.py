from __future__ import annotations

from datetime import datetime, timezone
import unittest

from .outreach_contract import (
    OutreachContractError,
    build_outreach_model_input,
    render_outreach_draft,
    validate_outreach_model_output,
)
from .test_model_decision_contract import verified_fact
from .test_opportunity_match_gate import complete_profile, opportunity


class OutreachContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = complete_profile()
        self.profile["hospital_relationships"] = [
            {
                "hospital_name": "天津医科大学总医院",
                "department": "检验科",
                "relationship_strength": "STRONG",
                "owner": "销售A",
                "confirmed_by_customer": True,
                "last_confirmed_at": "2026-08-29T10:00:00+08:00",
            }
        ]
        self.item = opportunity()
        self.facts = [
            verified_fact("fact_11111111-1111-1111-1111-111111111111", "buyer_name", "天津医科大学总医院"),
            verified_fact("fact_22222222-2222-2222-2222-222222222222", "project_name", "化学发光设备采购项目"),
            verified_fact("fact_33333333-3333-3333-3333-333333333333", "budget_cny", "5730000.00"),
        ]

    def valid_output(self, model_input) -> dict:
        return {
            "schema_version": "0.1",
            "opportunity_id": self.item["opportunity_id"],
            "strategy_code": model_input.allowed_strategy_codes[0],
            "question_codes": [model_input.allowed_question_codes[0], model_input.allowed_question_codes[1]],
            "positioning_code": "RELATIONSHIP_CONTEXT",
            "supporting_fact_ids": [item["fact_id"] for item in model_input.grounded_facts],
            "supporting_profile_paths": ["hospital_relationship"],
        }

    def test_requires_verified_buyer_and_project_name(self) -> None:
        with self.assertRaises(OutreachContractError) as context:
            build_outreach_model_input(
                profile=self.profile,
                opportunity=self.item,
                evidence_facts=self.facts[1:],
            )
        self.assertEqual(context.exception.code, "OUTREACH_CORE_FACTS_MISSING")

    def test_model_cannot_reference_unknown_fact_or_profile_path(self) -> None:
        model_input = build_outreach_model_input(
            profile=self.profile,
            opportunity=self.item,
            evidence_facts=self.facts,
        )
        output = self.valid_output(model_input)
        output["supporting_fact_ids"].append("fact_ffffffff-ffff-ffff-ffff-ffffffffffff")
        with self.assertRaises(OutreachContractError) as context:
            validate_outreach_model_output(output, model_input)
        self.assertEqual(context.exception.code, "OUTREACH_UNGROUNDED_FACT_REFERENCE")

        output = self.valid_output(model_input)
        output["supporting_profile_paths"].append("secret_customer_note")
        with self.assertRaises(OutreachContractError) as context:
            validate_outreach_model_output(output, model_input)
        self.assertEqual(context.exception.code, "OUTREACH_PROFILE_PATH_NOT_ALLOWED")

    def test_server_renderer_uses_grounded_core_facts(self) -> None:
        model_input = build_outreach_model_input(
            profile=self.profile,
            opportunity=self.item,
            evidence_facts=self.facts,
        )
        validated = validate_outreach_model_output(self.valid_output(model_input), model_input)
        rendered = render_outreach_draft(
            validated,
            model_input,
            generated_at=datetime(2026, 8, 30, 7, 30, tzinfo=timezone.utc),
        )
        self.assertIn("天津医科大学总医院", rendered["draft"])
        self.assertIn("化学发光设备采购项目", rendered["draft"])
        self.assertIn("内部沟通话术草稿", rendered["draft"])
        self.assertTrue(rendered["requires_human_confirmation"])
        self.assertIn("不代表中标概率或采购承诺", rendered["draft"])


if __name__ == "__main__":
    unittest.main()
