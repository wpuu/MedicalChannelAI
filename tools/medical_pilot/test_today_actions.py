from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions import build_today_actions


def verified_fact(opportunity_id: str, fact_id: str, value: str = "化学发光设备采购项目") -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": fact_id,
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": value,
        "source_url": f"https://www.ccgp.gov.cn/example/{opportunity_id}",
    }


class TodayActionsTests(unittest.TestCase):
    def test_top_five_cards_are_the_only_model_requests(self) -> None:
        profile = complete_profile()
        items = []
        evidence: dict[str, list[dict]] = {}
        for index in range(8):
            item = opportunity()
            item["opportunity_id"] = f"opp_{index + 1:08x}-1111-1111-1111-111111111111"
            item["budget"] = {"amount": str(1000000 + index * 1000000) + ".00", "currency": "CNY"}
            items.append(item)
            evidence[item["opportunity_id"]] = [
                verified_fact(
                    item["opportunity_id"],
                    f"fact_{index + 1:08x}-1111-1111-1111-111111111111",
                )
            ]

        result = build_today_actions(
            profile=profile,
            opportunities=items,
            evidence_facts_by_opportunity=evidence,
        )
        self.assertEqual(result["matched_count"], 8)
        self.assertEqual(result["card_count"], 5)
        self.assertEqual(result["model_request_count"], 5)
        self.assertEqual(
            [item["opportunity_id"] for item in result["model_requests"]],
            [card["opportunity_id"] for card in result["cards"]],
        )
        self.assertTrue(all(card["model_decision_status"] == "AWAITING_MODEL" for card in result["cards"]))

    def test_customer_private_relationship_and_product_context_are_separate(self) -> None:
        profile = complete_profile()
        profile["hospital_relationships"] = [
            {
                "hospital_name": "天津医科大学总医院",
                "department": "检验科",
                "relationship_strength": "STRONG",
                "owner": "销售A",
                "confirmed_by_customer": True,
                "last_confirmed_at": "2026-08-28T20:00:00+08:00",
            }
        ]
        item = opportunity()
        fact = verified_fact(
            item["opportunity_id"],
            "fact_99999999-1111-1111-1111-999999999999",
        )
        result = build_today_actions(
            profile=profile,
            opportunities=[item],
            evidence_facts_by_opportunity={item["opportunity_id"]: [fact]},
        )
        context = result["cards"][0]["customer_context"]
        self.assertEqual(context["context_type"], "CUSTOMER_PRIVATE_FACTS")
        self.assertEqual(context["hospital_relationship"]["owner"], "销售A")
        self.assertEqual(context["hospital_relationship"]["department"], "检验科")
        self.assertEqual(context["matching_product_capabilities"][0]["subcategory"], "化学发光分析仪")
        self.assertNotIn("hospital_relationship", result["cards"][0]["facts"])

    def test_no_grounded_fact_blocks_model_without_removing_action_card(self) -> None:
        item = opportunity()
        result = build_today_actions(
            profile=complete_profile(),
            opportunities=[item],
            evidence_facts_by_opportunity={},
        )
        self.assertEqual(result["card_count"], 1)
        self.assertEqual(result["model_request_count"], 0)
        self.assertEqual(result["cards"][0]["model_decision_status"], "BLOCKED_GROUNDING")
        self.assertEqual(result["cards"][0]["model_block_reason"], "NO_GROUNDED_FACTS")
        self.assertIsNone(result["cards"][0]["decision"])

    def test_unverified_evidence_is_not_exposed_as_verified_source(self) -> None:
        item = opportunity()
        fact = verified_fact(
            item["opportunity_id"],
            "fact_aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa",
        )
        bad = copy.deepcopy(fact)
        bad["fact_id"] = "fact_bbbbbbbb-1111-1111-1111-bbbbbbbbbbbb"
        bad["verification_status"] = "UNVERIFIED"
        bad["source_url"] = "https://example.invalid/unverified"
        result = build_today_actions(
            profile=complete_profile(),
            opportunities=[item],
            evidence_facts_by_opportunity={item["opportunity_id"]: [fact, bad]},
        )
        self.assertEqual(result["cards"][0]["evidence_source_urls"], [fact["source_url"]])

    def test_valid_grounded_model_output_is_rendered(self) -> None:
        item = opportunity()
        fact = verified_fact(
            item["opportunity_id"],
            "fact_cccccccc-1111-1111-1111-cccccccccccc",
        )
        output = {
            "schema_version": "0.1",
            "opportunity_id": item["opportunity_id"],
            "action_type": "PREPARE_BID",
            "reason_codes": ["FORMAL_TENDER", "PRODUCT_CAPABILITY_DIRECT"],
            "risk_codes": ["COVERAGE_PARTIAL"],
            "supporting_fact_ids": [fact["fact_id"]],
            "supporting_profile_paths": ["product_capabilities"],
            "requires_human_confirmation": True,
        }
        result = build_today_actions(
            profile=complete_profile(),
            opportunities=[item],
            evidence_facts_by_opportunity={item["opportunity_id"]: [fact]},
            model_outputs_by_opportunity={item["opportunity_id"]: output},
        )
        card = result["cards"][0]
        self.assertEqual(card["model_decision_status"], "READY")
        self.assertEqual(card["decision"]["action"], "准备投标评估")
        self.assertEqual(result["model_request_count"], 0)

    def test_ungrounded_model_output_is_rejected_and_never_rendered(self) -> None:
        item = opportunity()
        fact = verified_fact(
            item["opportunity_id"],
            "fact_dddddddd-1111-1111-1111-dddddddddddd",
        )
        output = {
            "schema_version": "0.1",
            "opportunity_id": item["opportunity_id"],
            "action_type": "PREPARE_BID",
            "reason_codes": ["FORMAL_TENDER"],
            "risk_codes": [],
            "supporting_fact_ids": ["fact_eeeeeeee-1111-1111-1111-eeeeeeeeeeee"],
            "supporting_profile_paths": [],
            "requires_human_confirmation": True,
        }
        result = build_today_actions(
            profile=complete_profile(),
            opportunities=[item],
            evidence_facts_by_opportunity={item["opportunity_id"]: [fact]},
            model_outputs_by_opportunity={item["opportunity_id"]: output},
        )
        card = result["cards"][0]
        self.assertEqual(card["model_decision_status"], "MODEL_OUTPUT_REJECTED")
        self.assertEqual(card["model_block_reason"], "UNGROUNDED_FACT_REFERENCE")
        self.assertIsNone(card["decision"])


if __name__ == "__main__":
    unittest.main()
