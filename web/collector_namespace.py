from __future__ import annotations

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
LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v2"
LEGACY_LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v1"
ACTIVE_CYCLE_TTL_SECONDS = 2 * 24 * 60 * 60
INCREMENTAL_ACTIVE_TTL_SECONDS = 15 * 60
INCREMENTAL_CHAIN_TTL_SECONDS = 2 * 24 * 60 * 60

_RUNTIME_KEY_ASSIGNMENTS = {
    "META_KEY": META_KEY,
    "CCGP_RECORDS_KEY": CCGP_RECORDS_KEY,
    "CCGP_EVENTS_KEY": CCGP_EVENTS_KEY,
    "CCGP_WATCH_KEY": CCGP_WATCH_KEY,
    "TJMUGH_RECORDS_KEY": TJMUGH_RECORDS_KEY,
    "TJNOTHOP_RECORDS_KEY": TJNOTHOP_RECORDS_KEY,
    "TEDA_RECORDS_KEY": TEDA_RECORDS_KEY,
    "TJFCH_RECORDS_KEY": TJFCH_RECORDS_KEY,
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
    retried/fail closed instead of being silently acknowledged. A terminal
    publish FAILED/BLOCKED state is an ended degraded cycle and is idempotent on
    redelivery just like a completed publish.
    """
    current = active_cycle_id(active_value)
    if current is not None:
        return "MATCH" if current == cycle_id else "SUPERSEDED"

    local_date = str(cycle_local_date or "").strip()
    today = str(current_local_date or "").strip()
    if local_date and today and local_date < today:
        return "EXPIRED_STALE"

    if isinstance(runtime_state, dict):
        state_date = str(runtime_state.get("local_date") or "").strip()
        if state_date and local_date and state_date > local_date:
            return "SUPERSEDED"
        if state_date == local_date:
            stages = runtime_state.get("stages")
            if isinstance(stages, dict):
                publish = stages.get("publish")
                if isinstance(publish, dict):
                    if publish.get("status") == "COMPLETED":
                        return "COMPLETED_CYCLE"
                    if publish.get("status") in {"FAILED", "BLOCKED"} and publish.get("terminal") is True:
                        return "ENDED_DEGRADED_CYCLE"

    return "MISSING_UNSAFE"
