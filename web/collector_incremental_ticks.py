from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
TICK_INTERVAL_MINUTES = 15
BUSINESS_WINDOW_START = time(11, 30)
BUSINESS_WINDOW_END = time(19, 0)
MAX_TICKS_PER_DAY = 31


@dataclass(frozen=True)
class IncrementalTick:
    business_date: str
    scheduled_for: str
    tick_id: str
    sequence: int


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("INCREMENTAL_TICK_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def same_china_business_date(left: datetime, right: datetime) -> bool:
    return (
        _aware_utc(left).astimezone(SHANGHAI).date()
        == _aware_utc(right).astimezone(SHANGHAI).date()
    )


def _business_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, BUSINESS_WINDOW_START, tzinfo=SHANGHAI)
    end = datetime.combine(day, BUSINESS_WINDOW_END, tzinfo=SHANGHAI)
    return start, end


def _ceil_to_tick(value: datetime, start: datetime) -> datetime:
    if value <= start:
        return start
    elapsed_seconds = (value - start).total_seconds()
    interval_seconds = TICK_INTERVAL_MINUTES * 60
    slots = int((elapsed_seconds + interval_seconds - 1) // interval_seconds)
    return start + timedelta(seconds=slots * interval_seconds)


def _tick_sequence(scheduled_local: datetime, start: datetime) -> int:
    return int((scheduled_local - start).total_seconds() // (TICK_INTERVAL_MINUTES * 60)) + 1


def _build_tick(scheduled_local: datetime) -> IncrementalTick:
    start, end = _business_bounds(scheduled_local.date())
    if scheduled_local < start or scheduled_local > end:
        raise ValueError("INCREMENTAL_TICK_OUTSIDE_BUSINESS_WINDOW")
    sequence = _tick_sequence(scheduled_local, start)
    if sequence < 1 or sequence > MAX_TICKS_PER_DAY:
        raise ValueError("INCREMENTAL_TICK_SEQUENCE_INVALID")
    day = scheduled_local.date().isoformat()
    compact = scheduled_local.strftime("%Y%m%dT%H%M")
    return IncrementalTick(
        business_date=day,
        scheduled_for=scheduled_local.astimezone(timezone.utc).isoformat(),
        tick_id=f"incremental-tick:{compact}+0800:{sequence:02d}",
        sequence=sequence,
    )


def first_tick_after_deep(completed_at: datetime) -> IncrementalTick | None:
    current_local = _aware_utc(completed_at).astimezone(SHANGHAI)
    start, end = _business_bounds(current_local.date())
    if current_local > end:
        return None
    scheduled = _ceil_to_tick(max(current_local, start), start)
    return _build_tick(scheduled) if scheduled <= end else None


def next_tick_after(
    current_tick: IncrementalTick,
    *,
    delivered_at: datetime,
) -> IncrementalTick | None:
    delivered_local = _aware_utc(delivered_at).astimezone(SHANGHAI)
    try:
        day = date.fromisoformat(current_tick.business_date)
    except ValueError:
        return None
    if delivered_local.date() != day:
        return None

    start, end = _business_bounds(day)
    current_scheduled = parse_tick_schedule(current_tick)
    if current_scheduled is None:
        return None
    current_local = current_scheduled.astimezone(SHANGHAI)

    # Preserve the nominal cadence while delivery remains before the next slot.
    # Once a tick is materially late, skip backlog and schedule the first aligned
    # slot strictly after the actual delivery time. This avoids both replay bursts
    # and a zero-delay duplicate when a late delivery lands exactly on an aligned
    # tick boundary.
    nominal_next = current_local + timedelta(minutes=TICK_INTERVAL_MINUTES)
    if delivered_local <= nominal_next:
        scheduled = nominal_next
    else:
        scheduled = _ceil_to_tick(delivered_local, start)
        if scheduled <= delivered_local:
            scheduled += timedelta(minutes=TICK_INTERVAL_MINUTES)
    return _build_tick(scheduled) if scheduled <= end else None


def parse_tick_schedule(tick: IncrementalTick) -> datetime | None:
    try:
        scheduled = datetime.fromisoformat(tick.scheduled_for.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if scheduled.tzinfo is None:
        return None
    scheduled_local = scheduled.astimezone(SHANGHAI)
    try:
        expected = _build_tick(scheduled_local)
    except ValueError:
        return None
    if (
        expected.business_date != tick.business_date
        or expected.tick_id != tick.tick_id
        or expected.sequence != tick.sequence
    ):
        return None
    return scheduled.astimezone(timezone.utc)


def tick_from_payload(payload: object) -> IncrementalTick | None:
    if not isinstance(payload, dict):
        return None
    business_date = payload.get("business_date")
    scheduled_for = payload.get("scheduled_for")
    tick_id = payload.get("tick_id")
    sequence = payload.get("sequence")
    if not all(isinstance(value, str) and value.strip() for value in (business_date, scheduled_for, tick_id)):
        return None
    if not isinstance(sequence, int):
        return None
    tick = IncrementalTick(
        business_date=business_date.strip(),
        scheduled_for=scheduled_for.strip(),
        tick_id=tick_id.strip(),
        sequence=sequence,
    )
    return tick if parse_tick_schedule(tick) is not None else None


def tick_delay_seconds(tick: IncrementalTick, *, now: datetime) -> int:
    scheduled = parse_tick_schedule(tick)
    if scheduled is None:
        raise ValueError("INCREMENTAL_TICK_INVALID")
    current = _aware_utc(now)
    return max(0, int((scheduled - current).total_seconds()))
