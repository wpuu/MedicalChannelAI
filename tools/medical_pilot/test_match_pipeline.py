from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.match_pipeline import evaluate_match_pipeline
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


class MatchPipelineTests(unittest.TestCase):
    def test_deterministic_validated_product_labels_can_match(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "DETERMINISTIC"
        item["product_label_validation_status"] = "VALIDATED"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "MATCHED_PERSONALIZED")
        self.assertTrue(result.model_explanation_allowed)

    def test_human_confirmed_validated_product_labels_can_match(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "HUMAN_CONFIRMED"
        item["product_label_validation_status"] = "VALIDATED"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "MATCHED_PERSONALIZED")

    def test_controlled_model_classification_benchmark_pending_cannot_drive_match(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "CONTROLLED_MODEL_CLASSIFICATION"
        item["product_label_validation_status"] = "BENCHMARK_PENDING"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertFalse(result.model_explanation_allowed)
        self.assertIn("opportunity.product_label_validation_status", result.required_next_facts)

    def test_controlled_model_classification_only_works_after_explicit_validation(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "CONTROLLED_MODEL_CLASSIFICATION"
        item["product_label_validation_status"] = "VALIDATED"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "MATCHED_PERSONALIZED")

    def test_missing_product_provenance_is_not_silently_assumed(self) -> None:
        item = opportunity()
        item.pop("product_label_provenance", None)
        item["product_label_validation_status"] = "VALIDATED"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertFalse(result.model_explanation_allowed)
        self.assertIn("opportunity.product_label_provenance", result.required_next_facts)

    def test_incomplete_profile_still_blocks_before_model(self) -> None:
        profile = complete_profile()
        profile["product_capabilities"] = []
        item = opportunity()
        item["product_label_provenance"] = "DETERMINISTIC"
        item["product_label_validation_status"] = "VALIDATED"
        result = evaluate_match_pipeline(profile, item)
        self.assertEqual(result.status, "PROFILE_BLOCKED")
        self.assertFalse(result.model_explanation_allowed)


if __name__ == "__main__":
    unittest.main()
