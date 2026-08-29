from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
MORNING_DIGEST = time(8, 10)
MIDDAY_DELTA = time(13, 15)
IMMEDIATE_START = time(8, 30)
IMMEDIATE_END = time(18, 30)
EVENING_URGENT_END = time(21, 30)
WEEKEND_URGENT_START = time(9, 30)
WEEKEND_URGENT_END = time(18, 0)
CRITICAL_EVENT_TYPES = {"TERMINATION_PUBLISHED", "SUSPENSION_PUBLISHED", "DEADLINE_CHANGED"}


@dataclass(frozen=True)
class NotificationTimeDecision:
    timing_status: str
    scheduled_for: str | None
    delivery_window: str
    urgent_exception: bool
    reason: str

    def as_dict(self) -> dict:
        return {
            "schema_version": "0.1",
            "timing_status": self.timing_status,
            "scheduled_for": self.scheduled_for,
            "delivery_window": self.delivery_window,
            "urgent_exception": self.urgent_exception,
            "reason": self.reason,
        }


def _is_business_day(day: date, holiday_dates: set[str], forced_workdays: set[str]) -> bool:
    key = day.isoformat()
    if key in forced_workdays:
        return True
    if key in holiday_dates:
        return False
    return day.weekday() < 5


def _at(day: date, value: time) -> datetime:
    return datetime.combine(day, value, tzinfo=TZ)


def _next_business_morning(
    local_now: datetime,
    holiday_dates: set[str],
    forced_workdays: set[str],
    *,
    include_today: bool,
) -> datetime:
    day = local_now.date() if include_today else local_now.date() + timedelta(days=1)
    for _ in range(14):
        if _is_business_day(day, holiday_dates, forced_workdays):
            candidate = _at(day, MORNING_DIGEST)
            if candidate > local_now:
                return candidate
        day += timedelta(days=1)
    raise ValueError("unable to find next business morning within 14 days")


def _deadline_hours(local_now: datetime, action_deadline: datetime | None) -> float | None:
    if action_deadline is None:
        return None
    if action_deadline.tzinfo is None:
        raise ValueError("action_deadline must be timezone-aware")
    return (action_deadline.astimezone(TZ) - local_now).total_seconds() / 3600


def plan_notification_time(
    routing_result: dict,
    *,
    now: datetime,
    event_type: str | None = None,
    action_deadline: datetime | None = None,
    holiday_dates: set[str] | None = None,
    forced_workdays: set[str] | None = None,
) -> NotificationTimeDecision:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    holiday_dates = holiday_dates or set()
    forced_workdays = forced_workdays or set()
    local = now.astimezone(TZ)

    if not routing_result.get("should_notify"):
        return NotificationTimeDecision("NO_NOTIFY", None, "NONE", False, "routing layer suppressed notification")

    routing_status = routing_result.get("routing_status")
    if routing_status not in {"SEND_IMMEDIATE", "INCLUDE_DAILY_DIGEST"}:
        raise ValueError(f"unsupported routing_status for timing: {routing_status}")

    hours = _deadline_hours(local, action_deadline)
    urgent = event_type in CRITICAL_EVENT_TYPES or (hours is not None and 0 <= hours <= 16)
    business_day = _is_business_day(local.date(), holiday_dates, forced_workdays)
    current_time = local.timetz().replace(tzinfo=None)

    if routing_status == "INCLUDE_DAILY_DIGEST":
        if business_day and local < _at(local.date(), MORNING_DIGEST):
            target = _at(local.date(), MORNING_DIGEST)
            return NotificationTimeDecision("SCHEDULED", target.isoformat(), "MORNING_DIGEST", False, "overnight/early discovery enters same-day morning digest")
        if business_day and local < _at(local.date(), time(12, 50)):
            target = _at(local.date(), MIDDAY_DELTA)
            return NotificationTimeDecision("SCHEDULED", target.isoformat(), "MIDDAY_DELTA", False, "non-urgent morning discovery enters one same-day delta digest")
        target = _next_business_morning(local, holiday_dates, forced_workdays, include_today=False)
        return NotificationTimeDecision("SCHEDULED", target.isoformat(), "NEXT_BUSINESS_MORNING", False, "ordinary afternoon/evening discovery is prepared silently for the next business morning")

    if business_day and IMMEDIATE_START <= current_time < IMMEDIATE_END:
        return NotificationTimeDecision("SEND_NOW", local.isoformat(), "WORKDAY_IMMEDIATE", False, "high-priority verified event arrived during action hours")

    if business_day and IMMEDIATE_END <= current_time < EVENING_URGENT_END and urgent:
        return NotificationTimeDecision("SEND_NOW", local.isoformat(), "EVENING_URGENT_EXCEPTION", True, "time-sensitive termination/suspension/deadline event warrants limited evening interruption")

    if not business_day and WEEKEND_URGENT_START <= current_time < WEEKEND_URGENT_END and urgent:
        return NotificationTimeDecision("SEND_NOW", local.isoformat(), "WEEKEND_URGENT_EXCEPTION", True, "time-sensitive event warrants bounded weekend interruption")

    target = _next_business_morning(local, holiday_dates, forced_workdays, include_today=business_day and current_time < MORNING_DIGEST)
    return NotificationTimeDecision("SCHEDULED", target.isoformat(), "NEXT_BUSINESS_MORNING", False, "high priority but not action-urgent outside normal action hours; queue for next business morning")
