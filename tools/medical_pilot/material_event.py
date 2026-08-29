from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from .collector_core import SCHEMA_VERSION


ALLOWED_MATERIAL_EVENT_TYPES = {
    "NEW_VERIFIED_OPPORTUNITY",
    "LIFECYCLE_STATE_CHANGED",
    "DEADLINE_CHANGED",
    "AWARD_PUBLISHED",
}


class MaterialEventError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_aware_datetime(value: str, field_name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise MaterialEventError("TIMESTAMP_INVALID", f"invalid {field_name}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MaterialEventError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field_name} must include timezone")


def _verified_fact_index(facts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fact_id = fact.get("fact_id")
        if not isinstance(fact_id, str) or not fact_id:
            continue
        if fact.get("fact_type") != "OFFICIAL_PUBLIC_FACT":
            continue
        if fact.get("verification_status") != "VERIFIED":
            continue
        if fact.get("model_generated") is not False:
            continue
        result[fact_id] = fact
    return result


def _semantic_payload(opportunity_id: str, event_type: str, change_fields: dict[str, str]) -> str:
    # Publication/effective timestamps are evidence metadata, not material-event
    # identity. Mirrors may report the same semantic change at different clock
    # precision. Identity therefore uses only canonical opportunity + event type +
    # normalized business change fields.
    payload = {
        "opportunity_id": opportunity_id,
        "event_type": event_type,
        "change_fields": {key: change_fields[key] for key in sorted(change_fields)},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(opportunity_id: str, event_type: str, change_fields: dict[str, str]) -> str:
    return hashlib.sha256(_semantic_payload(opportunity_id, event_type, change_fields).encode("utf-8")).hexdigest()


def validate_material_event_envelope(event: dict[str, Any]) -> dict[str, Any]:
    """Validate a persisted material-event envelope before subscription dispatch."""

    if not isinstance(event, dict):
        raise MaterialEventError("EVENT_NOT_OBJECT", "material event must be an object")
    if event.get("schema_version") != SCHEMA_VERSION:
        raise MaterialEventError("SCHEMA_VERSION_INVALID", "material event schema_version must be 0.1")
    if event.get("verification_status") != "VERIFIED" or event.get("model_generated") is not False:
        raise MaterialEventError("EVENT_NOT_VERIFIED", "subscription dispatch requires VERIFIED non-model material event")

    opportunity_id = event.get("opportunity_id")
    event_type = event.get("event_type")
    change_fields = event.get("change_fields")
    if not isinstance(opportunity_id, str) or not opportunity_id:
        raise MaterialEventError("OPPORTUNITY_ID_REQUIRED", "opportunity_id is required")
    if event_type not in ALLOWED_MATERIAL_EVENT_TYPES:
        raise MaterialEventError("EVENT_TYPE_INVALID", str(event_type))
    if not isinstance(change_fields, dict) or not change_fields:
        raise MaterialEventError("CHANGE_FIELDS_REQUIRED", "material event needs change_fields")
    if any(not isinstance(key, str) or not key or not isinstance(value, str) or not value for key, value in change_fields.items()):
        raise MaterialEventError("CHANGE_FIELD_INVALID", "change_fields must contain non-empty strings")

    detected_at = event.get("detected_at")
    if not isinstance(detected_at, str) or not detected_at:
        raise MaterialEventError("DETECTED_AT_REQUIRED", "detected_at is required")
    _require_aware_datetime(detected_at, "detected_at")
    precision = event.get("official_effective_at_precision")
    effective_at = event.get("official_effective_at")
    if precision not in {"DAY", "MINUTE", "SECOND", "UNKNOWN"}:
        raise MaterialEventError("EFFECTIVE_PRECISION_INVALID", str(precision))
    if effective_at is not None:
        if not isinstance(effective_at, str):
            raise MaterialEventError("TIMESTAMP_INVALID", "official_effective_at must be string or null")
        _require_aware_datetime(effective_at, "official_effective_at")
    elif precision != "UNKNOWN":
        raise MaterialEventError("EFFECTIVE_TIME_REQUIRED", "known precision requires official_effective_at")

    supporting_fact_ids = event.get("supporting_fact_ids")
    if not isinstance(supporting_fact_ids, list) or not supporting_fact_ids or any(not isinstance(item, str) or not item for item in supporting_fact_ids):
        raise MaterialEventError("SUPPORTING_FACTS_REQUIRED", "material event must retain supporting_fact_ids")

    digest = _digest(opportunity_id, event_type, change_fields)
    if event.get("material_event_id") != "mevt_" + digest:
        raise MaterialEventError("MATERIAL_EVENT_ID_MISMATCH", "material_event_id does not match semantic payload")
    if event.get("idempotency_key") != "mat_" + digest:
        raise MaterialEventError("IDEMPOTENCY_KEY_MISMATCH", "idempotency_key does not match semantic payload")
    return event


def build_material_event(
    *,
    opportunity: dict[str, Any],
    event_type: str,
    change_fields: dict[str, str],
    supporting_fact_ids: list[str],
    available_facts: list[dict[str, Any]],
    source_event_ids: list[str] | None,
    detected_at: str,
    official_effective_at: str | None,
    official_effective_at_precision: str,
) -> dict[str, Any]:
    """Build one idempotent material event only from VERIFIED official facts.

    Event identity is semantic: adding mirror evidence or improving publication-time
    precision does not create another material event when the business change itself
    is unchanged. Every change field must be backed by a supplied VERIFIED official
    fact with the same field name/value.
    """

    if event_type not in ALLOWED_MATERIAL_EVENT_TYPES:
        raise MaterialEventError("EVENT_TYPE_INVALID", event_type)
    opportunity_id = opportunity.get("opportunity_id")
    if not isinstance(opportunity_id, str) or not opportunity_id:
        raise MaterialEventError("OPPORTUNITY_ID_REQUIRED", "opportunity_id is required")
    if opportunity.get("verification_status") != "VERIFIED":
        raise MaterialEventError("OPPORTUNITY_NOT_VERIFIED", "material events require a VERIFIED opportunity")
    if not isinstance(change_fields, dict) or not change_fields:
        raise MaterialEventError("CHANGE_FIELDS_REQUIRED", "at least one semantic change field is required")
    if any(not isinstance(key, str) or not key or not isinstance(value, str) or not value for key, value in change_fields.items()):
        raise MaterialEventError("CHANGE_FIELD_INVALID", "change_fields must contain non-empty string names and values")
    if official_effective_at_precision not in {"DAY", "MINUTE", "SECOND", "UNKNOWN"}:
        raise MaterialEventError("EFFECTIVE_PRECISION_INVALID", official_effective_at_precision)
    if not isinstance(detected_at, str) or not detected_at:
        raise MaterialEventError("DETECTED_AT_REQUIRED", "detected_at is required")
    _require_aware_datetime(detected_at, "detected_at")
    if official_effective_at is not None:
        _require_aware_datetime(official_effective_at, "official_effective_at")
    elif official_effective_at_precision != "UNKNOWN":
        raise MaterialEventError("EFFECTIVE_TIME_REQUIRED", "known precision requires official_effective_at")

    fact_index = _verified_fact_index(available_facts)
    unique_fact_ids = list(dict.fromkeys(supporting_fact_ids))
    if not unique_fact_ids:
        raise MaterialEventError("SUPPORTING_FACTS_REQUIRED", "at least one supporting fact is required")
    missing = [fact_id for fact_id in unique_fact_ids if fact_id not in fact_index]
    if missing:
        raise MaterialEventError("SUPPORTING_FACT_NOT_VERIFIED", f"unsupported fact ids: {', '.join(missing)}")

    supported_pairs = {
        (str(fact.get("field_name") or ""), str(fact.get("field_value") or ""))
        for fact_id, fact in fact_index.items()
        if fact_id in unique_fact_ids
    }
    unsupported_changes = [
        field_name
        for field_name, field_value in change_fields.items()
        if (field_name, field_value) not in supported_pairs
    ]
    if unsupported_changes:
        raise MaterialEventError(
            "CHANGE_NOT_GROUNDED",
            f"change fields are not backed by supplied VERIFIED official facts: {', '.join(unsupported_changes)}",
        )

    if event_type == "LIFECYCLE_STATE_CHANGED" and "lifecycle_state" not in change_fields:
        raise MaterialEventError("LIFECYCLE_STATE_REQUIRED", "lifecycle change requires lifecycle_state")
    if event_type == "DEADLINE_CHANGED" and not any("deadline" in key.lower() or "closing" in key.lower() for key in change_fields):
        raise MaterialEventError("DEADLINE_FIELD_REQUIRED", "deadline change requires a deadline/closing field")
    if event_type == "AWARD_PUBLISHED" and change_fields.get("lifecycle_state") != "AWARDED":
        raise MaterialEventError("AWARD_STATE_REQUIRED", "award event requires lifecycle_state=AWARDED")

    digest = _digest(opportunity_id, event_type, change_fields)
    source_ids = list(dict.fromkeys(item for item in (source_event_ids or []) if isinstance(item, str) and item))
    event = {
        "schema_version": SCHEMA_VERSION,
        "material_event_id": "mevt_" + digest,
        "opportunity_id": opportunity_id,
        "event_type": event_type,
        "verification_status": "VERIFIED",
        "model_generated": False,
        "change_fields": dict(sorted(change_fields.items())),
        "supporting_fact_ids": unique_fact_ids,
        "source_event_ids": source_ids,
        "detected_at": detected_at,
        "official_effective_at": official_effective_at,
        "official_effective_at_precision": official_effective_at_precision,
        "idempotency_key": "mat_" + digest,
    }
    return validate_material_event_envelope(event)
