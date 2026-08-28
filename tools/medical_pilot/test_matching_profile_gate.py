from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.matching_profile_gate import evaluate_matching_profile
from tools.medical_pilot.test_opportunity_match_gate import TAXONOMY_ID, complete_profile


class MatchingProfileGateTests(unittest.TestCase):
    def test_complete_taxonomy_ready_profile_remains_personalized_ready(self) -> None:
        result = evaluate_matching_profile(complete_profile())
        self.assertEqual(result.computed_status, "SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION")
        self.assertTrue(result.personalized_recommendation_allowed)
        self.assertTrue(result.candidate_opportunity_allowed)
        self.assertEqual(result.profile_completeness, 100)

    def test_missing_taxonomy_ids_turns_apparently_complete_profile_back_into_interview(self) -> None:
        profile = complete_profile()
        profile["product_capabilities"][0]["taxonomy_ids"] = []
        result = evaluate_matching_profile(profile)
        self.assertEqual(result.computed_status, "INCOMPLETE")
        self.assertEqual(result.recommendation_mode, "PROFILE_INTERVIEW_REQUIRED")
        self.assertFalse(result.candidate_opportunity_allowed)
        self.assertFalse(result.personalized_recommendation_allowed)
        self.assertLessEqual(result.profile_completeness, 60)
        self.assertTrue(any(item.code == "PRODUCT_TAXONOMY_IDS_MISSING" for item in result.missing_conditions))
        self.assertIsNotNone(result.next_question)
        self.assertIn("标准产品分类", result.next_question or "")

    def test_unknown_taxonomy_id_is_not_treated_as_profile_complete(self) -> None:
        profile = complete_profile()
        profile["product_capabilities"][0]["taxonomy_ids"] = ["NOT_A_REAL_TAXONOMY_ID"]
        result = evaluate_matching_profile(profile)
        self.assertEqual(result.computed_status, "INCOMPLETE")
        self.assertFalse(result.candidate_opportunity_allowed)
        self.assertTrue(any(item.code == "PRODUCT_TAXONOMY_ID_UNKNOWN" for item in result.missing_conditions))

    def test_base_interview_missing_condition_keeps_priority_over_taxonomy_question(self) -> None:
        profile = complete_profile()
        profile["company_name"] = ""
        profile["product_capabilities"][0]["taxonomy_ids"] = []
        result = evaluate_matching_profile(profile)
        self.assertEqual(result.computed_status, "INCOMPLETE")
        self.assertGreaterEqual(len(result.missing_conditions), 2)
        self.assertEqual(result.missing_conditions[0].code, "COMPANY_NAME_MISSING")
        self.assertIn("公司", result.next_question or "")

    def test_valid_taxonomy_id_does_not_replace_human_readable_fields(self) -> None:
        profile = complete_profile()
        item = copy.deepcopy(profile["product_capabilities"][0])
        self.assertEqual(item["taxonomy_ids"], [TAXONOMY_ID])
        self.assertEqual(item["category"], "IVD")
        self.assertEqual(item["subcategory"], TAXONOMY_ID)


if __name__ == "__main__":
    unittest.main()
