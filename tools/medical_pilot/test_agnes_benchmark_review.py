from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.agnes_benchmark_review import (
    AgnesBenchmarkReviewError,
    review_result,
)
from tools.medical_pilot.agnes_benchmark_suite import (
    EXPECTED_GENERAL_CASES,
    EXPECTED_TAXONOMY_CASES,
    EXPECTED_TOTAL_CASES,
    TARGET_CLASSIFIER_ID,
    _input_hashes,
)
from tools.medical_pilot.classifier_admission import load_classifier_admissions


def valid_result() -> dict:
    hashes = _input_hashes()
    return {
        "schema_version": "0.1",
        "status": "PASS",
        "model": "agnes-2.5-flash",
        "total_case_count": EXPECTED_TOTAL_CASES,
        "completed_case_count": EXPECTED_TOTAL_CASES,
        "provider_start_count": EXPECTED_TOTAL_CASES,
        "general_manifest_sha256": hashes["general_manifest_sha256"],
        "taxonomy_manifest_sha256": hashes["taxonomy_manifest_sha256"],
        "classifier_registry_sha256_before": hashes["classifier_registry_sha256"],
        "classifier_registry_sha256_after": hashes["classifier_registry_sha256"],
        "benchmark_inputs_modified_during_run": False,
        "every_provider_start_requires_global_lease": True,
        "business_queue_quiescent_required": True,
        "maintenance_window_confirmed": True,
        "provider_retries_per_case": 0,
        "general": {
            "aggregate": {"passed": True},
            "cases": [{"case_id": f"g-{index}"} for index in range(EXPECTED_GENERAL_CASES)],
            "failures": [],
        },
        "taxonomy": {
            "aggregate": {"passed": True},
            "cases": [{"case_id": f"t-{index}"} for index in range(EXPECTED_TAXONOMY_CASES)],
            "failures": [],
        },
        "target_classifier_id": TARGET_CLASSIFIER_ID,
        "classifier_registry_modified": False,
        "automatic_classifier_admission_allowed": False,
        "automatic_classifier_admission_performed": False,
        "admission_recommendation": "ELIGIBLE_FOR_MANUAL_ADMISSION_REVIEW",
    }


def write_result(path: Path, payload: dict, *, mode: int = 0o600) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.chmod(path, mode)


class AgnesBenchmarkReviewTests(unittest.TestCase):
    def test_valid_pass_is_only_eligible_for_manual_registry_change_and_does_not_mutate(self) -> None:
        before = load_classifier_admissions()[TARGET_CLASSIFIER_ID]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            write_result(path, valid_result())
            reviewed = review_result(path)
        after = load_classifier_admissions()[TARGET_CLASSIFIER_ID]

        self.assertEqual(reviewed["status"], "ELIGIBLE_FOR_MANUAL_REGISTRY_CHANGE")
        self.assertEqual(reviewed["benchmark_case_count"], 28)
        self.assertTrue(reviewed["manifest_hashes_match_current_checkout"])
        self.assertTrue(reviewed["registry_hash_matches_benchmark"])
        self.assertFalse(reviewed["registry_change_performed"])
        self.assertFalse(reviewed["automatic_classifier_admission_allowed"])
        self.assertEqual(reviewed["next_action"], "OWNER_REVIEW_REQUIRED_BEFORE_EXPLICIT_REGISTRY_COMMIT")
        self.assertEqual(before, after)
        self.assertEqual(after.admission_status, "BENCHMARK_PENDING")
        self.assertFalse(after.can_drive_matching)

    def test_manifest_hash_mismatch_blocks_review(self) -> None:
        payload = valid_result()
        payload["taxonomy_manifest_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            write_result(path, payload)
            with self.assertRaises(AgnesBenchmarkReviewError) as context:
                review_result(path)
        self.assertEqual(context.exception.code, "BENCHMARK_TAXONOMY_MANIFEST_CHANGED_SINCE_RUN")

    def test_registry_hash_mismatch_blocks_review(self) -> None:
        payload = valid_result()
        payload["classifier_registry_sha256_before"] = "f" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            write_result(path, payload)
            with self.assertRaises(AgnesBenchmarkReviewError) as context:
                review_result(path)
        self.assertEqual(context.exception.code, "BENCHMARK_REGISTRY_CHANGED_SINCE_RUN")

    def test_non_private_result_mode_blocks_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            write_result(path, valid_result(), mode=0o644)
            with self.assertRaises(AgnesBenchmarkReviewError) as context:
                review_result(path)
        self.assertEqual(context.exception.code, "BENCHMARK_RESULT_MODE_NOT_0600")

    def test_failed_or_auto_admitting_result_is_never_eligible(self) -> None:
        payload = valid_result()
        payload["status"] = "FAIL"
        payload["automatic_classifier_admission_allowed"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            write_result(path, payload)
            with self.assertRaises(AgnesBenchmarkReviewError) as context:
                review_result(path)
        self.assertEqual(context.exception.code, "BENCHMARK_RESULT_NOT_PASS")


if __name__ == "__main__":
    unittest.main()
