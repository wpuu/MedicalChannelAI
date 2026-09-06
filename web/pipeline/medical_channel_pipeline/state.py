from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .ccgp_events import validate_notice_events
from .channel_scope import is_medical_channel_relevant_record
from .validation import validate_record, validate_records


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _record_identity(record: dict[str, Any]) -> tuple[str, str]:
    project_number = str(record.get('facts', {}).get('project_number') or '').strip().lower()
    opportunity_id = str(record.get('opportunity_id') or '').strip()
    if not project_number and not opportunity_id:
        raise ValueError('STATE_RECORD_KEY_REQUIRED')
    return project_number, opportunity_id


def _same_record_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_project, left_opportunity = _record_identity(left)
    right_project, right_opportunity = _record_identity(right)
    return bool(
        (left_project and right_project and left_project == right_project)
        or (
            left_opportunity
            and right_opportunity
            and left_opportunity == right_opportunity
        )
    )


def _reconcile_validated_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse overlapping canonical state in input order.

    Callers intentionally pass state from oldest/base to newest/current. Later
    verified records therefore replace earlier seed/live copies while the first
    canonical slot is retained for stable ordering. Matching by either project
    number or opportunity id also repairs legacy identity drift before the final
    collection-level duplicate validation runs.
    """
    merged: list[dict[str, Any]] = []
    for record in records:
        matching_indexes = [
            index
            for index, current in enumerate(merged)
            if _same_record_identity(current, record)
        ]
        if not matching_indexes:
            merged.append(record)
            continue

        first = matching_indexes[0]
        merged[first] = record
        for index in reversed(matching_indexes[1:]):
            del merged[index]
    return merged


def merge_canonical_records(
    existing_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Validate each record before reconciliation, but deliberately defer
    # collection-level duplicate checks until after identity repair. Existing
    # state may legitimately overlap because the refresh workflow layers a
    # verified seed below the latest live state; new verified records are then
    # applied last. This also lets a newer record heal legacy malformed ids.
    existing = [validate_record(record) for record in existing_records] if existing_records else []
    new = [validate_record(record) for record in new_records] if new_records else []
    merged = _reconcile_validated_records([*existing, *new])
    return validate_records(merged) if merged else []


def merge_notice_events(
    existing_events: list[dict[str, Any]],
    new_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = validate_notice_events(existing_events) if existing_events else []
    new = validate_notice_events(new_events) if new_events else []
    merged = {event['event_id']: event for event in existing}
    for event in new:
        merged[event['event_id']] = event
    return validate_notice_events(list(merged.values())) if merged else []


def active_ccgp_project_numbers(
    records: list[dict[str, Any]],
    as_of: datetime,
) -> list[str]:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    active: set[str] = set()
    for record in validate_records(records):
        source = record.get('source', {})
        if source.get('source_type') != 'CCGP_NOTICE':
            continue
        if not is_medical_channel_relevant_record(record):
            continue
        facts = record.get('facts', {})
        project_number = str(facts.get('project_number') or '').strip()
        if not project_number:
            continue
        deadline = _as_datetime(facts.get('bid_deadline'))
        if deadline is None or deadline > as_of:
            active.add(project_number)
    return sorted(active)
