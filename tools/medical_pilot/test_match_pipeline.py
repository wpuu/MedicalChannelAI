from __future__ import annotations

import unittest

from tools.medical_pilot.match_pipeline import evaluate_match_pipeline
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


class MatchPipelineTests(unittest.TestCase):
    def test_deterministic_validated_product_labels_can_match(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "DETERMINISTIC"
        item["product_label_validation_status"] = "VALIDATED"
        item["product_classifier_id"] = "deterministic-product-taxonomy-v0.1"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "MATCHED_PERSONALIZED")
        self.assertTrue(result.model_explanation_allowed)

    def test_human_confirmed_validated_product_labels_can_match(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "HUMAN_CONFIRMED"
        item["product_label_validation_status"] = "VALIDATED"
        item["product_classifier_id"] = "human-confirmed-product-taxonomy-v0.1"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "MATCHED_PERSONALIZED")

    def test_controlled_model_benchmark_pending_cannot_drive_match(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "CONTROLLED_MODEL_CLASSIFICATION"
        item["product_label_validation_status"] = "BENCHMARK_PENDING"
        item["product_classifier_id"] = "agnes-2.5-flash-product-taxonomy-v0.1"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertFalse(result.model_explanation_allowed)
        self.assertIn("opportunity.product_classifier_id", result.required_next_facts)

    def test_controlled_model_cannot_bypass_global_pending_by_self_declaring_validated(self) -> None:
        item = opportunity()
        item["product_label_provenance"] = "CONTROLLED_MODEL_CLASSIFICATION"
        item["product_label_validation_status"] = "VALIDATED"
        item["product_classifier_id"] = "agnes-2.5-flash-product-taxonomy-v0.1"
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertFalse(result.model_explanation_allowed)
        self.assertTrue(any(reason.code == "PRODUCT_CLASSIFIER_NOT_ADMITTED" for reason in result.reasons))

    def test_missing_classifier_id_is_not_silently_assumed(self) -> None:
        item = opportunity()
        item.pop("product_classifier_id", None)
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertIn("opportunity.product_classifier_id", result.required_next_facts)

    def test_missing_product_provenance_is_not_silently_assumed(self) -> None:
        item = opportunity()
        item.pop("product_label_provenance", None)
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertFalse(result.model_explanation_allowed)
        self.assertIn("opportunity.product_label_provenance", result.required_next_facts)

    def test_unknown_opportunity_taxonomy_id_requires_enrichment(self) -> None:
        item = opportunity()
        item["product_labels"] = ["NOT_A_REAL_TAXONOMY_ID"]
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertFalse(result.model_explanation_allowed)
        self.assertIn("opportunity.product_labels", result.required_next_facts)

    def test_profile_missing_taxonomy_id_blocks_candidates(self) -> None:
        profile = complete_profile()
        profile["product_capabilities"][0]["taxonomy_ids"] = []
        result = evaluate_match_pipeline(profile, opportunity())
        self.assertEqual(result.status, "PROFILE_BLOCKED")
        self.assertFalse(result.candidate_opportunity_allowed)
        self.assertFalse(result.model_explanation_allowed)

    def test_profile_unknown_taxonomy_id_blocks_candidates(self) -> None:
        profile = complete_profile()
        profile["product_capabilities"][0]["taxonomy_ids"] = ["UNKNOWN_TAXONOMY_ID"]
        result = evaluate_match_pipeline(profile, opportunity())
        self.assertEqual(result.status, "PROFILE_BLOCKED")
        self.assertTrue(any(reason.code == "PRODUCT_TAXONOMY_ID_UNKNOWN" for reason in result.reasons))

    def test_customer_type_without_provenance_cannot_drive_match(self) -> None:
        item = opportunity()
        item.pop("customer_type_provenance", None)
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertFalse(result.model_explanation_allowed)
        self.assertIn("opportunity.customer_type_provenance", result.required_next_facts)

    def test_official_customer_type_requires_institution_evidence_id(self) -> None:
        item = opportunity()
        item["institution_evidence_id"] = None
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "NEEDS_MORE_FACTS")
        self.assertIn("opportunity.institution_evidence_id", result.required_next_facts)

    def test_human_confirmed_customer_type_can_match_without_institution_registry_id(self) -> None:
        item = opportunity()
        item["customer_type_provenance"] = "HUMAN_CONFIRMED"
        item["customer_type_validation_status"] = "VALIDATED"
        item["institution_evidence_id"] = None
        result = evaluate_match_pipeline(complete_profile(), item)
        self.assertEqual(result.status, "MATCHED_PERSONALIZED")

    def test_incomplete_profile_still_blocks_before_model(self) -> None:
        profile = complete_profile()
        profile["product_capabilities"] = []
        result = evaluate_match_pipeline(profile, opportunity())
        self.assertEqual(result.status, "PROFILE_BLOCKED")
        self.assertFalse(result.model_explanation_allowed)


if __name__ == "__main__":
    unittest.main()
