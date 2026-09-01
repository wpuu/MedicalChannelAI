from __future__ import annotations

from typing import Any

NAMESPACE_VERSION = "v2"
QUEUE_TOPIC_NAME = "medicalchannelai-refresh-v2"

META_KEY = "medicalchannelai:collector-runtime-state:v2"
ACTIVE_CYCLE_KEY = "medicalchannelai:collector-active-cycle:v2"
CCGP_RECORDS_KEY = "medicalchannelai:collector-ccgp-records:v2"
CCGP_EVENTS_KEY = "medicalchannelai:collector-ccgp-events:v2"
CCGP_WATCH_KEY = "medicalchannelai:collector-ccgp-watch-projects:v2"
TJMUGH_RECORDS_KEY = "medicalchannelai:collector-tjmugh-records:v2"
TJNOTHOP_RECORDS_KEY = "medicalchannelai:collector-tjnothop-records:v2"
LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v2"
LEGACY_LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v1"
ACTIVE_CYCLE_TTL_SECONDS = 2 * 24 * 60 * 60

_RUNTIME_KEY_ASSIGNMENTS = {
    "META_KEY": META_KEY,
    "CCGP_RECORDS_KEY": CCGP_RECORDS_KEY,
    "CCGP_EVENTS_KEY": CCGP_EVENTS_KEY,
    "CCGP_WATCH_KEY": CCGP_WATCH_KEY,
    "TJMUGH_RECORDS_KEY": TJMUGH_RECORDS_KEY,
    "TJNOTHOP_RECORDS_KEY": TJNOTHOP_RECORDS_KEY,
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
