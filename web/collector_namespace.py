from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

NAMESPACE_VERSION = "v2"
QUEUE_TOPIC_NAME = "medicalchannelai-refresh-v2"

META_KEY = "medicalchannelai:collector-runtime-state:v2"
ACTIVE_CYCLE_KEY = "medicalchannelai:collector-active-cycle:v2"
INCREMENTAL_ACTIVE_KEY = "medicalchannelai:collector-incremental-active:v2"
INCREMENTAL_CHAIN_KEY = "medicalchannelai:collector-incremental-chain:v2"
CCGP_RECORDS_KEY = "medicalchannelai:collector-ccgp-records:v2"
CCGP_EVENTS_KEY = "medicalchannelai:collector-ccgp-events:v2"
CCGP_WATCH_KEY = "medicalchannelai:collector-ccgp-watch-projects:v2"
TJMUGH_RECORDS_KEY = "medicalchannelai:collector-tjmugh-records:v2"
TJNOTHOP_RECORDS_KEY = "medicalchannelai:collector-tjnothop-records:v2"
TEDA_RECORDS_KEY = "medicalchannelai:collector-teda-records:v2"
TJFCH_RECORDS_KEY = "medicalchannelai:collector-tjfch-records:v2"
TJZYEFY_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-records:v2"
TJZYEFY_INTENT_RECORDS_KEY = "medicalchannelai:collector-tjzyefy-intent-records:v2"
TJZXFC_RECORDS_KEY = "medicalchannelai:collector-tjzxfc-records:v2"
SOURCE_HEALTH_KEY = "medicalchannelai:collector-source-health:v2"
LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v2"
LEGACY_LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v1"
ACTIVE_CYCLE_TTL_SECONDS = 2 * 24 * 60 * 60
INCREMENTAL_ACTIVE_TTL_SECONDS = 15 * 60
INCREMENTAL_CHAIN_TTL_SECONDS = 2 * 24 * 60 * 60
DEEP_EXECUTION_LEASE_TIMEOUT = timedelta(minutes=15)

_RUNTIME_KEY_ASSIGNMENTS = {
    "META_KEY": META_KEY,
    "CCGP_RECORDS_KEY": CCGP_RECORDS_KEY,
    "CCGP_EVENTS_KEY": CCGP_EVENTS_KEY,
    "CCGP_WATCH_KEY": CCGP_WATCH_KEY,
    "TJMUGH_RECORDS_KEY": TJMUGH_RECORDS_KEY,
    "TJNOTHOP_RECORDS_KEY": TJNOTHOP_RECORDS_KEY,
    "TEDA_RECORDS_KEY": TEDA_RECORDS_KEY,
    "TJFCH_RECORDS_KEY": TJFCH_RECORDS_KEY,
    "TJZYEFY_RECORDS_KEY": TJZYEFY_RECORDS_KEY,
    "TJZYEFY_INTENT_RECORDS_KEY": TJZYEFY_INTENT_RECORDS_KEY,
    "TJZXFC_RECORDS_KEY": TJZXFC_RECORDS_KEY,
    "SOURCE_HEALTH_KEY": SOURCE_HEALTH_KEY,
    "LATEST_RUNTIME_SNAPSHOT_KEY": LATEST_RUNTIME_SNAPSHOT_KEY,
}


def apply_runtime_namespace(runtime_module: Any) -> None:
    """Switch the collector runtime to the isolated v2 cache namespace."""
    for name, value in _RUNTIME_KEY_ASSIGNMENTS.items():
        setattr(runtime_module, name, value)


def active_cycle_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    cycle_id = str(value.get("cycle_id") or "").strip()
    return cycle_id or None


def active_incremental_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    scan_id = str(value.get("scan_id") or "").strip()
    return scan_id or None


def cycle_has_running_stage(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    stages = value.get("stages")
    if not isinstance(stages, dict):
        return False
    return any(
        isinstance(stage_state, dict) and stage_state.get("status") == "RUNNING"
        for stage_state in stages.values()
    )


def deep_cycle_owner_is_live(
    active_value: Any, runtime_state: Any, *, now: datetime,
) -> bool:
    """Distinguish a cached owner marker from a current execution lease.

    Fifteen minutes exceeds the bounded 300-second worker and its queue retry
    delay. A long deep cycle remains live through actual stage writes and queue
    heartbeats; its frozen collection clock never establishes liveness.
    Unknown legacy wall metadata remains protected until it can be reconciled.
    """
    if active_cycle_id(active_value) is None:
        return False
    raw_clocks = [active_value.get("activated_at"), active_value.get("wall_heartbeat_at")]
    if (
        isinstance(runtime_state, dict)
        and active_value.get("local_date")
        and runtime_state.get("local_date") == active_value.get("local_date")
    ):
        raw_clocks.append(runtime_state.get("updated_at"))
        stages = runtime_state.get("stages")
        if isinstance(stages, dict):
            raw_clocks.extend(
                row.get("wall_started_at") for row in stages.values() if isinstance(row, dict)
            )
    clocks = []
    for raw in raw_clocks:
        try:
            parsed = datetime.fromisoformat(str(raw or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            clocks.append(parsed.astimezone(timezone.utc))
    return not clocks or now.astimezone(timezone.utc) - max(clocks) < DEEP_EXECUTION_LEASE_TIMEOUT


def deep_message_lease_disposition(
    active_value: Any,
    runtime_state: Any,
    *,
    cycle_id: str,
    cycle_local_date: str,
    current_local_date: str,
) -> str:
    """Classify a deep-collector queue delivery against the mutation lease.

    Queue delivery is at-least-once. A missing active lease is normal only after
    the whole authoritative cycle has completed and publish was marked COMPLETED,
    or when the message is clearly from an older date that has been superseded.
    Missing lease during an unfinished same-day cycle remains unsafe and must be
    retried/fail closed instead of being silently acknowledged.
    """
    current = active_cycle_id(active_value)
    if current is not None:
        return "MATCH" if current == cycle_id else "SUPERSEDED"

    local_date = str(cycle_local_date or "").strip()
    today = str(current_local_date or "").strip()
    if local_date and today and local_date < today:
        return "EXPIRED_STALE"

    if isinstance(runtime_state, dict):
        if runtime_state.get("abandoned_cycle_id") == cycle_id:
            return "SUPERSEDED"
        state_date = str(runtime_state.get("local_date") or "").strip()
        if state_date and local_date and state_date > local_date:
            return "SUPERSEDED"
        if state_date == local_date:
            stages = runtime_state.get("stages")
            if isinstance(stages, dict):
                publish = stages.get("publish")
                if isinstance(publish, dict) and publish.get("status") == "COMPLETED":
                    return "COMPLETED_CYCLE"

    return "MISSING_UNSAFE"
