from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .source_precedence import (
    event_source_rank,
    event_time,
    latest_temporal_bucket,
    preferred_event,
)


EVENT_TO_STATE = {
    "MARKET_RESEARCH": "MARKET_RESEARCH",
    "PROCUREMENT_INTENT": "PROCUREMENT_INTENT",
    "INTERNAL_SELECTION": "PREPARING",
    "TENDER": "TENDERING",
    "AMENDMENT": "AMENDED",
    "SUSPENSION": "SUSPENDED",
    "TERMINATION": "TERMINATED",
    "AWARD": "AWARDED",
    "CONTRACT": "CONTRACTED",
    "OTHER": "UNKNOWN",
}

SAME_TIME_PRECEDENCE = {
    "UNKNOWN": 0,
    "MARKET_RESEARCH": 10,
    "PROCUREMENT_INTENT": 20,
    "PREPARING": 30,
    "TENDERING": 40,
    "AMENDED": 50,
    "SUSPENDED": 60,
    "TERMINATED": 70,
    "AWARDED": 80,
    "CONTRACTED": 90,
}


@dataclass(frozen=True)
class LifecycleAggregate:
    canonical_project_id: str
    lifecycle_state: str
    current_event_id: str
    source_event_ids: tuple[str, ...]
    verification_status: str
    latest_effective_at: str
    ignored_unverified_event_ids: tuple[str, ...]
    conflict_event_ids: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "canonical_project_id": self.canonical_project_id,
            "lifecycle_state": self.lifecycle_state,
            "current_event_id": self.current_event_id,
            "source_event_ids": list(self.source_event_ids),
            "verification_status": self.verification_status,
            "latest_effective_at": self.latest_effective_at,
            "ignored_unverified_event_ids": list(self.ignored_unverified_event_ids),
            "conflict_event_ids": list(self.conflict_event_ids),
        }


def _event_time(event: dict) -> str:
    return event_time(event)


def _state(event: dict) -> str:
    return EVENT_TO_STATE.get(event.get("event_type", "OTHER"), "UNKNOWN")


def _validate_event(event: dict) -> None:
    required = ("event_id", "canonical_project_id", "event_type", "verification_status")
    missing = [key for key in required if not event.get(key)]
    if missing:
        raise ValueError(f"event missing required fields: {', '.join(missing)}")
    if not _event_time(event):
        raise ValueError("event missing effective_at/published_at")


def _sorted_events(events: Iterable[dict]) -> list[dict]:
    return sorted(
        events,
        key=lambda event: (
            _event_time(event),
            SAME_TIME_PRECEDENCE.get(_state(event), 0),
            event_source_rank(event),
            event["event_id"],
        ),
    )


def resolve_project_lifecycle(events: Iterable[dict]) -> LifecycleAggregate:
    items = list(events)
    if not items:
        raise ValueError("at least one event is required")
    for event in items:
        _validate_event(event)

    project_ids = {event["canonical_project_id"] for event in items}
    if len(project_ids) != 1:
        raise ValueError("events from different canonical_project_id values cannot be auto-linked")
    canonical_project_id = next(iter(project_ids))

    verified = [event for event in items if event["verification_status"] == "VERIFIED"]
    ignored = tuple(event["event_id"] for event in items if event["verification_status"] != "VERIFIED")
    if not verified:
        latest_bucket = latest_temporal_bucket(items)
        latest = preferred_event(latest_bucket)
        return LifecycleAggregate(
            canonical_project_id=canonical_project_id,
            lifecycle_state="UNKNOWN",
            current_event_id=latest["event_id"],
            source_event_ids=tuple(event["event_id"] for event in _sorted_events(items)),
            verification_status="UNVERIFIED",
            latest_effective_at=_event_time(latest),
            ignored_unverified_event_ids=ignored,
            conflict_event_ids=(),
        )

    latest_events = latest_temporal_bucket(verified)
    latest_states = {_state(event) for event in latest_events}

    conflict_ids: tuple[str, ...] = ()
    verification_status = "VERIFIED"
    if len(latest_states) > 1:
        conflict_ids = tuple(sorted(event["event_id"] for event in latest_events))
        verification_status = "CONFLICTED"

    if verification_status == "VERIFIED":
        current = preferred_event(latest_events)
        lifecycle_state = _state(current)
    else:
        # Do not resolve a contradictory low-precision same-day lifecycle by guessing
        # chronology. Keep a deterministic evidence pointer while exposing UNKNOWN.
        current = preferred_event(latest_events)
        lifecycle_state = "UNKNOWN"

    latest_effective_at = max(_event_time(event) for event in latest_events)
    return LifecycleAggregate(
        canonical_project_id=canonical_project_id,
        lifecycle_state=lifecycle_state,
        current_event_id=current["event_id"],
        source_event_ids=tuple(event["event_id"] for event in _sorted_events(verified)),
        verification_status=verification_status,
        latest_effective_at=latest_effective_at,
        ignored_unverified_event_ids=ignored,
        conflict_event_ids=conflict_ids,
    )


def group_and_resolve_lifecycles(events: Iterable[dict]) -> list[LifecycleAggregate]:
    groups: dict[str, list[dict]] = {}
    for event in events:
        _validate_event(event)
        groups.setdefault(event["canonical_project_id"], []).append(event)
    return [resolve_project_lifecycle(groups[key]) for key in sorted(groups)]
