from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from collector_namespace import AUTOMATION_HEALTH_KEY


PUBLIC_FIELDS = (
    "last_deep_trigger_at",
    "last_deep_cycle_id",
    "last_deep_completed_at",
    "last_deep_snapshot_as_of",
    "last_chain_schedule_attempt_at",
    "last_chain_schedule_status",
    "last_chain_tick_id",
    "last_tick_delivered_at",
    "last_tick_id",
    "last_tick_selected_source",
    "last_source_scan_at",
    "last_source_id",
    "last_source_action",
    "last_source_error",
    "last_intraday_snapshot_as_of",
    "updated_at",
)


def update_automation_health(cache: Any, **fields: Any) -> dict[str, Any]:
    current = cache.get(AUTOMATION_HEALTH_KEY)
    payload = dict(current) if isinstance(current, dict) else {"schema_version": "0.1"}
    for key, value in fields.items():
        if key in PUBLIC_FIELDS:
            payload[key] = value
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    cache.set(
        AUTOMATION_HEALTH_KEY,
        payload,
        {},
    )
    return payload


def public_automation_health(cache: Any) -> dict[str, Any]:
    value = cache.get(AUTOMATION_HEALTH_KEY)
    if not isinstance(value, dict):
        return {"schema_version": "0.1", **{field: None for field in PUBLIC_FIELDS}}
    return {
        "schema_version": "0.1",
        **{field: value.get(field) for field in PUBLIC_FIELDS},
    }
