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
LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v2"
LEGACY_LATEST_RUNTIME_SNAPSHOT_KEY = "medicalchannelai:verified-snapshot:latest:v1"
ACTIVE_CYCLE_TTL_SECONDS = 2 * 24 * 60 * 60
INCREMENTAL_ACTIVE_TTL_SECONDS = 15 * 60
INCREMENTAL_CHAIN_TTL_SECONDS = 2 * 24 * 60 * 60
STATE_TTL_SECONDS = 14 * 24 * 60 * 60
STATE_CACHE_TAG = "medicalchannelai-collector-state"

# Must equal functions["api/collector-queue.py"].maxDuration in web/vercel.json
# (guarded by tests). Vercel terminates the queue worker at that limit, so a
# stage whose lease is older than this cannot still be running anywhere.
QUEUE_FUNCTION_MAX_DURATION_SECONDS = 300
# Grace for clock skew between instances; NOT for extra work time.
STAGE_LEASE_GRACE_SECONDS = 15
STAGE_LEASE_SECONDS = QUEUE_FUNCTION_MAX_DURATION_SECONDS + STAGE_LEASE_GRACE_SECONDS
# Same-day manual/cron re-triggers may mint at most this many recovery cycles.
MAX_RECOVERY_CYCLES_PER_DAY = 3

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


def parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def stage_lease_expires_at(stage_state: Any) -> datetime | None:
    """Wall-clock instant after which a RUNNING stage entry is known to be dead.

    New entries carry ``lease_expires_at``. Entries written before the lease
    existed fall back to ``started_at`` + STAGE_LEASE_SECONDS. Unparsable
    entries return None and are treated as already expired.
    """
    if not isinstance(stage_state, dict):
        return None
    explicit = parse_iso_datetime(stage_state.get("lease_expires_at"))
    if explicit is not None:
        return explicit
    started = parse_iso_datetime(stage_state.get("started_at"))
    if started is None:
        return None
    return started + timedelta(seconds=STAGE_LEASE_SECONDS)


def stage_lease_is_live(stage_state: Any, *, now: datetime) -> bool:
    if not isinstance(stage_state, dict) or stage_state.get("status") != "RUNNING":
        return False
    expires_at = stage_lease_expires_at(stage_state)
    return expires_at is not None and now.astimezone(timezone.utc) < expires_at


def cycle_has_live_running_stage(value: Any, *, now: datetime) -> bool:
    """True only while some stage's lease is unexpired, i.e. a worker may still be alive."""
    if not isinstance(value, dict):
        return False
    stages = value.get("stages")
    if not isinstance(stages, dict):
        return False
    return any(stage_lease_is_live(stage_state, now=now) for stage_state in stages.values())


def cycle_publish_completed(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    stages = value.get("stages")
    if not isinstance(stages, dict):
        return False
    publish = stages.get("publish")
    return isinstance(publish, dict) and publish.get("status") == "COMPLETED"


def recovery_attempt_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    try:
        return max(0, int(value.get("recovery_attempts") or 0))
    except (TypeError, ValueError):
        return 0


def reset_unfinished_stage_attempts(
    state: dict[str, Any],
    *,
    recovery_cycle_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Give every non-COMPLETED stage a fresh attempt budget for a recovery cycle.

    COMPLETED stages keep their results (they are replayed as
    ALREADY_COMPLETED_TODAY unless their canonical output vanished). Attempt
    history is preserved compactly for diagnosis instead of being overwritten.
    """
    stages = state.get("stages")
    if not isinstance(stages, dict):
        stages = {}
        state["stages"] = stages
    for stage_state in stages.values():
        if not isinstance(stage_state, dict) or stage_state.get("status") == "COMPLETED":
            continue
        history = stage_state.get("previous_attempts")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "attempt_count": int(stage_state.get("attempt_count") or 0),
                "status": stage_state.get("status"),
                "error_code": stage_state.get("error_code"),
                "started_at": stage_state.get("started_at"),
                "completed_at": stage_state.get("completed_at"),
                "reset_by": recovery_cycle_id,
            }
        )
        stage_state["previous_attempts"] = history[-6:]
        stage_state["attempt_count"] = 0
        if stage_state.get("status") == "RUNNING":
            # The lease is expired (the caller verified), so the worker is gone.
            stage_state["status"] = "FAILED"
            stage_state["error_code"] = "COLLECTOR_STAGE_TIMEOUT"
            stage_state["error_message"] = "COLLECTOR_STAGE_TIMEOUT:lease_expired_before_recovery"
            stage_state["completed_at"] = now.astimezone(timezone.utc).isoformat()
    state["recovery_attempts"] = recovery_attempt_count(state) + 1
    state["recovery_cycle_id"] = recovery_cycle_id
    state["recovery_started_at"] = now.astimezone(timezone.utc).isoformat()
    return state


def write_collector_state(cache: Any, state: dict[str, Any], *, now: datetime) -> None:
    state["updated_at"] = now.astimezone(timezone.utc).isoformat()
    cache.set(META_KEY, state, {"ttl": STATE_TTL_SECONDS, "tags": [STATE_CACHE_TAG]})
