from __future__ import annotations

import unittest

from tools.medical_pilot.taxonomy_corpus_audit import audit_corpus


class TaxonomyCorpusAuditTests(unittest.TestCase):
    def test_all_50_verified_opportunity_fixtures_enter_the_audit(self) -> None:
        result = audit_corpus()
        self.assertEqual(result["corpus_case_count"], 50)
        self.assertEqual(result["deterministically_classified_count"] + result["unresolved_count"], 50)
        self.assertEqual(len(result["rows"]), 50)
        ids = [row["case_id"] for row in result["rows"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_generic_equipment_title_remains_unresolved_instead_of_being_guessed(self) -> None:
        result = audit_corpus()
        rows = {row["case_id"]: row for row in result["rows"]}
        row = rows["tianjin_cancer_hospital_equipment_award_20260803"]
        self.assertFalse(row["deterministically_classified"])
        self.assertTrue(row["needs_controlled_model_or_human"])
        self.assertEqual(row["taxonomy_ids"], [])

    def test_high_specificity_imaging_case_is_deterministically_classified(self) -> None:
        result = audit_corpus()
        rows = {row["case_id"]: row for row in result["rows"]}
        row = rows["tj_tianjin_hospital_spectct_terminated_20260824"]
        self.assertTrue(row["deterministically_classified"])
        self.assertIn("MEDICAL_IMAGING_SPECT_CT", row["taxonomy_ids"])
        self.assertFalse(row["needs_controlled_model_or_human"])

    def test_flow_cytometer_award_uses_stable_taxonomy(self) -> None:
        result = audit_corpus()
        rows = {row["case_id"]: row for row in result["rows"]}
        row = rows["tmu_analytical_flow_cytometer_award_20260623"]
        self.assertIn("LAB_FLOW_CYTOMETER", row["taxonomy_ids"])
        self.assertTrue(row["supporting_fact_ids"])

    def test_classified_rows_require_grounding_fact_ids(self) -> None:
        result = audit_corpus()
        for row in result["rows"]:
            if row["deterministically_classified"]:
                self.assertTrue(row["supporting_fact_ids"], row["case_id"])
            else:
                self.assertEqual(row["supporting_fact_ids"], [], row["case_id"])

    def test_audit_does_not_claim_coverage_equals_accuracy(self) -> None:
        result = audit_corpus()
        self.assertEqual(result["important_interpretation"], "COVERAGE_RATE_IS_NOT_MODEL_ACCURACY")


if __name__ == "__main__":
    unittest.main()
