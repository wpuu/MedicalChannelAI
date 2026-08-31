from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .agnes_benchmark_suite import (
    EXPECTED_GENERAL_CASES,
    EXPECTED_TAXONOMY_CASES,
    EXPECTED_TOTAL_CASES,
    GENERAL_MANIFEST_PATH,
    TARGET_CLASSIFIER_ID,
    TAXONOMY_MANIFEST_PATH,
    _registry_path,
    _sha256_file,
)
from .agnes_client import DEFAULT_MODEL
from .classifier_admission import load_classifier_admissions


DEFAULT_RESULT_PATH = Path("/srv/medical/data/agnes-benchmark-result-v0.1.json")
MAX_RESULT_BYTES = 2 * 1024 * 1024


class AgnesBenchmarkReviewError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _result_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_private_result(path: Path) -> tuple[dict[str, Any], str]:
    target = Path(path)
    if target.is_symlink():
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_SYMLINK_FORBIDDEN")
    try:
        info = target.stat()
    except OSError as exc:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_UNREADABLE") from exc
    if not stat.S_ISREG(info.st_mode):
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_NOT_REGULAR_FILE")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_MODE_NOT_0600")
    if info.st_size <= 0 or info.st_size > MAX_RESULT_BYTES:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_SIZE_INVALID")
    try:
        raw = target.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_NOT_OBJECT")
    return payload, _result_sha256(raw)


def _require_true(payload: dict[str, Any], key: str, error_code: str) -> None:
    if payload.get(key) is not True:
        raise AgnesBenchmarkReviewError(error_code)


def _require_false(payload: dict[str, Any], key: str, error_code: str) -> None:
    if payload.get(key) is not False:
        raise AgnesBenchmarkReviewError(error_code)


def review_result(path: Path = DEFAULT_RESULT_PATH) -> dict[str, Any]:
    payload, result_sha = _load_private_result(path)

    if payload.get("schema_version") != "0.1" or payload.get("status") != "PASS":
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_NOT_PASS")
    if payload.get("model") != DEFAULT_MODEL:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_MODEL_MISMATCH")
    if payload.get("target_classifier_id") != TARGET_CLASSIFIER_ID:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_CLASSIFIER_MISMATCH")
    if payload.get("total_case_count") != EXPECTED_TOTAL_CASES:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_TOTAL_CASE_COUNT_MISMATCH")
    if payload.get("completed_case_count") != EXPECTED_TOTAL_CASES:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_INCOMPLETE")
    if payload.get("provider_start_count") != EXPECTED_TOTAL_CASES:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_PROVIDER_START_COUNT_MISMATCH")
    _require_true(payload, "every_provider_start_requires_global_lease", "BENCHMARK_RESULT_LEASE_GATE_MISSING")
    _require_true(payload, "business_queue_quiescent_required", "BENCHMARK_RESULT_QUEUE_GATE_MISSING")
    _require_true(payload, "maintenance_window_confirmed", "BENCHMARK_RESULT_MAINTENANCE_GATE_MISSING")
    if payload.get("provider_retries_per_case") != 0:
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_PROVIDER_RETRY_INVALID")
    _require_false(payload, "classifier_registry_modified", "BENCHMARK_RESULT_REGISTRY_WAS_MODIFIED")
    _require_false(payload, "benchmark_inputs_modified_during_run", "BENCHMARK_RESULT_INPUTS_CHANGED_DURING_RUN")
    _require_false(payload, "automatic_classifier_admission_allowed", "BENCHMARK_RESULT_AUTO_ADMISSION_ALLOWED")
    _require_false(payload, "automatic_classifier_admission_performed", "BENCHMARK_RESULT_AUTO_ADMISSION_PERFORMED")
    if payload.get("admission_recommendation") != "ELIGIBLE_FOR_MANUAL_ADMISSION_REVIEW":
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_NOT_ELIGIBLE_FOR_MANUAL_REVIEW")

    general = payload.get("general")
    taxonomy = payload.get("taxonomy")
    if not isinstance(general, dict) or not isinstance(taxonomy, dict):
        raise AgnesBenchmarkReviewError("BENCHMARK_RESULT_AGGREGATES_MISSING")
    if (general.get("aggregate") or {}).get("passed") is not True:
        raise AgnesBenchmarkReviewError("BENCHMARK_GENERAL_GATE_FAILED")
    if (taxonomy.get("aggregate") or {}).get("passed") is not True:
        raise AgnesBenchmarkReviewError("BENCHMARK_TAXONOMY_GATE_FAILED")
    if len(general.get("cases") or []) != EXPECTED_GENERAL_CASES or general.get("failures") not in ([], None):
        raise AgnesBenchmarkReviewError("BENCHMARK_GENERAL_CASE_EVIDENCE_INVALID")
    if len(taxonomy.get("cases") or []) != EXPECTED_TAXONOMY_CASES or taxonomy.get("failures") not in ([], None):
        raise AgnesBenchmarkReviewError("BENCHMARK_TAXONOMY_CASE_EVIDENCE_INVALID")

    current_general_sha = _sha256_file(GENERAL_MANIFEST_PATH)
    current_taxonomy_sha = _sha256_file(TAXONOMY_MANIFEST_PATH)
    current_registry_sha = _sha256_file(_registry_path())
    if payload.get("general_manifest_sha256") != current_general_sha:
        raise AgnesBenchmarkReviewError("BENCHMARK_GENERAL_MANIFEST_CHANGED_SINCE_RUN")
    if payload.get("taxonomy_manifest_sha256") != current_taxonomy_sha:
        raise AgnesBenchmarkReviewError("BENCHMARK_TAXONOMY_MANIFEST_CHANGED_SINCE_RUN")
    if payload.get("classifier_registry_sha256_before") != current_registry_sha:
        raise AgnesBenchmarkReviewError("BENCHMARK_REGISTRY_CHANGED_SINCE_RUN")
    if payload.get("classifier_registry_sha256_after") != current_registry_sha:
        raise AgnesBenchmarkReviewError("BENCHMARK_REGISTRY_AFTER_HASH_MISMATCH")

    admission = load_classifier_admissions().get(TARGET_CLASSIFIER_ID)
    if admission is None:
        raise AgnesBenchmarkReviewError("TARGET_CLASSIFIER_NOT_REGISTERED")
    if admission.admission_status != "BENCHMARK_PENDING" or admission.can_drive_matching:
        raise AgnesBenchmarkReviewError("TARGET_CLASSIFIER_ALREADY_CHANGED")

    return {
        "schema_version": "0.1",
        "status": "ELIGIBLE_FOR_MANUAL_REGISTRY_CHANGE",
        "benchmark_result_sha256": result_sha,
        "target_classifier_id": TARGET_CLASSIFIER_ID,
        "current_classifier_status": admission.admission_status,
        "current_classifier_can_drive_matching": admission.can_drive_matching,
        "benchmark_case_count": EXPECTED_TOTAL_CASES,
        "manifest_hashes_match_current_checkout": True,
        "registry_hash_matches_benchmark": True,
        "registry_change_performed": False,
        "automatic_classifier_admission_allowed": False,
        "next_action": "OWNER_REVIEW_REQUIRED_BEFORE_EXPLICIT_REGISTRY_COMMIT",
    }


def _safe_failure(exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", None) or type(exc).__name__
    return {
        "schema_version": "0.1",
        "status": "NOT_ELIGIBLE",
        "error_class": str(code)[:120],
        "registry_change_performed": False,
        "automatic_classifier_admission_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Review an Agnes benchmark result without changing classifier admission")
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT_PATH)
    args = parser.parse_args()
    try:
        result = review_result(args.result)
    except Exception as exc:
        result = _safe_failure(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") == "ELIGIBLE_FOR_MANUAL_REGISTRY_CHANGE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
