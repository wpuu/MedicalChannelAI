from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.agnes_benchmark_suite import (
    AgnesBenchmarkSuiteError,
    EXPECTED_TOTAL_CASES,
    TARGET_CLASSIFIER_ID,
    _write_private_result,
    dry_run_summary,
    run_suite,
)
from tools.medical_pilot.agnes_dispatch_queue import SQLiteAgnesDispatchQueue
from tools.medical_pilot.classifier_admission import load_classifier_admissions
from tools.medical_pilot.today_actions_dispatch import model_input_sha256


START = datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self) -> None:
        self.current = START
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


def seed_pending_business_task(db_path: Path) -> None:
    queue = SQLiteAgnesDispatchQueue(db_path)
    opportunity_id = "opp_pending_benchmark_guard"
    model_input = {"schema_version": "0.1", "opportunity_id": opportunity_id}
    input_hash = model_input_sha256(model_input)
    task_id = f"today|profile_guard|{opportunity_id}|{input_hash[:24]}"
    queue.enqueue_if_absent(
        {
            "schema_version": "0.1",
            "task_id": task_id,
            "source": "TODAY_ACTIONS",
            "profile_id": "profile_guard",
            "opportunity_id": opportunity_id,
            "model_input_sha256": input_hash,
            "model_input": model_input,
            "dispatch_item": {
                "task_id": task_id,
                "requires_global_lease": True,
            },
            "enqueued_at": START.isoformat(),
        }
    )


class AgnesBenchmarkSuiteTests(unittest.TestCase):
    def test_dry_run_freezes_12_plus_16_as_28_and_never_admits(self) -> None:
        result = dry_run_summary()
        self.assertEqual(result["status"], "DRY_RUN_NO_NETWORK")
        self.assertEqual(result["general_case_count"], 12)
        self.assertEqual(result["taxonomy_case_count"], 16)
        self.assertEqual(result["total_case_count"], 28)
        self.assertTrue(result["requires_shared_global_lease"])
        self.assertTrue(result["requires_quiescent_maintenance_window"])
        self.assertEqual(result["provider_retries_per_case"], 0)
        self.assertFalse(result["automatic_classifier_admission_allowed"])
        self.assertFalse(result["classifier_registry_modified"])
        self.assertFalse(result["network_called"])

    def test_execute_requires_explicit_maintenance_window_before_provider_start(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(AgnesBenchmarkSuiteError) as context:
                run_suite(
                    api_key="fake-key",
                    base_url="https://apihub.agnes-ai.com/v1",
                    lease_db_path=Path(temp_dir) / "lease.sqlite",
                    general_provider=lambda *args: calls.append("general") or "{}",
                    taxonomy_provider=lambda *args: calls.append("taxonomy") or "{}",
                )
        self.assertEqual(context.exception.code, "MAINTENANCE_WINDOW_CONFIRMATION_REQUIRED")
        self.assertEqual(calls, [])

    def test_pending_business_queue_blocks_benchmark_before_provider_start(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "lease.sqlite"
            seed_pending_business_task(db_path)
            with self.assertRaises(AgnesBenchmarkSuiteError) as context:
                run_suite(
                    api_key="fake-key",
                    base_url="https://apihub.agnes-ai.com/v1",
                    lease_db_path=db_path,
                    maintenance_window_confirmed=True,
                    general_provider=lambda *args: calls.append("general") or "{}",
                    taxonomy_provider=lambda *args: calls.append("taxonomy") or "{}",
                )
        self.assertEqual(context.exception.code, "BUSINESS_AGNES_QUEUE_NOT_QUIESCENT")
        self.assertEqual(calls, [])

    def test_perfect_28_case_suite_passes_with_global_spacing_and_registry_unchanged(self) -> None:
        clock = FakeClock()
        starts: list[datetime] = []
        observed_keys: list[str] = []
        fake_key = "benchmark-key-must-never-echo"

        def general_provider(manifest, case, api_key, base_url):
            starts.append(clock.now())
            observed_keys.append(api_key)
            expected = case["expected"]
            return json.dumps(
                {
                    "case_id": case["case_id"],
                    "segment": expected["acceptable_segments"][0],
                    "item_detail_status": expected["item_detail_status"],
                    "needs_more_source_data": expected["needs_more_source_data"],
                    "risk_flags": list(expected["required_risk_flags"]),
                },
                ensure_ascii=False,
            )

        def taxonomy_provider(case, api_key, base_url):
            starts.append(clock.now())
            observed_keys.append(api_key)
            return json.dumps(
                {
                    "case_id": case["case_id"],
                    "taxonomy_ids": case["acceptable_label_sets"][0],
                    "needs_more_detail": case["needs_more_detail"],
                },
                ensure_ascii=False,
            )

        before = load_classifier_admissions()[TARGET_CLASSIFIER_ID]
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_suite(
                api_key=fake_key,
                base_url="https://apihub.agnes-ai.com/v1",
                lease_db_path=Path(temp_dir) / "lease.sqlite",
                maintenance_window_confirmed=True,
                now_provider=clock.now,
                sleeper=clock.sleep,
                general_provider=general_provider,
                taxonomy_provider=taxonomy_provider,
            )
        after = load_classifier_admissions()[TARGET_CLASSIFIER_ID]

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["completed_case_count"], EXPECTED_TOTAL_CASES)
        self.assertEqual(result["provider_start_count"], EXPECTED_TOTAL_CASES)
        self.assertEqual(len(starts), EXPECTED_TOTAL_CASES)
        self.assertTrue(result["every_provider_start_requires_global_lease"])
        self.assertTrue(result["business_queue_quiescent_required"])
        self.assertTrue(result["maintenance_window_confirmed"])
        self.assertEqual(result["provider_retries_per_case"], 0)
        self.assertEqual(result["admission_recommendation"], "ELIGIBLE_FOR_MANUAL_ADMISSION_REVIEW")
        self.assertFalse(result["automatic_classifier_admission_allowed"])
        self.assertFalse(result["automatic_classifier_admission_performed"])
        self.assertFalse(result["classifier_registry_modified"])
        self.assertTrue(all(key == fake_key for key in observed_keys))
        self.assertNotIn(fake_key, json.dumps(result, ensure_ascii=False))
        self.assertEqual(before.admission_status, "BENCHMARK_PENDING")
        self.assertFalse(before.can_drive_matching)
        self.assertEqual(after, before)

        for previous, current in zip(starts, starts[1:]):
            self.assertGreaterEqual((current - previous).total_seconds(), 5.0)

    def test_one_bad_taxonomy_case_fails_and_keeps_manual_admission_blocked(self) -> None:
        clock = FakeClock()
        seen_taxonomy = 0

        def general_provider(manifest, case, api_key, base_url):
            expected = case["expected"]
            return json.dumps(
                {
                    "case_id": case["case_id"],
                    "segment": expected["acceptable_segments"][0],
                    "item_detail_status": expected["item_detail_status"],
                    "needs_more_source_data": expected["needs_more_source_data"],
                    "risk_flags": list(expected["required_risk_flags"]),
                }
            )

        def taxonomy_provider(case, api_key, base_url):
            nonlocal seen_taxonomy
            seen_taxonomy += 1
            labels = case["acceptable_label_sets"][0]
            if seen_taxonomy == 1:
                labels = [] if labels else ["LAB_CHEMILUMINESCENCE_ANALYZER"]
            return json.dumps(
                {
                    "case_id": case["case_id"],
                    "taxonomy_ids": labels,
                    "needs_more_detail": case["needs_more_detail"],
                }
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_suite(
                api_key="fake-key",
                base_url="https://apihub.agnes-ai.com/v1",
                lease_db_path=Path(temp_dir) / "lease.sqlite",
                maintenance_window_confirmed=True,
                now_provider=clock.now,
                sleeper=clock.sleep,
                general_provider=general_provider,
                taxonomy_provider=taxonomy_provider,
            )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["admission_recommendation"], "KEEP_BENCHMARK_PENDING")
        self.assertFalse(result["automatic_classifier_admission_performed"])
        admission = load_classifier_admissions()[TARGET_CLASSIFIER_ID]
        self.assertEqual(admission.admission_status, "BENCHMARK_PENDING")
        self.assertFalse(admission.can_drive_matching)

    def test_unofficial_base_url_fails_before_provider_start(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                run_suite(
                    api_key="fake-key",
                    base_url="https://example.com/v1",
                    lease_db_path=Path(temp_dir) / "lease.sqlite",
                    maintenance_window_confirmed=True,
                    general_provider=lambda *args: calls.append("general") or "{}",
                    taxonomy_provider=lambda *args: calls.append("taxonomy") or "{}",
                )
        self.assertEqual(calls, [])

    def test_provider_failure_is_sanitized_and_counted_once(self) -> None:
        clock = FakeClock()
        call_count = 0

        def failing_general(manifest, case, api_key, base_url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("provider-body-with-secret-key")
            expected = case["expected"]
            return json.dumps(
                {
                    "case_id": case["case_id"],
                    "segment": expected["acceptable_segments"][0],
                    "item_detail_status": expected["item_detail_status"],
                    "needs_more_source_data": expected["needs_more_source_data"],
                    "risk_flags": list(expected["required_risk_flags"]),
                }
            )

        def taxonomy_provider(case, api_key, base_url):
            return json.dumps(
                {
                    "case_id": case["case_id"],
                    "taxonomy_ids": case["acceptable_label_sets"][0],
                    "needs_more_detail": case["needs_more_detail"],
                }
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_suite(
                api_key="do-not-echo-this-key",
                base_url="https://apihub.agnes-ai.com/v1",
                lease_db_path=Path(temp_dir) / "lease.sqlite",
                maintenance_window_confirmed=True,
                now_provider=clock.now,
                sleeper=clock.sleep,
                general_provider=failing_general,
                taxonomy_provider=taxonomy_provider,
            )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["provider_start_count"], 28)
        self.assertEqual(result["completed_case_count"], 27)
        self.assertEqual(result["general"]["failures"][0]["error_class"], "RuntimeError")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("provider-body-with-secret-key", serialized)
        self.assertNotIn("do-not-echo-this-key", serialized)

    def test_result_file_is_private_and_refuses_overwrite(self) -> None:
        result = dry_run_summary()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "benchmark-result.json"
            _write_private_result(path, result)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaises(Exception):
                _write_private_result(path, result)


if __name__ == "__main__":
    unittest.main()
