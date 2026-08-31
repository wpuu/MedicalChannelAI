from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from .agnes_client import AgnesChatClient, AgnesClientError, DEFAULT_BASE_URL
from .agnes_global_lease import SQLiteAgnesLeaseStore, acquire_global_lease, release_global_lease
from .model_decision_contract import (
    GroundedFact,
    ModelDecisionError,
    ModelDecisionInput,
    validate_model_decision,
)


WORKER_ID = "agnes-provider-smoke-v0.1"
TASK_ID = "smoke|agnes-provider|synthetic-grounded-contract-v0.1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _smoke_input() -> ModelDecisionInput:
    return ModelDecisionInput(
        opportunity_id="opp_7b44844b-56d4-5bbf-ae9c-8f32b6d15d21",
        match_status="MATCHED_PERSONALIZED",
        recommendation_mode="PERSONALIZED_RECOMMENDATION",
        lifecycle_state="TENDERING",
        allowed_action_types=(
            "PREPARE_BID",
            "VERIFY_RELATIONSHIP",
            "FIND_MANUFACTURER",
            "CONTACT_CHANNEL_PARTNER",
            "MONITOR",
            "NO_ACTION",
        ),
        allowed_reason_codes=(
            "RELATIONSHIP_EXISTS",
            "RELATIONSHIP_UNKNOWN",
            "PRODUCT_CAPABILITY_DIRECT",
            "PRODUCT_CAPABILITY_PARTNERABLE",
            "EARLY_STAGE",
            "FORMAL_TENDER",
            "LARGE_PROJECT",
            "RENTAL_CAPABILITY_MATCH",
            "AWARD_INTELLIGENCE_ONLY",
        ),
        allowed_risk_codes=(
            "ATTACHMENT_DETAILS_PENDING",
            "COVERAGE_PARTIAL",
            "RELATIONSHIP_UNKNOWN",
            "PRODUCT_CLASSIFICATION_MODEL_DERIVED",
            "DEADLINE_NEAR",
            "CROSS_STAGE_LINK_UNCONFIRMED",
        ),
        grounded_facts=(
            GroundedFact(
                fact_id="fact_11111111-1111-1111-1111-111111111111",
                field_name="project_name",
                field_value="隔离 Provider Smoke 测试项目",
                source_url="https://www.ccgp.gov.cn/smoke-contract-only",
            ),
        ),
        confirmed_profile_context={
            "business_role": "LOCAL_DISTRIBUTOR",
            "partnering_policy": {
                "can_seek_temporary_manufacturer": True,
                "can_cooperate_with_channel_partner": True,
                "can_do_rental_projects": False,
            },
            "opportunity_thresholds": {"minimum_project_amount_cny": "100000"},
            "product_capabilities": [],
            "hospital_relationship": None,
            "profile_status": "READY_FOR_CANDIDATE_MATCHING",
        },
        grounded_fact_source_count=1,
        grounded_fact_omitted_count=0,
        grounded_fact_char_count=80,
        max_grounded_facts=24,
        max_grounded_fact_chars=12000,
    )


def run_provider_smoke(
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    lease_db_path: Path,
    now_provider: Callable[[], datetime] = _utc_now,
    model_call: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("MCAI_AGNES_API_KEY is required")

    started_at = now_provider()
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("now_provider must return timezone-aware datetime")

    model_input = _smoke_input()
    store = SQLiteAgnesLeaseStore(Path(lease_db_path), now=started_at)
    dispatch_item = {
        "task_id": TASK_ID,
        "requires_global_lease": True,
        "not_before": started_at.astimezone(timezone.utc).isoformat(),
    }
    lease = acquire_global_lease(
        store,
        dispatch_item=dispatch_item,
        worker_id=WORKER_ID,
        now=started_at,
    )
    if lease.status != "GRANTED" or not lease.lease_id:
        return {
            "schema_version": "0.1",
            "status": "DEFERRED",
            "provider_call_executed": False,
            "contract_validation_passed": False,
            "lease_status": lease.status,
            "retry_after": lease.retry_after,
        }

    released = False
    try:
        caller = model_call or AgnesChatClient(api_key=api_key.strip(), base_url=base_url)
        output = caller(model_input.as_dict())
        validated = validate_model_decision(output, model_input)
        return {
            "schema_version": "0.1",
            "status": "PASS",
            "provider_call_executed": True,
            "contract_validation_passed": True,
            "action_type": validated["action_type"],
            "supporting_fact_count": len(validated["supporting_fact_ids"]),
            "requires_human_confirmation": validated["requires_human_confirmation"],
            "lease_status": "GRANTED",
        }
    finally:
        released = release_global_lease(
            store,
            lease_id=lease.lease_id,
            worker_id=WORKER_ID,
            now=now_provider(),
        )
        if not released:
            raise RuntimeError("Agnes smoke lease could not be released")


def _safe_failure(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AgnesClientError):
        return {
            "schema_version": "0.1",
            "status": "FAIL",
            "provider_call_executed": True,
            "contract_validation_passed": False,
            "error_class": exc.error_class,
            "retryable": exc.retryable,
        }
    if isinstance(exc, ModelDecisionError):
        return {
            "schema_version": "0.1",
            "status": "FAIL",
            "provider_call_executed": True,
            "contract_validation_passed": False,
            "error_class": exc.code,
            "retryable": False,
        }
    return {
        "schema_version": "0.1",
        "status": "FAIL",
        "provider_call_executed": False,
        "contract_validation_passed": False,
        "error_class": type(exc).__name__,
        "retryable": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one isolated authenticated Agnes provider contract smoke using synthetic grounded data."
    )
    parser.add_argument(
        "--lease-db",
        type=Path,
        default=None,
        help="Optional isolated SQLite path. Defaults to a temporary file and never uses Pilot customer data.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("MCAI_AGNES_API_KEY", "")
    base_url = os.environ.get("MCAI_AGNES_BASE_URL", DEFAULT_BASE_URL)
    if args.lease_db is not None:
        lease_db = args.lease_db
        cleanup = False
    else:
        handle = tempfile.NamedTemporaryFile(prefix="mcai-agnes-smoke-", suffix=".sqlite", delete=False)
        handle.close()
        lease_db = Path(handle.name)
        cleanup = True

    try:
        try:
            result = run_provider_smoke(
                api_key=api_key,
                base_url=base_url,
                lease_db_path=lease_db,
            )
        except Exception as exc:
            result = _safe_failure(exc)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("status") == "PASS" else 2
    finally:
        if cleanup:
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(lease_db) + suffix).unlink(missing_ok=True)
                except OSError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
