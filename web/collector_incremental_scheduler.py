from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from collector_incremental import SOURCE_POLICIES, scan_bucket_id


SCHEDULED_INCREMENTAL_SOURCES = (
    "tjmugh",
    "tjnothop",
    "tjfch",
    "tjfch_test",
    "teda",
)
ATTEMPT_TTL_SECONDS = 3 * 24 * 60 * 60


@dataclass(frozen=True)
class IncrementalScheduleDecision:
    source_id: str | None
    reason: str
    evaluated_at: str
    next_due_at: str | None
    due_sources: tuple[str, ...]


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("INCREMENTAL_SCHEDULER_TIMEZONE_REQUIRED")
    return current.astimezone(timezone.utc)


def _bucket_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-bucket:{source_id}:v2"


def _attempt_key(source_id: str) -> str:
    return f"medicalchannelai:collector-incremental-attempt:{source_id}:v2"


def _parsed_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _last_completed(cache: Any, source_id: str) -> tuple[str | None, datetime | None]:
    value = cache.get(_bucket_key(source_id))
    if not isinstance(value, dict):
        return None, None
    bucket_id = str(value.get("bucket_id") or "").strip() or None
    completed_at = _parsed_at(value.get("completed_at"))
    return bucket_id, completed_at


def _last_attempted(cache: Any, source_id: str) -> datetime | None:
    value = cache.get(_attempt_key(source_id))
    if not isinstance(value, dict):
        return None
    return _parsed_at(value.get("attempted_at"))


def _mark_attempt(cache: Any, source_id: str, *, now: datetime) -> None:
    cache.set(
        _attempt_key(source_id),
        {
            "schema_version": "0.1",
            "source_id": source_id,
            "attempted_at": now.isoformat(),
            "bucket_id": scan_bucket_id(source_id, now=now),
        },
        {
            "ttl": ATTEMPT_TTL_SECONDS,
            "tags": ["medicalchannelai-collector-incremental-attempt"],
        },
    )


def choose_due_incremental_source(
    cache: Any,
    *,
    now: datetime | None = None,
) -> IncrementalScheduleDecision:
    current = _utc(now)
    due: list[tuple[int, float, str]] = []
    next_due_times: list[datetime] = []

    for order, source_id in enumerate(SCHEDULED_INCREMENTAL_SOURCES):
        policy = SOURCE_POLICIES[source_id]
        interval = timedelta(minutes=int(policy["scan_interval_minutes"]))
        last_bucket, completed_at = _last_completed(cache, source_id)
        attempted_at = _last_attempted(cache, source_id)
        current_bucket = scan_bucket_id(source_id, now=current)

        # A selected source is marked as attempted before it is returned. The
        # Queue itself still performs its bounded retries, but a source that keeps
        # failing cannot be selected again by every 10-minute scheduler tick and
        # starve all later sources. After one source interval it becomes eligible
        # again in a new bucket.
        if completed_at is None:
            if attempted_at is None:
                due.append((order, float("inf"), source_id))
                continue
            retry_due = attempted_at + interval
            next_due_times.append(retry_due)
            if current >= retry_due:
                due.append(
                    (
                        order,
                        max(0.0, (current - retry_due).total_seconds()),
                        source_id,
                    )
                )
            continue

        baseline = completed_at
        if attempted_at is not None and attempted_at > baseline:
            baseline = attempted_at
        next_due = baseline + interval
        next_due_times.append(next_due)
        bucket_advanced = last_bucket != current_bucket
        if bucket_advanced and current >= next_due:
            overdue_seconds = max(0.0, (current - next_due).total_seconds())
            due.append((order, overdue_seconds, source_id))

    if due:
        # Never-attempted sources have infinite overdue and are introduced one at
        # a time in deterministic order. Otherwise pick the most overdue source;
        # source order only breaks ties.
        due.sort(key=lambda item: (-item[1], item[0]))
        selected = due[0][2]
        _mark_attempt(cache, selected, now=current)
        return IncrementalScheduleDecision(
            source_id=selected,
            reason="SOURCE_DUE",
            evaluated_at=current.isoformat(),
            next_due_at=current.isoformat(),
            due_sources=tuple(item[2] for item in due),
        )

    next_due = min(next_due_times) if next_due_times else None
    return IncrementalScheduleDecision(
        source_id=None,
        reason="NO_SOURCE_DUE",
        evaluated_at=current.isoformat(),
        next_due_at=next_due.isoformat() if next_due else None,
        due_sources=(),
    )
