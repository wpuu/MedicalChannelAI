from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .ccgp_events import validate_notice_events
from .channel_scope import is_medical_channel_relevant_record
from .validation import validate_record, validate_records

LEGACY_DEFAULT_MARKET_CODE = 'TJ'


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def market_code_for_record(record: dict[str, Any]) -> str:
    value = str(record.get('facts', {}).get('market_code') or '').strip().upper()
    return value or LEGACY_DEFAULT_MARKET_CODE


def _record_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    market_code = market_code_for_record(record)
    project_number = str(record.get('facts', {}).get('project_number') or '').strip().lower()
    opportunity_id = str(record.get('opportunity_id') or '').strip()
    if not project_number and not opportunity_id:
        raise ValueError('STATE_RECORD_KEY_REQUIRED')
    return market_code, project_number, opportunity_id


def _same_record_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_market, left_project, left_opportunity = _record_identity(left)
    right_market, right_project, right_opportunity = _record_identity(right)
    if left_opportunity and right_opportunity and left_opportunity == right_opportunity:
        return True
    return bool(
        left_market == right_market
        and left_project
        and right_project
        and left_project == right_project
    )


def _reconcile_validated_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse overlapping canonical state in input order without cross-market merging."""
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
    *,
    market_code: str | None = None,
) -> list[str]:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    wanted_market = market_code.strip().upper() if market_code else None
    active: set[str] = set()
    for record in validate_records(records):
        source = record.get('source', {})
        if source.get('source_type') != 'CCGP_NOTICE':
            continue
        if wanted_market and market_code_for_record(record) != wanted_market:
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
