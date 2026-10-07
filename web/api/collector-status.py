from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

from vercel.functions import RuntimeCache

import collector_runtime as runtime
from collector_automation_health import public_automation_health
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
                        "active_cycle_id": active,
                        "execution_namespace": "v2",
                        "stage_order": list(STAGE_ORDER),
                        "completed_stage_count": completed,
                        "total_stage_count": len(STAGE_ORDER),
                        "incremental": _incremental_status(cache),
                        "automation": public_automation_health(cache),
                    },
                },
            )
        except Exception:
            self._send_json(503, {"error": "COLLECTOR_STATUS_UNAVAILABLE"})

    def do_POST(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.end_headers()
