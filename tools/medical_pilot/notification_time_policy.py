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
MATERIAL_EVENT_TYPES = {"NEW_VERIFIED_OPPORTUNITY", "LIFECYCLE_STATE_CHANGED", "DEADLINE_CHANGED", "AWARD_PUBLISHED"}
URGENT_LIFECYCLE_STATES = {"TERMINATED", "SUSPENDED"}

@dataclass(frozen=True)
class NotificationTimeDecision:
    timing_status: str
    scheduled_for: str | None
    delivery_window: str
    urgent_exception: bool
    reason: str

    def as_dict(self) -> dict:
        return {"schema_version": "0.1", "timing_status": self.timing_status, "scheduled_for": self.scheduled_for, "delivery_window": self.delivery_window, "urgent_exception": self.urgent_exception, "reason": self.reason}

def _is_business_day(day: date, holiday_dates: set[str], forced_workdays: set[str]) -> bool:
    key = day.isoformat()
    if key in forced_workdays:
        return True
    if key in holiday_dates:
        return False
    return day.weekday() < 5

def _at(day: date, value: time) -> datetime:
    return datetime.combine(day, value, tzinfo=TZ)

def _next_business_morning(local_now: datetime, holiday_dates: set[str], forced_workdays: set[str]) -> datetime:
    day = local_now.date() + timedelta(days=1)
    for _ in range(14):
        if _is_business_day(day, holiday_dates, forced_workdays):
            return _at(day, MORNING_DIGEST)
        day += timedelta(days=1)
    raise ValueError("unable to find next business morning within 14 days")

def _deadline_hours(local_now: datetime, action_deadline: datetime | None) -> float | None:
    if action_deadline is None:
        return None
    if action_deadline.tzinfo is None:
        raise ValueError("action_deadline must be timezone-aware")
    return (action_deadline.astimezone(TZ) - local_now).total_seconds() / 3600

def _urgent(event_type: str | None, change_fields: dict | None, deadline_hours: float | None) -> bool:
    if event_type is not None and event_type not in MATERIAL_EVENT_TYPES:
        raise ValueError(f"unsupported material event type: {event_type}")
    if deadline_hours is not None and 0 <= deadline_hours <= 16:
        return True
    if event_type == "DEADLINE_CHANGED":
        return True
    if event_type == "LIFECYCLE_STATE_CHANGED":
        return str((change_fields or {}).get("lifecycle_state") or "").upper() in URGENT_LIFECYCLE_STATES
    return False

def plan_notification_time(routing_result: dict, *, now: datetime, event_type: str | None = None, change_fields: dict | None = None, action_deadline: datetime | None = None, holiday_dates: set[str] | None = None, forced_workdays: set[str] | None = None) -> NotificationTimeDecision:
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
    urgent = _urgent(event_type, change_fields, _deadline_hours(local, action_deadline))
    business_day = _is_business_day(local.date(), holiday_dates, forced_workdays)
    current_time = local.time().replace(tzinfo=None)
    if routing_status == "INCLUDE_DAILY_DIGEST":
        if business_day and current_time < MORNING_DIGEST:
            target = _at(local.date(), MORNING_DIGEST)
            return NotificationTimeDecision("SCHEDULED", target.isoformat(), "MORNING_DIGEST", False, "early discovery enters same-day morning digest")
        if business_day and current_time < time(12, 50):
            target = _at(local.date(), MIDDAY_DELTA)
            return NotificationTimeDecision("SCHEDULED", target.isoformat(), "MIDDAY_DELTA", False, "morning discovery enters one same-day delta digest")
        target = _next_business_morning(local, holiday_dates, forced_workdays)
        return NotificationTimeDecision("SCHEDULED", target.isoformat(), "NEXT_BUSINESS_MORNING", False, "ordinary afternoon/evening discovery is prepared silently for the next business morning")
    if business_day and current_time < IMMEDIATE_START:
        target = _at(local.date(), IMMEDIATE_START)
        return NotificationTimeDecision("SCHEDULED", target.isoformat(), "WORKDAY_OPEN", urgent, "high-priority event arrived before action hours")
    if business_day and IMMEDIATE_START <= current_time < IMMEDIATE_END:
        return NotificationTimeDecision("SEND_NOW", local.isoformat(), "WORKDAY_IMMEDIATE", False, "high-priority verified event arrived during action hours")
    if business_day and IMMEDIATE_END <= current_time < EVENING_URGENT_END and urgent:
        return NotificationTimeDecision("SEND_NOW", local.isoformat(), "EVENING_URGENT_EXCEPTION", True, "time-sensitive lifecycle/deadline change warrants limited evening interruption")
    if not business_day and WEEKEND_URGENT_START <= current_time < WEEKEND_URGENT_END and urgent:
        return NotificationTimeDecision("SEND_NOW", local.isoformat(), "WEEKEND_URGENT_EXCEPTION", True, "time-sensitive event warrants bounded weekend interruption")
    target = _next_business_morning(local, holiday_dates, forced_workdays)
    return NotificationTimeDecision("SCHEDULED", target.isoformat(), "NEXT_BUSINESS_MORNING", False, "high priority but not action-urgent outside normal action hours")
