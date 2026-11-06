from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from typing import Any

from collector_epoch import RuntimeCache, preview_epoch

import collector_runtime as runtime
from collector_incremental import SOURCE_POLICIES, normalize_ledger
from collector_incremental_scheduler import SCHEDULED_INCREMENTAL_SOURCES
from collector_incremental_ticks import (
    BUSINESS_WINDOW_END,
    BUSINESS_WINDOW_START,
    TICK_INTERVAL_MINUTES,
)
from collector_namespace import (
    ACTIVE_CYCLE_KEY,
    INCREMENTAL_ACTIVE_KEY,
    INCREMENTAL_CHAIN_KEY,
    active_cycle_id,
    active_incremental_id,
    apply_runtime_namespace,
)

apply_runtime_namespace(runtime)
STAGE_ORDER = runtime.STAGE_ORDER
INCREMENTAL_SOURCE_IDS = SCHEDULED_INCREMENTAL_SOURCES

_INCREMENTAL_RESULT_FIELDS = (
    "discovered_candidate_count",
    "selected_detail_count",
    "deferred_detail_count",
    "skipped_unchanged_count",
    "verified_record_count",
    "verified_nonfact_count",
    "verification_failure_count",
    "canonical_record_count",
    "pending_record_count",
    "pending_barrier_count",
    "snapshot_refreshed",
    "snapshot_as_of",
    "deferred_reason",
)
_CHAIN_FIELDS = (
    "state",
    "business_date",
    "tick_id",
    "next_tick_id",
    "selected_source",
    "detail",
    "updated_at",
)

# Only these fixed parser codes may pass through. Never sanitize arbitrary
# exception text into a public code: it may contain credentials or source data.
_SAFE_DETAIL_REASON_CODES = frozenset("""
    TJMUGH_PROJECT_ITEMS_EMPTY TJMUGH_PROJECT_ITEMS_NOT_FOUND
    TJMUGH_PROJECT_ITEM_SEQUENCE_INVALID TJMUGH_PROJECT_SECTION_NOT_FOUND
    TJMUGH_PUBLISHED_DATE_NOT_FOUND TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND
    TJMUGH_SOURCE_HOST_REJECTED TJMUGH_TITLE_NOT_FOUND
    TJNOTHOP_BUDGET_INVALID TJNOTHOP_BUDGET_NOT_WHOLE_CNY
    TJNOTHOP_INDEX_DETAIL_HOST_MISMATCH TJNOTHOP_INDEX_HOST_REJECTED
    TJNOTHOP_INDEX_PUBLISHED_DATE_INVALID TJNOTHOP_INDEX_PUBLISHED_DATE_REQUIRED
    TJNOTHOP_PRODUCT_NAME_EMPTY TJNOTHOP_PRODUCT_NAME_NOT_FOUND
    TJNOTHOP_REGISTRATION_DATE_INVALID TJNOTHOP_REGISTRATION_DATE_NOT_FOUND
    TJNOTHOP_REGISTRATION_SECTION_NOT_FOUND TJNOTHOP_SOURCE_HOST_REJECTED
    TJNOTHOP_TITLE_MISMATCH TJNOTHOP_TITLE_NOT_FOUND
    TEDA_BUDGET_INVALID TEDA_INDEX_PUBLISHED_DATE_INVALID
    TEDA_INDEX_URL_REJECTED TEDA_MEDICAL_EARLY_SIGNAL_NOT_VERIFIED
    TEDA_OFFICIAL_PUBLISHED_DATE_NOT_AVAILABLE TEDA_PRODUCT_ITEMS_NOT_FOUND
    TEDA_PRODUCT_NAME_EMPTY TEDA_PRODUCT_SECTION_NOT_FOUND
    TEDA_PUBLISHED_DATE_INVALID TEDA_PUBLISHED_DATE_MISMATCH
    TEDA_REGISTRATION_DEADLINE_INVALID TEDA_REGISTRATION_DEADLINE_NOT_FOUND
    TEDA_SOURCE_URL_REJECTED TEDA_TITLE_MISMATCH
    TJFCH_BID_DEADLINE_INVALID TJFCH_BID_DEADLINE_NOT_EXACT
    TJFCH_BUDGET_INVALID TJFCH_BUDGET_NOT_WHOLE_CNY
    TJFCH_DETAIL_PUBLISHED_DATE_NOT_CONFIRMED TJFCH_INDEX_DETAIL_HOST_MISMATCH
    TJFCH_INDEX_HOST_REJECTED TJFCH_INDEX_PUBLISHED_DATE_INVALID
    TJFCH_NOTICE_TYPE_UNSUPPORTED TJFCH_SOURCE_HOST_REJECTED TJFCH_TITLE_MISMATCH
    TJFCH_TEST_INDEX_DETAIL_HOST_MISMATCH TJFCH_TEST_INDEX_HOST_REJECTED
    TJFCH_TEST_NOTICE_TYPE_UNSUPPORTED TJFCH_TEST_PUBLISHED_DATE_INVALID
    TJFCH_TEST_PUBLISHED_DATE_NOT_FOUND TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED
    TJFCH_TEST_SOURCE_HOST_REJECTED TJFCH_TEST_TITLE_MISMATCH
    TJZYEFY_HOSPITAL_IDENTITY_NOT_FOUND TJZYEFY_INDEX_DETAIL_HOST_MISMATCH
    TJZYEFY_INDEX_HOST_REJECTED TJZYEFY_INDEX_PUBLISHED_DATE_INVALID
    TJZYEFY_NON_MEDICAL_RESEARCH TJZYEFY_NOT_MARKET_RESEARCH
    TJZYEFY_PROCUREMENT_INTENT_NOT_SUPPORTED TJZYEFY_PRODUCT_ITEMS_NOT_FOUND
    TJZYEFY_PUBLISHED_DATE_INVALID TJZYEFY_PUBLISHED_DATE_MISMATCH
    TJZYEFY_PUBLISHED_DATE_NOT_FOUND TJZYEFY_REGISTRATION_DATE_INVALID
    TJZYEFY_REGISTRATION_DATE_NOT_FOUND TJZYEFY_REGISTRATION_TIME_INVALID
    TJZYEFY_REGISTRATION_WINDOW_NOT_FOUND TJZYEFY_SOURCE_HOST_REJECTED
    TJZYEFY_TITLE_MISMATCH
    TJZYEFY_INTENT_HOSPITAL_IDENTITY_NOT_FOUND TJZYEFY_INTENT_INDEX_DETAIL_HOST_MISMATCH
    TJZYEFY_INTENT_INDEX_HOST_REJECTED TJZYEFY_INTENT_INDEX_PUBLISHED_DATE_INVALID
    TJZYEFY_INTENT_NON_MEDICAL TJZYEFY_INTENT_NOTICE_TYPE_NOT_FOUND
    TJZYEFY_INTENT_PRODUCT_ITEMS_NOT_FOUND TJZYEFY_INTENT_PUBLISHED_DATE_INVALID
    TJZYEFY_INTENT_PUBLISHED_DATE_MISMATCH TJZYEFY_INTENT_PUBLISHED_DATE_NOT_FOUND
    TJZYEFY_INTENT_SOURCE_HOST_REJECTED TJZYEFY_INTENT_SUPPLIER_CONSULTATION_NOT_FOUND
    TJZYEFY_INTENT_TITLE_MISMATCH
    TJZXFC_DEADLINE_INVALID TJZXFC_HOSPITAL_IDENTITY_NOT_FOUND
    TJZXFC_INDEX_DETAIL_HOST_MISMATCH TJZXFC_INDEX_HOST_REJECTED
    TJZXFC_INDEX_PUBLISHED_DATE_INVALID TJZXFC_NON_MEDICAL_EARLY_SIGNAL
    TJZXFC_NOT_MARKET_RESEARCH TJZXFC_PUBLISHED_DATE_INVALID
    TJZXFC_PUBLISHED_DATE_MISMATCH TJZXFC_PUBLISHED_DATE_NOT_FOUND
    TJZXFC_REGISTRATION_DEADLINE_NOT_FOUND TJZXFC_RESEARCH_CONTENT_INVALID
    TJZXFC_RESEARCH_EVENT_TIME_INVALID TJZXFC_RESEARCH_EVENT_TIME_NOT_FOUND
    TJZXFC_SOURCE_HOST_REJECTED TJZXFC_TITLE_MISMATCH
""".split())
_FAILURE_CLASS_REASONS = {
    "HTTPError": "HTTP_ERROR",
    "URLError": "NETWORK_ERROR",
    "TimeoutError": "NETWORK_TIMEOUT",
    "ConnectionError": "NETWORK_ERROR",
    "ConnectionResetError": "NETWORK_ERROR",
    "UnicodeDecodeError": "RESPONSE_ENCODING_ERROR",
    "ValidationError": "DETAIL_VALIDATION_FAILED",
    "ValueError": "DETAIL_VALIDATION_FAILED",
    **{name: "DETAIL_PARSE_FAILED" for name in (
        "TjmughParseError", "TjnothopParseError", "TedaParseError", "TjfchParseError",
        "TjfchTestParseError", "TjzyefyParseError", "TjzyefyIntentParseError", "TjzxfcParseError",
    )},
}


def _safe_failure_reason(value: Any) -> str:
    text = value if isinstance(value, str) else ""
    exception_name, separator, message = text.partition(":")
    code = message.partition(":")[0] if separator else exception_name
    if code in _SAFE_DETAIL_REASON_CODES:
        return code
    if exception_name == "RuntimeError":
        prefixes = {source.upper() for source in INCREMENTAL_SOURCE_IDS}
        if any(code == f"{prefix}_NETWORK_ERROR" for prefix in prefixes):
            return "NETWORK_ERROR"
        if any(re.fullmatch(rf"{prefix}_HTTP_[1-5][0-9]{{2}}", code) for prefix in prefixes):
            return "HTTP_ERROR"
    return _FAILURE_CLASS_REASONS.get(exception_name, "DETAIL_VERIFICATION_FAILED")


def _failed_ledger_diagnostics(entries: dict[str, Any], source_id: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    candidates: list[dict[str, str]] = []
    for key, row in sorted(entries.items()):
        if row.get("verification_status") != "FAILED":
            continue
        reason = _safe_failure_reason(row.get("last_error"))
        counts[reason] = counts.get(reason, 0) + 1
        prefix, separator, reference = key.partition(":")
        if (len(candidates) < 5 and separator and prefix == source_id
                and re.fullmatch(r"[0-9a-f]{64}", reference)):
            candidates.append({"candidate_ref": reference, "reason": reason})
    return {"failed_reason_counts": dict(sorted(counts.items())), "failed_candidates": candidates}


def _incremental_ledger_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-ledger:{source_id}:v2"


def _incremental_bucket_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-bucket:{source_id}:v2"


def _incremental_pending_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-pending:{source_id}:v2"


def _incremental_pending_barrier_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-pending-barrier:{source_id}:v2"


def _safe_list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _safe_bucket_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    return {field: result.get(field) for field in _INCREMENTAL_RESULT_FIELDS}


def _safe_chain_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {field: value.get(field) for field in _CHAIN_FIELDS}


def _incremental_status(cache: RuntimeCache) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for source_id in INCREMENTAL_SOURCE_IDS:
        policy = SOURCE_POLICIES[source_id]
        ledger = normalize_ledger(cache.get(_incremental_ledger_key(source_id)))
        entries = list(ledger.get("entries", {}).values())
        verified = sum(1 for row in entries if row.get("verification_status") == "VERIFIED")
        failed = sum(1 for row in entries if row.get("verification_status") == "FAILED")
        unverified = max(0, len(entries) - verified - failed)
        bucket = cache.get(_incremental_bucket_key(source_id))
        bucket = bucket if isinstance(bucket, dict) else {}
        sources[source_id] = {
            "policy": {
                "scan_interval_minutes": int(policy["scan_interval_minutes"]),
                "reverify_after_hours": int(policy["reverify_after_hours"]),
                "max_details_per_scan": int(policy["max_details_per_scan"]),
            },
            "ledger": {
                "candidate_count": len(entries),
                "verified_count": verified,
                "failed_count": failed,
                "unverified_count": unverified,
                "updated_at": ledger.get("updated_at"),
                **_failed_ledger_diagnostics(ledger["entries"], source_id),
            },
            "staging": {
                "record_count": _safe_list_count(cache.get(_incremental_pending_key(source_id))),
                "barrier_count": _safe_list_count(
                    cache.get(_incremental_pending_barrier_key(source_id))
                ),
            },
            "last_completed_scan": {
                "bucket_id": bucket.get("bucket_id"),
                "completed_at": bucket.get("completed_at"),
                "result": _safe_bucket_result(bucket),
            },
        }
    return {
        "active_scan_id": active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY)),
        "tick_policy": {
            "timezone": "Asia/Shanghai",
            "business_window_start": BUSINESS_WINDOW_START.strftime("%H:%M"),
            "business_window_end": BUSINESS_WINDOW_END.strftime("%H:%M"),
            "tick_interval_minutes": TICK_INTERVAL_MINUTES,
        },
        "chain": _safe_chain_state(cache.get(INCREMENTAL_CHAIN_KEY)),
        "sources": sources,
    }


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            cache = RuntimeCache()
            state = runtime.load_status(cache)
            active = active_cycle_id(cache.get(ACTIVE_CYCLE_KEY))
            stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
            completed = sum(
                1
                for stage in STAGE_ORDER
                if isinstance(stages.get(stage), dict) and stages[stage].get("status") == "COMPLETED"
            )
            self._send_json(
                200,
                {
                    "schema_version": "0.1",
                    "service": "MedicalChannelAI",
                    "collector": {
                        **state,
                        "preview_epoch": preview_epoch(),
                        "active_cycle_id": active,
                        "execution_namespace": "v2",
                        "stage_order": list(STAGE_ORDER),
                        "completed_stage_count": completed,
                        "total_stage_count": len(STAGE_ORDER),
                        # Operational attempts are distinct from the committed
                        # snapshot health served by /api/status. Failed scans
                        # remain observable even when no publish occurs.
                        "source_scan_health": runtime.snapshot_source_health(cache),
                        "incremental": _incremental_status(cache),
                    },
                },
            )
        except Exception:
            self._send_json(503, {"error": "COLLECTOR_STATUS_UNAVAILABLE"})

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
