from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Callable

from .today_actions_http import TrustedPrincipal
from .today_actions_queue_worker import execute_next_queued_today_actions_task
from .today_actions_worker_daemon import build_agnes_client_from_env
from .today_runtime import build_sqlite_today_runtime


SYNTHETIC_TENANT_ID = "tenant_full_chain_smoke"
SYNTHETIC_PROFILE_ID = "mprof_90000000-0000-0000-0000-000000000001"
SYNTHETIC_OPPORTUNITY_ID = "opp_90000000-0000-0000-0000-000000000002"
SYNTHETIC_FACT_ID = "fact_full_chain_smoke_project_name"
SYNTHETIC_TAXONOMY_ID = "LAB_CHEMILUMINESCENCE_ANALYZER"
SYNTHETIC_COMPANY = "【隔离验收合成数据】医疗渠道公司"
SYNTHETIC_HOSPITAL = "【隔离验收合成数据】天津验收医院"
SYNTHETIC_PROJECT = "【隔离验收合成数据】化学发光设备采购项目"


class PilotFullChainSmokeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PilotFullChainSmokeError(f"{name.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value


def _starter_profile(now: datetime) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "profile_id": SYNTHETIC_PROFILE_ID,
        "tenant_id": SYNTHETIC_TENANT_ID,
        "company_name": SYNTHETIC_COMPANY,
        "business_role": "OTHER",
        "operating_regions": [],
        "customer_types": [],
        "product_capabilities": [],
        "partnering_policy": {
            "can_seek_temporary_manufacturer": False,
            "can_cooperate_with_channel_partner": False,
            "can_do_rental_projects": False,
        },
        "opportunity_thresholds": {
            "minimum_project_amount_cny": "0",
            "owner_attention_amount_cny": None,
            "preferred_stages": [],
        },
        "exclusion_rules": [],
        "hospital_relationships": [],
        "confirmation_flags": {
            "region_scope_confirmed": False,
            "customer_types_confirmed": False,
            "product_capabilities_confirmed": False,
            "partnering_policy_confirmed": False,
            "opportunity_preferences_confirmed": False,
            "exclusion_rules_confirmed": False,
        },
        "profile_status": "INCOMPLETE",
        "profile_completeness": 0,
        "missing_required_conditions": ["CUSTOMER_PROFILE_NOT_CONFIRMED"],
        "updated_at": now.astimezone(timezone.utc).isoformat(),
    }


def _editable_complete_profile(now: datetime) -> dict[str, Any]:
    return {
        "company_name": SYNTHETIC_COMPANY,
        "business_role": "LOCAL_DISTRIBUTOR",
        "operating_regions": [
            {
                "province": "天津市",
                "city": "天津市",
                "scope_mode": "ENTIRE_CITY",
                "districts": [],
            }
        ],
        "customer_types": ["TERTIARY_HOSPITAL"],
        "product_capabilities": [
            {
                "category": "IVD",
                "subcategory": "化学发光分析仪",
                "taxonomy_ids": [SYNTHETIC_TAXONOMY_ID],
                "brands": [],
                "capability_type": "DIRECT_UNCONFIRMED",
                "notes": "SYNTHETIC_FULL_CHAIN_SMOKE",
            }
        ],
        "partnering_policy": {
            "can_seek_temporary_manufacturer": True,
            "can_cooperate_with_channel_partner": True,
            "can_do_rental_projects": False,
        },
        "opportunity_thresholds": {
            "minimum_project_amount_cny": "100000.00",
            "owner_attention_amount_cny": "1000000.00",
            "preferred_stages": ["PROCUREMENT_INTENT", "TENDERING", "AWARDED"],
        },
        "exclusion_rules": [],
        "hospital_relationships": [
            {
                "hospital_name": SYNTHETIC_HOSPITAL,
                "department": "检验科",
                "relationship_strength": "STRONG",
                "owner": "SYNTHETIC_SMOKE_OWNER",
                "confirmed_by_customer": True,
                "last_confirmed_at": now.astimezone(timezone.utc).isoformat(),
            }
        ],
        "confirmation_flags": {
            "region_scope_confirmed": True,
            "customer_types_confirmed": True,
            "product_capabilities_confirmed": True,
            "partnering_policy_confirmed": True,
            "opportunity_preferences_confirmed": True,
            "exclusion_rules_confirmed": True,
        },
    }


def _synthetic_opportunity(now: datetime) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "opportunity_id": SYNTHETIC_OPPORTUNITY_ID,
        "project_number": "SYNTHETIC-SMOKE-001",
        "buyer_name": SYNTHETIC_HOSPITAL,
        "hospital_name": SYNTHETIC_HOSPITAL,
        "department": "检验科",
        "project_name": SYNTHETIC_PROJECT,
        "verification_status": "VERIFIED",
        "coverage_status": "PARTIAL",
        "region": {"province": "天津市", "city": "天津市", "district": "和平区"},
        "customer_type": "TERTIARY_HOSPITAL",
        "customer_type_provenance": "OFFICIAL_INSTITUTION_EVIDENCE",
        "customer_type_validation_status": "VALIDATED",
        "institution_evidence_id": "inst_synthetic_full_chain_smoke",
        "lifecycle_state": "TENDERING",
        "notice_type": "采购公告",
        "published_at": now.astimezone(timezone.utc).isoformat(),
        "published_at_precision": "DATETIME",
        "budget": {"amount": "5730000.00", "currency": "CNY"},
        "product_labels": [SYNTHETIC_TAXONOMY_ID],
        "product_label_provenance": "HUMAN_CONFIRMED",
        "product_label_validation_status": "VALIDATED",
        "product_classifier_id": "synthetic-full-chain-smoke-v0.1",
        "product_categories": ["IVD"],
        "product_items": ["化学发光分析仪"],
        "is_rental_project": False,
    }


def _synthetic_evidence() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "fact_id": SYNTHETIC_FACT_ID,
        "opportunity_id": SYNTHETIC_OPPORTUNITY_ID,
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": SYNTHETIC_PROJECT,
        "source_url": "https://example.invalid/medicalchannelai/synthetic-full-chain-smoke",
    }


def _cookie_pair(set_cookie: str) -> str:
    pair = str(set_cookie or "").split(";", 1)[0].strip()
    if not pair or "=" not in pair:
        raise PilotFullChainSmokeError("SESSION_COOKIE_MISSING")
    return pair


def _single_card(body: dict[str, Any], expected_status: str) -> dict[str, Any]:
    cards = body.get("cards")
    if not isinstance(cards, list) or len(cards) != 1 or not isinstance(cards[0], dict):
        raise PilotFullChainSmokeError("TODAY_SINGLE_CARD_EXPECTED")
    card = cards[0]
    if card.get("opportunity_id") != SYNTHETIC_OPPORTUNITY_ID:
        raise PilotFullChainSmokeError("TODAY_OPPORTUNITY_MISMATCH")
    if card.get("model_decision_status") != expected_status:
        raise PilotFullChainSmokeError(f"TODAY_{expected_status}_NOT_OBSERVED")
    return card


def _safe_failure(exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", None) or type(exc).__name__
    return {
        "schema_version": "0.1",
        "status": "FAIL",
        "error_class": str(code)[:120],
        "database_scope": "TEMPORARY_ONLY",
        "synthetic_account": True,
        "customer_data_used": False,
        "production_data_touched": False,
    }


def run_full_chain_smoke(
    *,
    model_call: Callable[[dict[str, Any]], dict[str, Any]],
    now_provider: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    completion_clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Exercise the real customer-to-Agnes path on an isolated temporary SQLite DB.

    No external procurement source is fetched. All account/profile/opportunity/evidence
    values are explicit synthetic smoke data. The only external call, when `model_call`
    is a real Agnes client, is the one grounded model request produced by the normal
    Today Actions queue/worker path.
    """

    clock = now_provider or (lambda: datetime.now(timezone.utc))
    started_at = _aware(clock(), "started_at")

    with tempfile.TemporaryDirectory(prefix="mcai-full-chain-smoke-") as temp_dir:
        db_path = Path(temp_dir) / "pilot.sqlite"
        runtime = build_sqlite_today_runtime(db_path, now_provider=clock)
        principal = TrustedPrincipal(SYNTHETIC_TENANT_ID, SYNTHETIC_PROFILE_ID)

        runtime.repository.upsert_profile(_starter_profile(started_at))
        runtime.repository.upsert_public_opportunity(_synthetic_opportunity(started_at))
        runtime.repository.upsert_public_evidence(_synthetic_evidence())

        invite = runtime.issue_profile_invite(principal=principal, now=started_at, ttl_seconds=1800)
        before = runtime.account_store.get(principal)
        if before is None or before.status != "INVITED":
            raise PilotFullChainSmokeError("ACCOUNT_INVITED_NOT_OBSERVED")

        redeemed = runtime.auth_transport.handle(
            method="POST",
            target="/auth/redeem",
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=json.dumps({"code": invite.code}, separators=(",", ":")).encode("utf-8"),
            now=started_at,
        )
        if redeemed.status_code != 200 or redeemed.json_body() != {"authenticated": True}:
            raise PilotFullChainSmokeError("INVITE_REDEEM_FAILED")
        cookie = _cookie_pair(redeemed.headers.get("Set-Cookie", ""))
        after = runtime.account_store.get(principal)
        if after is None or after.status != "ACTIVE":
            raise PilotFullChainSmokeError("ACCOUNT_ACTIVE_NOT_OBSERVED")

        replay = runtime.auth_transport.handle(
            method="POST",
            target="/auth/redeem",
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=json.dumps({"code": invite.code}, separators=(",", ":")).encode("utf-8"),
            now=started_at,
        )
        if replay.status_code != 401:
            raise PilotFullChainSmokeError("INVITE_REPLAY_NOT_REJECTED")

        profile_saved = runtime.profile_transport.handle(
            method="PUT",
            target="/profile",
            headers={"Cookie": cookie},
            body=json.dumps(
                _editable_complete_profile(started_at),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            now=started_at,
        )
        if profile_saved.status_code != 200:
            raise PilotFullChainSmokeError("PROFILE_SAVE_FAILED")
        readiness = profile_saved.json_body().get("readiness") or {}
        if readiness.get("personalized_recommendation_allowed") is not True:
            raise PilotFullChainSmokeError("PROFILE_NOT_PERSONALIZED_READY")

        initial_today = runtime.transport.handle(
            method="GET",
            target="/today",
            headers={"Cookie": cookie},
            now=started_at,
        )
        if initial_today.status_code != 200:
            raise PilotFullChainSmokeError("INITIAL_TODAY_FAILED")
        initial_body = initial_today.json_body()
        _single_card(initial_body, "AWAITING_MODEL")
        if initial_body.get("model_request_count") != 1:
            raise PilotFullChainSmokeError("INITIAL_MODEL_REQUEST_COUNT_INVALID")
        for forbidden in ("model_requests", "task_payloads", "agnes_dispatch_plan", "provider", "api_key"):
            if forbidden in initial_body:
                raise PilotFullChainSmokeError("PUBLIC_INTERNAL_FIELD_LEAK")

        pending = runtime.dispatch_queue.list_pending(limit=10)
        if len(pending) != 1:
            raise PilotFullChainSmokeError("QUEUE_SINGLE_TASK_EXPECTED")
        due_raw = pending[0].get("dispatch_item", {}).get("not_before")
        if not isinstance(due_raw, str):
            raise PilotFullChainSmokeError("QUEUE_NOT_BEFORE_MISSING")
        due = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        _aware(due, "queue_not_before")

        current = _aware(clock(), "current_time")
        delay = (due.astimezone(timezone.utc) - current.astimezone(timezone.utc)).total_seconds()
        if delay > 10.0:
            raise PilotFullChainSmokeError("QUEUE_DELAY_UNEXPECTED")
        if delay > 0:
            sleeper(delay)
        observed = _aware(clock(), "worker_time")
        worker_now = max(observed.astimezone(timezone.utc), due.astimezone(timezone.utc))

        worker = execute_next_queued_today_actions_task(
            queue=runtime.dispatch_queue,
            lease_store=runtime.lease_store,
            result_store=runtime.result_store,
            worker_id="full-chain-smoke-worker",
            now=worker_now,
            model_call=model_call,
            clock=completion_clock,
        )
        if worker.status != "READY":
            raise PilotFullChainSmokeError(f"WORKER_{worker.status}")
        if runtime.dispatch_queue.list_pending(limit=10):
            raise PilotFullChainSmokeError("QUEUE_NOT_DRAINED_AFTER_READY")

        final_now = max(worker_now + timedelta(milliseconds=1), _aware(clock(), "final_time").astimezone(timezone.utc))
        final_today = runtime.transport.handle(
            method="GET",
            target="/today",
            headers={"Cookie": cookie},
            now=final_now,
        )
        if final_today.status_code != 200:
            raise PilotFullChainSmokeError("FINAL_TODAY_FAILED")
        final_body = final_today.json_body()
        final_card = _single_card(final_body, "READY")
        if final_body.get("model_request_count") != 0 or final_card.get("decision") is None:
            raise PilotFullChainSmokeError("FINAL_READY_DECISION_MISSING")
        if runtime.dispatch_queue.list_pending(limit=10):
            raise PilotFullChainSmokeError("FINAL_QUEUE_NOT_EMPTY")

        return {
            "schema_version": "0.1",
            "status": "PASS",
            "database_scope": "TEMPORARY_ONLY",
            "synthetic_account": True,
            "customer_data_used": False,
            "production_data_touched": False,
            "invite_redeemed": True,
            "invite_replay_rejected": True,
            "account_transition": "INVITED_TO_ACTIVE",
            "profile_saved": True,
            "profile_personalized_ready": True,
            "initial_today_model_status": "AWAITING_MODEL",
            "queued_task_count": 1,
            "global_lease_required": True,
            "worker_status": "READY",
            "provider_call_executed": True,
            "queue_drained": True,
            "final_today_model_status": "READY",
            "decision_rendered": True,
            "public_internal_field_leak": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full invite/session/profile/Today/queue/Agnes/READY path in temporary SQLite. "
            "Requires MCAI_AGNES_API_KEY and never touches the production Pilot database."
        )
    )
    parser.parse_args()
    try:
        client = build_agnes_client_from_env()
        result = run_full_chain_smoke(model_call=client)
    except Exception as exc:
        result = _safe_failure(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
