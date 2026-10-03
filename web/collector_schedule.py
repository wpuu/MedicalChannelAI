"""Single-user twice-daily schedule; periods are named, never minute-derived."""
from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo('Asia/Shanghai')
SCHEDULE_VERSION = 'twice-daily-v1'
PERIOD_HOURS = {'morning': 8, 'noon': 12}


def scheduled_cycle(now: datetime, period: str) -> tuple[str, datetime]:
    if now.tzinfo is None or period not in PERIOD_HOURS:
        raise ValueError('COLLECTOR_PERIOD_INVALID')
    local = now.astimezone(SHANGHAI)
    hour = PERIOD_HOURS[period]
    # Hobby has hourly precision. Accept the configured hour and up to 59
    # minutes after :20; reject late old-period triggers outside this window.
    if not hour <= local.hour < hour + 2:
        raise ValueError('COLLECTOR_PERIOD_OUTSIDE_WINDOW')
    anchor = local  # Freeze the actual first start, never synthesize a future freshness clock.
    return f'prod:{local.date().isoformat()}:{period}:{SCHEDULE_VERSION}', anchor


def valid_cycle(cycle_id: str, anchor: datetime) -> bool:
    if anchor.tzinfo is None:
        return False
    for period in PERIOD_HOURS:
        try:
            expected_id, _ = scheduled_cycle(anchor, period)
        except ValueError:
            continue
        if cycle_id == expected_id:
            return True
    return False


def running_stage_is_live(state: object, now: datetime) -> bool:
    """A stale status is not an in-flight function: maxDuration 300s + 60s."""
    if not isinstance(state, dict) or not isinstance(state.get('stages'), dict):
        return False
    for stage in state['stages'].values():
        if not isinstance(stage, dict) or stage.get('status') != 'RUNNING':
            continue
        try:
            started = datetime.fromisoformat(str(stage.get('started_at') or '').replace('Z', '+00:00'))
        except ValueError:
            return True
        if started.tzinfo is None or (now - started).total_seconds() < 360:
            return True
    return False
