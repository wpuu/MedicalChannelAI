from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .ccgp_events import validate_notice_events
from .validation import validate_records


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _record_key(record: dict[str, Any]) -> str:
    project_number = str(record.get('facts', {}).get('project_number') or '').strip().lower()
    if project_number:
        return f'project:{project_number}'
    opportunity_id = str(record.get('opportunity_id') or '').strip()
    if not opportunity_id:
        raise ValueError('STATE_RECORD_KEY_REQUIRED')
    return f'opportunity:{opportunity_id}'


def merge_canonical_records(
    existing_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = validate_records(existing_records) if existing_records else []
    new = validate_records(new_records) if new_records else []
    merged: dict[str, dict[str, Any]] = {}
    for record in existing:
        merged[_record_key(record)] = record
    for record in new:
        merged[_record_key(record)] = record
    return validate_records(list(merged.values())) if merged else []


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
        facts = record.get('facts', {})
        project_number = str(facts.get('project_number') or '').strip()
        if not project_number:
            continue
        deadline = _as_datetime(facts.get('bid_deadline'))
        if deadline is None or deadline > as_of:
            active.add(project_number)
    return sorted(active)
