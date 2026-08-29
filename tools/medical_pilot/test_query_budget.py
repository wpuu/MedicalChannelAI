from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.query_budget import build_query_execution_plan
from tools.medical_pilot.test_opportunity_match_gate import complete_profile


class QueryBudgetTests(unittest.TestCase):
    def test_normal_interactive_profile_uses_shared_index_and_no_live_crawl(self) -> None:
        plan = build_query_execution_plan(complete_profile())
        self.assertEqual(plan["scope_class"], "NORMAL")
        self.assertEqual(plan["acquisition_strategy"], "SHARED_FACT_INDEX_NOT_PER_PROFILE_CRAWL")
        self.assertEqual(plan["budgets"]["max_live_source_requests"], 0)
        self.assertEqual(plan["budgets"]["max_model_candidates"], 10)
        self.assertEqual(plan["budgets"]["max_final_action_cards"], 5)
        self.assertIn("MODEL_CONTEXT_IS_BOUNDED_PER_OPPORTUNITY", plan["warnings"])

    def test_wide_profile_is_batched_not_rejected_or_cartesian_crawled(self) -> None:
        profile = complete_profile()
        profile["operating_regions"] = [
            {
                "province": "天津市",
                "city": "天津市",
                "scope_mode": "SELECTED_DISTRICTS",
                "districts": ["和平区", "河西区", "南开区", "河东区"],
            }
        ]
        profile["product_capabilities"][0]["taxonomy_ids"] = [f"TEST_TAXONOMY_{i}" for i in range(10)]
        plan = build_query_execution_plan(profile)
        self.assertEqual(plan["profile_scope"]["scope_cells"], 40)
        self.assertEqual(plan["scope_class"], "WIDE")
        self.assertEqual(plan["budgets"]["max_live_source_requests"], 0)
        self.assertEqual(plan["budgets"]["max_model_candidates"], 8)
        self.assertIn("WIDE_PROFILE_SCOPE_USE_SUMMARY_THEN_DRILL_DOWN", plan["warnings"])

    def test_very_wide_profile_tightens_deep_and_model_top_n(self) -> None:
        profile = complete_profile()
        profile["operating_regions"] = [
            {
                "province": "天津市",
                "city": "天津市",
                "scope_mode": "SELECTED_DISTRICTS",
                "districts": [f"区{i}" for i in range(16)],
            }
        ]
        profile["product_capabilities"][0]["taxonomy_ids"] = [f"TEST_TAXONOMY_{i}" for i in range(10)]
        plan = build_query_execution_plan(profile)
        self.assertEqual(plan["profile_scope"]["scope_cells"], 160)
        self.assertEqual(plan["scope_class"], "VERY_WIDE")
        self.assertEqual(plan["budgets"]["max_deep_enrichment_candidates"], 15)
        self.assertEqual(plan["budgets"]["max_model_candidates"], 5)
        self.assertEqual(plan["budgets"]["max_final_action_cards"], 5)
        self.assertIn("VERY_WIDE_PROFILE_SCOPE_STRICT_TOP_N_AND_BATCHING_REQUIRED", plan["warnings"])

    def test_single_opportunity_deep_dive_allows_only_small_bounded_live_fetch(self) -> None:
        plan = build_query_execution_plan(complete_profile(), mode="SINGLE_OPPORTUNITY_DEEP_DIVE")
        self.assertEqual(plan["budgets"]["max_deep_enrichment_candidates"], 1)
        self.assertEqual(plan["budgets"]["max_model_candidates"], 1)
        self.assertEqual(plan["budgets"]["max_live_source_requests"], 3)
        self.assertEqual(plan["budgets"]["max_final_action_cards"], 1)

    def test_scheduled_refresh_is_source_driven_and_has_no_model_stage_budget(self) -> None:
        profile = copy.deepcopy(complete_profile())
        plan = build_query_execution_plan(profile, mode="SCHEDULED_INDEX_REFRESH")
        self.assertEqual(plan["acquisition_strategy"], "SHARED_FACT_INDEX_NOT_PER_PROFILE_CRAWL")
        self.assertEqual(plan["budgets"]["max_model_candidates"], 0)
        self.assertEqual(plan["budgets"]["max_live_source_requests"], 250)
        self.assertIn("INDEX_REFRESH_IS_SOURCE_DRIVEN_NOT_CUSTOMER_CARTESIAN_QUERY", plan["warnings"])

    def test_unknown_mode_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_query_execution_plan(complete_profile(), mode="UNBOUNDED")


if __name__ == "__main__":
    unittest.main()
