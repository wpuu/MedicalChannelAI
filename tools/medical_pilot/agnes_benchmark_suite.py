from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable

from .agnes_client import DEFAULT_BASE_URL, DEFAULT_MODEL, validate_base_url
from .agnes_dispatch import build_agnes_dispatch_plan
from .agnes_dispatch_queue import SQLiteAgnesDispatchQueue
from .agnes_global_lease import SQLiteAgnesLeaseStore, acquire_global_lease, release_global_lease
from .benchmark_agnes import (
    aggregate_scores as aggregate_general,
    build_user_prompt as build_general_prompt,
    call_chat_completion,
    extract_json_object as extract_general_json,
    load_manifest as load_general_manifest,
    score_case as score_general_case,
)
from .benchmark_agnes_taxonomy import (
    aggregate as aggregate_taxonomy,
    build_user_prompt as build_taxonomy_prompt,
    call_model as call_taxonomy_model,
    extract_json_object as extract_taxonomy_json,
    load_manifest as load_taxonomy_manifest,
    score_case as score_taxonomy_case,
)
from .classifier_admission import load_classifier_admissions


DEFAULT_LEASE_DB = Path("/srv/medical/data/pilot.sqlite")
TARGET_CLASSIFIER_ID = "agnes-2.5-flash-product-taxonomy-v0.1"
EXPECTED_GENERAL_CASES = 12
EXPECTED_TAXONOMY_CASES = 16
EXPECTED_TOTAL_CASES = 28
WORKER_ID = "agnes-benchmark-suite"
MAX_LEASE_WAIT_SECONDS = 900.0


class AgnesBenchmarkSuiteError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _aware_now(now_provider: Callable[[], datetime]) -> datetime:
    value = now_provider()
    if value.tzinfo is None or value.utcoffset() is None:
        raise AgnesBenchmarkSuiteError("BENCHMARK_CLOCK_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _registry_path() -> Path:
    return Path(__file__).with_name("product_classifier_registry.v0.1.json")


def _validate_suite_inputs() -> tuple[dict[str, Any], dict[str, Any], str]:
    general = load_general_manifest()
    taxonomy = load_taxonomy_manifest()
    if general.get("model_target") != DEFAULT_MODEL or taxonomy.get("model_target") != DEFAULT_MODEL:
        raise AgnesBenchmarkSuiteError("BENCHMARK_MODEL_TARGET_MISMATCH")
    if len(general.get("cases") or []) != EXPECTED_GENERAL_CASES:
        raise AgnesBenchmarkSuiteError("GENERAL_BENCHMARK_CASE_COUNT_CHANGED")
    if len(taxonomy.get("cases") or []) != EXPECTED_TAXONOMY_CASES:
        raise AgnesBenchmarkSuiteError("TAXONOMY_BENCHMARK_CASE_COUNT_CHANGED")
    if len(general["cases"]) + len(taxonomy["cases"]) != EXPECTED_TOTAL_CASES:
        raise AgnesBenchmarkSuiteError("BENCHMARK_TOTAL_CASE_COUNT_CHANGED")
    if taxonomy.get("classifier_id_if_passed") != TARGET_CLASSIFIER_ID:
        raise AgnesBenchmarkSuiteError("BENCHMARK_CLASSIFIER_ID_MISMATCH")

    admission = load_classifier_admissions().get(TARGET_CLASSIFIER_ID)
    if admission is None:
        raise AgnesBenchmarkSuiteError("TARGET_CLASSIFIER_NOT_REGISTERED")
    if admission.kind != "CONTROLLED_MODEL_CLASSIFICATION":
        raise AgnesBenchmarkSuiteError("TARGET_CLASSIFIER_KIND_INVALID")
    if admission.admission_status != "BENCHMARK_PENDING" or admission.can_drive_matching:
        raise AgnesBenchmarkSuiteError("TARGET_CLASSIFIER_NOT_BENCHMARK_PENDING")
    return general, taxonomy, _sha256_file(_registry_path())


def dry_run_summary() -> dict[str, Any]:
    general, taxonomy, registry_sha = _validate_suite_inputs()
    return {
        "schema_version": "0.1",
        "status": "DRY_RUN_NO_NETWORK",
        "model": DEFAULT_MODEL,
        "general_case_count": len(general["cases"]),
        "taxonomy_case_count": len(taxonomy["cases"]),
        "total_case_count": len(general["cases"]) + len(taxonomy["cases"]),
        "requires_shared_global_lease": True,
        "requires_quiescent_maintenance_window": True,
        "provider_retries_per_case": 0,
        "automatic_classifier_admission_allowed": False,
        "classifier_registry_modified": False,
        "classifier_registry_sha256": registry_sha,
        "admission_state_required": "BENCHMARK_PENDING",
        "network_called": False,
    }


def _assert_business_queue_quiescent(queue: SQLiteAgnesDispatchQueue) -> None:
    if queue.list_pending(limit=1):
        raise AgnesBenchmarkSuiteError("BUSINESS_AGNES_QUEUE_NOT_QUIESCENT")


def _sleep_until_lease(
    *,
    store: SQLiteAgnesLeaseStore,
    task_id: str,
    now_provider: Callable[[], datetime],
    sleeper: Callable[[float], None],
) -> tuple[str, datetime]:
    started = _aware_now(now_provider)
    task = {
        "task_id": task_id,
        "task_type": "BENCHMARK",
        "requested_at": started.isoformat(),
    }
    plan = build_agnes_dispatch_plan([task], now=started)
    dispatch_item = plan["items"][0]
    waited = 0.0

    while True:
        now = _aware_now(now_provider)
        decision = acquire_global_lease(
            store,
            dispatch_item=dispatch_item,
            worker_id=WORKER_ID,
            now=now,
        )
        if decision.status == "GRANTED" and decision.lease_id:
            return decision.lease_id, now
        if not decision.retry_after:
            raise AgnesBenchmarkSuiteError(f"LEASE_{decision.status}")
        retry_at = datetime.fromisoformat(decision.retry_after.replace("Z", "+00:00")).astimezone(timezone.utc)
        delay = max(0.05, (retry_at - now).total_seconds())
        waited += delay
        if waited > MAX_LEASE_WAIT_SECONDS:
            raise AgnesBenchmarkSuiteError("BENCHMARK_LEASE_WAIT_EXCEEDED")
        sleeper(delay)


def _safe_general_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id"),
        "valid_contract": bool(row.get("valid_contract")),
        "segment_correct": bool(row.get("segment_correct")),
        "item_detail_status_correct": bool(row.get("item_detail_status_correct")),
        "needs_more_source_data_correct": bool(row.get("needs_more_source_data_correct")),
        "required_risk_flag_recall": row.get("required_risk_flag_recall"),
        "unexpected_risk_flag_rate": row.get("unexpected_risk_flag_rate"),
    }


def _safe_taxonomy_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id"),
        "contract_valid": bool(row.get("contract_valid")),
        "acceptable_label_set": bool(row.get("acceptable_label_set")),
        "needs_more_detail_correct": bool(row.get("needs_more_detail_correct")),
        "safe_abstention": bool(row.get("safe_abstention")),
        "unknown_taxonomy_id": bool(row.get("unknown_taxonomy_id")),
    }


def _run_one_provider_start(
    *,
    store: SQLiteAgnesLeaseStore,
    task_id: str,
    provider_call: Callable[[], str],
    now_provider: Callable[[], datetime],
    sleeper: Callable[[float], None],
) -> str:
    lease_id, _ = _sleep_until_lease(
        store=store,
        task_id=task_id,
        now_provider=now_provider,
        sleeper=sleeper,
    )
    try:
        return provider_call()
    finally:
        release_global_lease(
            store,
            lease_id=lease_id,
            worker_id=WORKER_ID,
            now=_aware_now(now_provider),
        )


def run_suite(
    *,
    api_key: str,
    base_url: str,
    lease_db_path: Path,
    maintenance_window_confirmed: bool = False,
    now_provider: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    general_provider: Callable[[dict[str, Any], dict[str, Any], str, str], str] | None = None,
    taxonomy_provider: Callable[[dict[str, Any], str, str], str] | None = None,
) -> dict[str, Any]:
    if not maintenance_window_confirmed:
        raise AgnesBenchmarkSuiteError("MAINTENANCE_WINDOW_CONFIRMATION_REQUIRED")
    if not isinstance(api_key, str) or not api_key.strip():
        raise AgnesBenchmarkSuiteError("MCAI_AGNES_API_KEY_MISSING")
    official_base_url = validate_base_url(base_url)
    general_manifest, taxonomy_manifest, registry_before = _validate_suite_inputs()
    clock = now_provider or (lambda: datetime.now(timezone.utc))
    db_path = Path(lease_db_path)
    store = SQLiteAgnesLeaseStore(db_path, now=_aware_now(clock))
    business_queue = SQLiteAgnesDispatchQueue(db_path)
    _assert_business_queue_quiescent(business_queue)

    def default_general_provider(manifest: dict[str, Any], case: dict[str, Any], key: str, url: str) -> str:
        return call_chat_completion(
            base_url=url,
            api_key=key,
            model=DEFAULT_MODEL,
            user_prompt=build_general_prompt(manifest, case),
            retries=0,
            global_lease_granted=True,
        )

    def default_taxonomy_provider(case: dict[str, Any], key: str, url: str) -> str:
        return call_taxonomy_model(
            api_key=key,
            base_url=url,
            model=DEFAULT_MODEL,
            prompt=build_taxonomy_prompt(case),
            global_lease_granted=True,
        )

    general_call = general_provider or default_general_provider
    taxonomy_call = taxonomy_provider or default_taxonomy_provider
    general_scored: list[dict[str, Any]] = []
    general_failures: list[dict[str, str]] = []
    taxonomy_scored: list[dict[str, Any]] = []
    taxonomy_failures: list[dict[str, str]] = []
    provider_start_count = 0

    def invoke_general(case: dict[str, Any]) -> str:
        nonlocal provider_start_count
        provider_start_count += 1
        return general_call(general_manifest, case, api_key, official_base_url)

    def invoke_taxonomy(case: dict[str, Any]) -> str:
        nonlocal provider_start_count
        provider_start_count += 1
        return taxonomy_call(case, api_key, official_base_url)

    for case in general_manifest["cases"]:
        task_id = f"benchmark|general|{case['case_id']}"
        try:
            _assert_business_queue_quiescent(business_queue)
            raw = _run_one_provider_start(
                store=store,
                task_id=task_id,
                provider_call=lambda case=case: invoke_general(case),
                now_provider=clock,
                sleeper=sleeper,
            )
            output = extract_general_json(raw)
            general_scored.append(score_general_case(general_manifest, case, output))
        except Exception as exc:
            general_failures.append({"case_id": case["case_id"], "error_class": type(exc).__name__})
            if isinstance(exc, AgnesBenchmarkSuiteError) and exc.code == "BUSINESS_AGNES_QUEUE_NOT_QUIESCENT":
                break

    if not general_failures or general_failures[-1].get("error_class") != "AgnesBenchmarkSuiteError":
        for case in taxonomy_manifest["cases"]:
            task_id = f"benchmark|taxonomy|{case['case_id']}"
            try:
                _assert_business_queue_quiescent(business_queue)
                raw = _run_one_provider_start(
                    store=store,
                    task_id=task_id,
                    provider_call=lambda case=case: invoke_taxonomy(case),
                    now_provider=clock,
                    sleeper=sleeper,
                )
                output = extract_taxonomy_json(raw)
                taxonomy_scored.append(score_taxonomy_case(case, output))
            except Exception as exc:
                taxonomy_failures.append({"case_id": case["case_id"], "error_class": type(exc).__name__})
                if isinstance(exc, AgnesBenchmarkSuiteError) and exc.code == "BUSINESS_AGNES_QUEUE_NOT_QUIESCENT":
                    break

    general_aggregate = aggregate_general(general_manifest, general_scored, len(general_failures))
    taxonomy_aggregate = aggregate_taxonomy(taxonomy_manifest, taxonomy_scored, len(taxonomy_failures))
    registry_after = _sha256_file(_registry_path())
    registry_modified = registry_after != registry_before
    completed = len(general_scored) + len(taxonomy_scored)
    passed = (
        completed == EXPECTED_TOTAL_CASES
        and provider_start_count == EXPECTED_TOTAL_CASES
        and general_aggregate.get("passed") is True
        and taxonomy_aggregate.get("passed") is True
        and not registry_modified
    )

    return {
        "schema_version": "0.1",
        "status": "PASS" if passed else "FAIL",
        "model": DEFAULT_MODEL,
        "base_url_host_validated": True,
        "total_case_count": EXPECTED_TOTAL_CASES,
        "completed_case_count": completed,
        "provider_start_count": provider_start_count,
        "every_provider_start_requires_global_lease": True,
        "business_queue_quiescent_required": True,
        "maintenance_window_confirmed": True,
        "provider_retries_per_case": 0,
        "general": {
            "aggregate": general_aggregate,
            "cases": [_safe_general_row(row) for row in general_scored],
            "failures": general_failures,
        },
        "taxonomy": {
            "aggregate": taxonomy_aggregate,
            "cases": [_safe_taxonomy_row(row) for row in taxonomy_scored],
            "failures": taxonomy_failures,
        },
        "target_classifier_id": TARGET_CLASSIFIER_ID,
        "classifier_registry_modified": registry_modified,
        "automatic_classifier_admission_allowed": False,
        "automatic_classifier_admission_performed": False,
        "admission_recommendation": (
            "ELIGIBLE_FOR_MANUAL_ADMISSION_REVIEW" if passed else "KEEP_BENCHMARK_PENDING"
        ),
        "api_key_echoed": False,
    }


def _safe_failure(exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", None) or type(exc).__name__
    return {
        "schema_version": "0.1",
        "status": "FAIL",
        "error_class": str(code)[:120],
        "automatic_classifier_admission_allowed": False,
        "automatic_classifier_admission_performed": False,
        "classifier_registry_modified": False,
        "api_key_echoed": False,
    }


def _write_private_result(path: Path, result: dict[str, Any]) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise AgnesBenchmarkSuiteError("BENCHMARK_OUTPUT_ALREADY_EXISTS")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".agnes-benchmark-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, target)
        os.chmod(target, 0o600)
    except Exception:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed 28-case Agnes benchmark through the shared global lease. "
            "Passing never changes classifier admission automatically."
        )
    )
    parser.add_argument("--execute", action="store_true", help="Actually call Agnes. Default is no-network dry run.")
    parser.add_argument(
        "--maintenance-window",
        action="store_true",
        help="Required with --execute. Confirms customer API/worker are stopped or otherwise quiescent.",
    )
    parser.add_argument("--lease-db", type=Path, default=DEFAULT_LEASE_DB)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        if not args.execute:
            result = dry_run_summary()
        else:
            api_key = (os.environ.get("MCAI_AGNES_API_KEY") or "").strip()
            if not api_key:
                raise AgnesBenchmarkSuiteError("MCAI_AGNES_API_KEY_MISSING")
            base_url = (os.environ.get("MCAI_AGNES_BASE_URL") or DEFAULT_BASE_URL).strip()
            result = run_suite(
                api_key=api_key,
                base_url=base_url,
                lease_db_path=args.lease_db,
                maintenance_window_confirmed=args.maintenance_window,
            )
        if args.output:
            _write_private_result(args.output, result)
    except Exception as exc:
        result = _safe_failure(exc)

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") in {"PASS", "DRY_RUN_NO_NETWORK"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
