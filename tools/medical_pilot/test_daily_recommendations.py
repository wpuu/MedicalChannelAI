from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.daily_recommendations import build_daily_recommendation_plan
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


WIDE_TAXONOMY_IDS = [
    "LAB_BIOCHEMISTRY_ANALYZER",
    "LAB_CHEMILUMINESCENCE_ANALYZER",
    "LAB_COAGULATION_ANALYZER",
    "LAB_HEMATOLOGY_ANALYZER",
    "LAB_URINALYSIS_ANALYZER",
    "LAB_PCR_QPCR",
    "LAB_FLOW_CYTOMETER",
    "LAB_AUTOMATION_LINE",
    "LAB_SAMPLE_PREPROCESSING",
    "LAB_REAGENT_IMMUNOASSAY",
]


class DailyRecommendationTests(unittest.TestCase):
    def test_final_home_cards_and_model_calls_are_bounded_to_five(self) -> None:
        profile = complete_profile()
        items = []
        for index in range(8):
            item = opportunity()
            item["opportunity_id"] = f"opp_{index + 1:08x}-1111-1111-1111-111111111111"
            item["budget"] = {"amount": str(1000000 + index * 1000000) + ".00", "currency": "CNY"}
            items.append(item)
        result = build_daily_recommendation_plan(profile, items)
        self.assertEqual(result["matched_count"], 8)
        self.assertEqual(result["model_candidate_count"], 5)
        self.assertEqual(result["final_action_card_count"], 5)
        self.assertEqual(len(result["final_action_cards"]), 5)
        self.assertTrue(all(card["model_explanation_allowed"] for card in result["final_action_cards"]))
        self.assertEqual(
            result["model_candidate_ids"],
            [card["opportunity_id"] for card in result["final_action_cards"]],
        )

    def test_rejected_and_needs_more_facts_do_not_enter_model_candidates(self) -> None:
        profile = complete_profile()
        matched = opportunity()
        rejected = copy.deepcopy(matched)
        rejected["opportunity_id"] = "opp_aaaaaaaa-1111-1111-1111-111111111111"
        rejected["region"] = {"province": "河北省", "city": "唐山市", "district": "路北区"}
        needs = copy.deepcopy(matched)
        needs["opportunity_id"] = "opp_bbbbbbbb-1111-1111-1111-111111111111"
        needs["product_labels"] = []
        result = build_daily_recommendation_plan(profile, [matched, rejected, needs])
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["needs_more_facts_count"], 1)
        self.assertEqual(result["rejected_or_blocked_count"], 1)
        self.assertEqual(result["model_candidate_ids"], [matched["opportunity_id"]])

    def test_wide_profile_reduces_model_candidate_budget_without_rejecting_profile(self) -> None:
        profile = complete_profile()
        profile["operating_regions"] = [
            {"province": "天津市", "city": "天津市", "scope_mode": "SELECTED_DISTRICTS", "districts": [f"区{i}" for i in range(16)]}
        ]
        profile["product_capabilities"] = [
            {
                "category": "医疗产品",
                "subcategory": f"产品{i}",
                "taxonomy_ids": [taxonomy_id],
                "brands": [],
                "capability_type": "DIRECT_UNCONFIRMED",
                "notes": None,
            }
            for i, taxonomy_id in enumerate(WIDE_TAXONOMY_IDS)
        ]
        result = build_daily_recommendation_plan(profile, [])
        self.assertEqual(result["query_plan"]["scope_class"], "VERY_WIDE")
        self.assertEqual(result["query_plan"]["profile_scope"]["scope_cells"], 160)
        self.assertEqual(result["query_plan"]["budgets"]["max_model_candidates"], 5)
        self.assertEqual(result["input_candidate_count"], 0)

    def test_orchestrator_never_requests_live_crawl_for_interactive_daily(self) -> None:
        result = build_daily_recommendation_plan(complete_profile(), [])
        self.assertEqual(result["query_plan"]["budgets"]["max_live_source_requests"], 0)
        self.assertEqual(result["query_plan"]["acquisition_strategy"], "SHARED_FACT_INDEX_NOT_PER_PROFILE_CRAWL")


if __name__ == "__main__":
    unittest.main()
