from __future__ import annotations

import unittest

from tools.medical_pilot.match_pipeline import evaluate_match_pipeline
from tools.medical_pilot.model_decision_contract import (
    ModelDecisionError,
    build_model_decision_input,
    render_model_decision,
    validate_model_decision,
)
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


def verified_fact(fact_id: str, field_name: str, field_value: str) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": fact_id,
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": field_name,
        "field_value": field_value,
        "source_url": "https://www.ccgp.gov.cn/example",
    }


class ModelDecisionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = complete_profile()
        self.profile["hospital_relationships"] = [
            {
                "hospital_name": "天津测试医院",
                "department": "检验科",
                "relationship_strength": "STRONG",
                "owner": "销售A",
                "confirmed_by_customer": True,
                "last_confirmed_at": "2026-08-28T20:00:00+08:00",
            }
        ]
        self.item = opportunity()
        self.item["hospital_name"] = "天津测试医院"
        self.item["product_label_provenance"] = "DETERMINISTIC"
        self.item["product_label_validation_status"] = "VALIDATED"
        self.item["product_classifier_id"] = "deterministic-product-taxonomy-v0.1"
        self.match = evaluate_match_pipeline(self.profile, self.item)
        self.facts = [
            verified_fact("fact_11111111-1111-1111-1111-111111111111", "project_name", "检验设备采购项目"),
            verified_fact("fact_22222222-2222-2222-2222-222222222222", "budget_cny", "5730000.00"),
        ]

    def test_builder_only_includes_verified_non_model_facts(self) -> None:
        facts = list(self.facts)
        facts.append({
            "fact_id": "fact_33333333-3333-3333-3333-333333333333",
            "fact_type": "OFFICIAL_PUBLIC_FACT",
            "verification_status": "UNVERIFIED",
            "model_generated": False,
            "field_name": "brand",
            "field_value": "不应进入",
            "source_url": "https://example.invalid",
        })
        model_input = build_model_decision_input(
            profile=self.profile,
            opportunity=self.item,
            match_result=self.match,
            evidence_facts=facts,
        )
        ids = {fact.fact_id for fact in model_input.grounded_facts}
        self.assertEqual(ids, {
            "fact_11111111-1111-1111-1111-111111111111",
            "fact_22222222-2222-2222-2222-222222222222",
        })
        self.assertEqual(model_input.grounded_fact_source_count, 2)
        self.assertEqual(model_input.grounded_fact_omitted_count, 0)
        self.assertEqual(model_input.confirmed_profile_context["hospital_relationship"]["relationship_strength"], "STRONG")

    def test_builder_bounds_large_fact_sets_and_reports_omissions(self) -> None:
        facts = [
            verified_fact(
                f"fact_{i:08x}-1111-1111-1111-{i:012x}",
                "other_detail",
                f"官方事实{i}",
            )
            for i in range(30)
        ]
        facts.append(
            verified_fact(
                "fact_aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa",
                "project_name",
                "应优先保留的项目名称",
            )
        )
        model_input = build_model_decision_input(
            profile=self.profile,
            opportunity=self.item,
            match_result=self.match,
            evidence_facts=facts,
            max_grounded_facts=5,
            max_grounded_fact_chars=12000,
        )
        self.assertEqual(model_input.grounded_fact_source_count, 31)
        self.assertEqual(len(model_input.grounded_facts), 5)
        self.assertEqual(model_input.grounded_fact_omitted_count, 26)
        self.assertEqual(model_input.grounded_facts[0].field_name, "project_name")
        payload = model_input.as_dict()
        self.assertEqual(payload["input_budget"]["included_fact_count"], 5)
        self.assertEqual(payload["input_budget"]["omitted_fact_count"], 26)

    def test_builder_never_truncates_a_fact_to_force_it_into_context(self) -> None:
        huge = verified_fact(
            "fact_bbbbbbbb-1111-1111-1111-bbbbbbbbbbbb",
            "project_name",
            "超" * 2000,
        )
        with self.assertRaises(ModelDecisionError) as context:
            build_model_decision_input(
                profile=self.profile,
                opportunity=self.item,
                match_result=self.match,
                evidence_facts=[huge],
                max_grounded_facts=5,
                max_grounded_fact_chars=100,
            )
        self.assertEqual(context.exception.code, "MODEL_FACT_BUDGET_NO_FIT")

    def test_invalid_model_fact_budget_fails_closed(self) -> None:
        with self.assertRaises(ModelDecisionError) as context:
            build_model_decision_input(
                profile=self.profile,
                opportunity=self.item,
                match_result=self.match,
                evidence_facts=self.facts,
                max_grounded_facts=0,
            )
        self.assertEqual(context.exception.code, "MODEL_FACT_BUDGET_INVALID")

    def test_model_cannot_reference_unknown_fact_id(self) -> None:
        model_input = build_model_decision_input(
            profile=self.profile,
            opportunity=self.item,
            match_result=self.match,
            evidence_facts=self.facts,
        )
        output = {
            "schema_version": "0.1",
            "opportunity_id": self.item["opportunity_id"],
            "action_type": "PREPARE_BID",
            "reason_codes": ["FORMAL_TENDER"],
            "risk_codes": ["COVERAGE_PARTIAL"],
            "supporting_fact_ids": ["fact_99999999-9999-9999-9999-999999999999"],
            "supporting_profile_paths": ["product_capabilities"],
            "requires_human_confirmation": True,
        }
        with self.assertRaises(ModelDecisionError) as context:
            validate_model_decision(output, model_input)
        self.assertEqual(context.exception.code, "UNGROUNDED_FACT_REFERENCE")

    def test_formal_tender_cannot_choose_early_stage_contact_action(self) -> None:
        model_input = build_model_decision_input(
            profile=self.profile,
            opportunity=self.item,
            match_result=self.match,
            evidence_facts=self.facts,
        )
        output = {
            "schema_version": "0.1",
            "opportunity_id": self.item["opportunity_id"],
            "action_type": "CONTACT_HOSPITAL",
            "reason_codes": ["FORMAL_TENDER"],
            "risk_codes": [],
            "supporting_fact_ids": [self.facts[0]["fact_id"]],
            "supporting_profile_paths": [],
            "requires_human_confirmation": True,
        }
        with self.assertRaises(ModelDecisionError) as context:
            validate_model_decision(output, model_input)
        self.assertEqual(context.exception.code, "ACTION_NOT_ALLOWED")

    def test_valid_output_renders_without_model_free_text(self) -> None:
        model_input = build_model_decision_input(
            profile=self.profile,
            opportunity=self.item,
            match_result=self.match,
            evidence_facts=self.facts,
        )
        output = {
            "schema_version": "0.1",
            "opportunity_id": self.item["opportunity_id"],
            "action_type": "PREPARE_BID",
            "reason_codes": ["FORMAL_TENDER", "PRODUCT_CAPABILITY_DIRECT"],
            "risk_codes": ["COVERAGE_PARTIAL"],
            "supporting_fact_ids": [self.facts[0]["fact_id"], self.facts[1]["fact_id"]],
            "supporting_profile_paths": ["product_capabilities", "profile_status"],
            "requires_human_confirmation": True,
        }
        validated = validate_model_decision(output, model_input)
        rendered = render_model_decision(validated)
        self.assertEqual(rendered["action"], "准备投标评估")
        self.assertIn("项目已进入正式采购阶段", rendered["reasons"])
        self.assertIn("当前区域公开数据覆盖仍为 PARTIAL", rendered["risks"])

    def test_builder_refuses_match_that_did_not_pass_gate(self) -> None:
        blocked_item = opportunity()
        blocked_item["verification_status"] = "UNVERIFIED"
        blocked_item["product_label_provenance"] = "DETERMINISTIC"
        blocked_item["product_label_validation_status"] = "VALIDATED"
        blocked_item["product_classifier_id"] = "deterministic-product-taxonomy-v0.1"
        blocked_match = evaluate_match_pipeline(self.profile, blocked_item)
        with self.assertRaises(ModelDecisionError) as context:
            build_model_decision_input(
                profile=self.profile,
                opportunity=blocked_item,
                match_result=blocked_match,
                evidence_facts=self.facts,
            )
        self.assertEqual(context.exception.code, "MODEL_NOT_ALLOWED")


if __name__ == "__main__":
    unittest.main()
