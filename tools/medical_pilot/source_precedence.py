from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .registry import RegisteredSource, load_registry


PROVENANCE_RANK = {
    "DISCOVERY_ONLY": 10,
    "OFFICIAL_MIRROR": 20,
    "PRIMARY_SOURCE": 30,
}


def source_rank(source_id: str | None, registry: Iterable[RegisteredSource] | None = None) -> int:
    if not source_id:
        return 0
    sources = list(registry) if registry is not None else load_registry()
    for source in sources:
        if source.source_id == source_id:
            return PROVENANCE_RANK.get(source.provenance_role, 0)
    return 0


def event_source_rank(event: dict, registry: Iterable[RegisteredSource] | None = None) -> int:
    return source_rank(event.get("source_id"), registry)


def event_precision(event: dict) -> str:
    value = str(event.get("published_at_precision") or "MINUTE").upper()
    return value if value in {"MINUTE", "DAY", "UNKNOWN"} else "UNKNOWN"


def event_time(event: dict) -> str:
    return event.get("effective_at") or event.get("published_at") or ""


def event_day(event: dict) -> str:
    value = event_time(event)
    return value[:10] if len(value) >= 10 else value


def latest_temporal_bucket(events: Iterable[dict]) -> list[dict]:
    """Return the latest events without inventing chronology from low-precision dates.

    If every event on the latest calendar day has MINUTE precision, exact timestamps
    can safely select the latest instant. If any event on that day is only DAY/UNKNOWN
    precision, all events on the day remain in the latest bucket. This deliberately
    turns contradictory same-day lifecycle states into a conflict instead of pretending
    that a normalized 00:00 timestamp happened before a mirror's precise clock time.
    """

    items = list(events)
    if not items:
        return []
    latest_day = max(event_day(event) for event in items)
    day_items = [event for event in items if event_day(event) == latest_day]
    if day_items and all(event_precision(event) == "MINUTE" for event in day_items):
        latest_time = max(event_time(event) for event in day_items)
        return [event for event in day_items if event_time(event) == latest_time]
    return day_items


def preferred_event(events: Iterable[dict], registry: Iterable[RegisteredSource] | None = None) -> dict:
    items = list(events)
    if not items:
        raise ValueError("at least one event is required")
    sources = list(registry) if registry is not None else load_registry()
    return max(
        items,
        key=lambda event: (
            event_source_rank(event, sources),
            event_precision(event) == "MINUTE",
            event_time(event),
            event.get("event_id", ""),
        ),
    )
