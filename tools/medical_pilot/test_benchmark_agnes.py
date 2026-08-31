from __future__ import annotations

import unittest
from unittest.mock import patch

from tools.medical_pilot.benchmark_agnes import (
    BenchmarkError,
    aggregate_scores,
    build_user_prompt,
    call_chat_completion,
    extract_json_object,
    load_manifest,
    run_benchmark,
    score_case,
)


class AgnesBenchmarkHarnessTests(unittest.TestCase):
    def test_manifest_has_enough_diverse_cases_and_no_free_text_output_contract(self) -> None:
        manifest = load_manifest()
        self.assertGreaterEqual(len(manifest["cases"]), 10)
        self.assertTrue(manifest["output_contract"]["no_free_text"])
        self.assertEqual(manifest["model_target"], "agnes-2.5-flash")

    def test_user_prompt_contains_locked_input_and_enums_but_not_expected_answer(self) -> None:
        manifest = load_manifest()
        case = manifest["cases"][0]
        prompt = build_user_prompt(manifest, case)
        self.assertIn("locked_input", prompt)
        self.assertIn(case["case_id"], prompt)
        self.assertIn("allowed_segments", prompt)
        self.assertNotIn("acceptable_segments", prompt)
        self.assertNotIn("required_risk_flags", prompt)

    def test_valid_json_response_scores_without_network(self) -> None:
        manifest = load_manifest()
        case = next(item for item in manifest["cases"] if item["case_id"] == "teda_dr")
        output = extract_json_object(
            '{"case_id":"teda_dr","segment":"MEDICAL_IMAGING","item_detail_status":"ATTACHMENT_REQUIRED","needs_more_source_data":true,"risk_flags":["ATTACHMENT_NOT_PARSED","NO_BRAND_EVIDENCE","NO_SUPPLIER_EVIDENCE"]}'
        )
        scored = score_case(manifest, case, output)
        self.assertTrue(scored["valid_contract"])
        self.assertTrue(scored["segment_correct"])
        self.assertTrue(scored["item_detail_status_correct"])
        self.assertTrue(scored["needs_more_source_data_correct"])
        self.assertEqual(scored["required_risk_flag_recall"], 1.0)

    def test_free_text_or_unknown_enum_breaks_contract(self) -> None:
        manifest = load_manifest()
        case = manifest["cases"][0]
        output = {
            "case_id": case["case_id"],
            "segment": "MADE_UP_SEGMENT",
            "item_detail_status": "ATTACHMENT_REQUIRED",
            "needs_more_source_data": True,
            "risk_flags": [],
            "explanation": "this free text is forbidden",
        }
        scored = score_case(manifest, case, output)
        self.assertFalse(scored["valid_contract"])
        self.assertTrue(scored["validation_errors"])

    def test_perfect_fixture_scores_pass_gates(self) -> None:
        manifest = load_manifest()
        scored = []
        for case in manifest["cases"]:
            expected = case["expected"]
            output = {
                "case_id": case["case_id"],
                "segment": expected["acceptable_segments"][0],
                "item_detail_status": expected["item_detail_status"],
                "needs_more_source_data": expected["needs_more_source_data"],
                "risk_flags": list(expected["required_risk_flags"]),
            }
            scored.append(score_case(manifest, case, output))
        aggregate = aggregate_scores(manifest, scored, failures=0)
        self.assertTrue(aggregate["passed"])
        self.assertEqual(aggregate["metrics"]["segment_accuracy"], 1.0)
        self.assertEqual(aggregate["metrics"]["api_or_json_failure_rate"], 0.0)

    def test_direct_provider_call_requires_explicit_global_lease_and_never_opens_network(self) -> None:
        with patch("tools.medical_pilot.benchmark_agnes.urllib.request.urlopen") as urlopen:
            with self.assertRaises(BenchmarkError) as context:
                call_chat_completion(
                    base_url="https://apihub.agnes-ai.com/v1",
                    api_key="fake-key",
                    model="agnes-2.5-flash",
                    user_prompt="{}",
                )
        self.assertIn("GLOBAL_LEASE", str(context.exception))
        urlopen.assert_not_called()

    def test_provider_retry_under_one_lease_is_rejected_before_network(self) -> None:
        with patch("tools.medical_pilot.benchmark_agnes.urllib.request.urlopen") as urlopen:
            with self.assertRaises(BenchmarkError) as context:
                call_chat_completion(
                    base_url="https://apihub.agnes-ai.com/v1",
                    api_key="fake-key",
                    model="agnes-2.5-flash",
                    user_prompt="{}",
                    retries=1,
                    global_lease_granted=True,
                )
        self.assertIn("NEW_GLOBAL_LEASE", str(context.exception))
        urlopen.assert_not_called()

    def test_legacy_run_benchmark_execution_is_disabled(self) -> None:
        with self.assertRaises(BenchmarkError) as context:
            run_benchmark(
                load_manifest(),
                base_url="https://apihub.agnes-ai.com/v1",
                api_key="fake-key",
                model="agnes-2.5-flash",
                rpm=12,
            )
        self.assertIn("AGNES_BENCHMARK_SUITE", str(context.exception))


if __name__ == "__main__":
    unittest.main()
