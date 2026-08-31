from __future__ import annotations

import unittest
from unittest.mock import patch

from tools.medical_pilot.benchmark_agnes_taxonomy import (
    TaxonomyBenchmarkError,
    aggregate,
    build_user_prompt,
    call_model,
    load_manifest,
    run,
    score_case,
    validate_output,
)
from tools.medical_pilot.product_classifier import taxonomy_ids


class AgnesTaxonomyBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest()

    def test_all_expected_taxonomy_ids_exist_in_controlled_registry(self) -> None:
        allowed = taxonomy_ids()
        for case in self.manifest["cases"]:
            for expected_set in case["acceptable_label_sets"]:
                for label in expected_set:
                    self.assertIn(label, allowed, msg=case["case_id"])

    def test_prompt_contains_only_controlled_output_shape(self) -> None:
        prompt = build_user_prompt(self.manifest["cases"][0])
        self.assertIn('"taxonomy_ids"', prompt)
        self.assertIn('"needs_more_detail"', prompt)
        self.assertNotIn('"explanation"', prompt)

    def test_unknown_taxonomy_id_fails_contract(self) -> None:
        case = self.manifest["cases"][0]
        errors = validate_output(
            case,
            {
                "case_id": case["case_id"],
                "taxonomy_ids": ["MADE_UP_ID"],
                "needs_more_detail": False,
            },
        )
        self.assertTrue(any("unknown id" in error for error in errors))

    def test_extra_free_text_field_fails_contract(self) -> None:
        case = self.manifest["cases"][0]
        errors = validate_output(
            case,
            {
                "case_id": case["case_id"],
                "taxonomy_ids": ["LAB_CHEMILUMINESCENCE_ANALYZER"],
                "needs_more_detail": False,
                "explanation": "not allowed",
            },
        )
        self.assertTrue(any("exact no-free-text contract" in error for error in errors))

    def test_abstention_case_requires_empty_labels_and_more_detail(self) -> None:
        case = next(item for item in self.manifest["cases"] if item["case_id"] == "generic_medical_equipment")
        row = score_case(
            case,
            {
                "case_id": case["case_id"],
                "taxonomy_ids": [],
                "needs_more_detail": True,
            },
        )
        self.assertTrue(row["acceptable_label_set"])
        self.assertTrue(row["safe_abstention"])

        unsafe = score_case(
            case,
            {
                "case_id": case["case_id"],
                "taxonomy_ids": ["LAB_RESEARCH_INSTRUMENT"],
                "needs_more_detail": False,
            },
        )
        self.assertFalse(unsafe["acceptable_label_set"])
        self.assertFalse(unsafe["safe_abstention"])

    def test_perfect_synthetic_outputs_pass_all_gates(self) -> None:
        scored = []
        for case in self.manifest["cases"]:
            output = {
                "case_id": case["case_id"],
                "taxonomy_ids": case["acceptable_label_sets"][0],
                "needs_more_detail": case["needs_more_detail"],
            }
            scored.append(score_case(case, output))
        result = aggregate(self.manifest, scored, failures=0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["metrics"]["unknown_taxonomy_id_rate"], 0.0)
        self.assertEqual(result["metrics"]["abstention_safety_accuracy"], 1.0)

    def test_direct_provider_call_requires_explicit_global_lease_and_never_opens_network(self) -> None:
        with patch("tools.medical_pilot.benchmark_agnes_taxonomy.urllib.request.urlopen") as urlopen:
            with self.assertRaises(TaxonomyBenchmarkError) as context:
                call_model(
                    api_key="fake-key",
                    base_url="https://apihub.agnes-ai.com/v1",
                    model="agnes-2.5-flash",
                    prompt="{}",
                )
        self.assertIn("GLOBAL_LEASE", str(context.exception))
        urlopen.assert_not_called()

    def test_legacy_taxonomy_run_execution_is_disabled(self) -> None:
        with self.assertRaises(TaxonomyBenchmarkError) as context:
            run(
                self.manifest,
                api_key="fake-key",
                base_url="https://apihub.agnes-ai.com/v1",
                model="agnes-2.5-flash",
                rpm=12,
            )
        self.assertIn("AGNES_BENCHMARK_SUITE", str(context.exception))


if __name__ == "__main__":
    unittest.main()
