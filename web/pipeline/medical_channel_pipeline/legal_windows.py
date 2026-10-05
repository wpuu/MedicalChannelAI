"""Conditional legal-window display; rule applicability and anchors are unverified.

The retained calendar arithmetic is not evidence of an applicable legal deadline.
No derived OPEN/CLOSED state is published until official rules and notice-specific
anchors are independently verified.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TIANJIN_TZ = ZoneInfo("Asia/Shanghai")

LEGAL_WINDOWS_SCHEMA_VERSION = "0.1"
LEGAL_BASIS_CODE = "UNVERIFIED"

CHALLENGE_WORKING_DAYS = 7          # 94号令 第十条 / 第十一条
CHALLENGE_REPLY_WORKING_DAYS = 7    # 94号令 第十三条
COMPLAINT_WORKING_DAYS = 15         # 94号令 第十七条
AWARD_NOTICE_PERIOD_WORKING_DAYS = 1  # 87号令 第六十九条

DOCUMENT_CHALLENGE = "DOCUMENT_CHALLENGE"
RESULT_CHALLENGE = "RESULT_CHALLENGE"

CALENDAR_OFFICIAL = "CN_2025_2026_UNVERIFIED"
CALENDAR_WEEKENDS_ONLY = "WEEKENDS_ONLY_ESTIMATE"

CALENDAR_COVERAGE_FROM = date(2025, 1, 1)
CALENDAR_COVERAGE_TO = date(2026, 12, 31)


def _span(first: date, last: date) -> list[date]:
    days: list[date] = []
    current = first
    while current <= last:
        days.append(current)
        current += timedelta(days=1)
    return days


# 国办发明电〔2024〕8号（2025 年）
_HOLIDAYS_2025 = (
    _span(date(2025, 1, 1), date(2025, 1, 1))      # 元旦
    + _span(date(2025, 1, 28), date(2025, 2, 4))   # 春节
    + _span(date(2025, 4, 4), date(2025, 4, 6))    # 清明节
    + _span(date(2025, 5, 1), date(2025, 5, 5))    # 劳动节
    + _span(date(2025, 5, 31), date(2025, 6, 2))   # 端午节
    + _span(date(2025, 10, 1), date(2025, 10, 8))  # 国庆节、中秋节
)
_ADJUSTED_WORKDAYS_2025 = [
    date(2025, 1, 26), date(2025, 2, 8),           # 春节调休
    date(2025, 4, 27),                             # 劳动节调休
    date(2025, 9, 28), date(2025, 10, 11),         # 国庆节调休
]

# 国办发明电〔2025〕7号（2026 年）
_HOLIDAYS_2026 = (
    _span(date(2026, 1, 1), date(2026, 1, 3))      # 元旦
    + _span(date(2026, 2, 15), date(2026, 2, 23))  # 春节
    + _span(date(2026, 4, 4), date(2026, 4, 6))    # 清明节
    + _span(date(2026, 5, 1), date(2026, 5, 5))    # 劳动节
    + _span(date(2026, 6, 19), date(2026, 6, 21))  # 端午节
    + _span(date(2026, 9, 25), date(2026, 9, 27))  # 中秋节
    + _span(date(2026, 10, 1), date(2026, 10, 7))  # 国庆节
)
_ADJUSTED_WORKDAYS_2026 = [
    date(2026, 1, 4),                              # 元旦调休
    date(2026, 2, 14), date(2026, 2, 28),          # 春节调休
    date(2026, 5, 9),                              # 劳动节调休
    date(2026, 9, 20), date(2026, 10, 10),         # 国庆节调休
]

HOLIDAYS: frozenset[date] = frozenset(_HOLIDAYS_2025 + _HOLIDAYS_2026)
ADJUSTED_WORKDAYS: frozenset[date] = frozenset(_ADJUSTED_WORKDAYS_2025 + _ADJUSTED_WORKDAYS_2026)


def calendar_covers(day: date) -> bool:
    return CALENDAR_COVERAGE_FROM <= day <= CALENDAR_COVERAGE_TO


def is_working_day(day: date) -> bool:
    if day in ADJUSTED_WORKDAYS:
        return True
    if day in HOLIDAYS:
        return False
    return day.weekday() < 5


def add_working_days(start: date, count: int) -> date:
    """Return the ``count``-th working day strictly after ``start``.

    94号令 第四十二条: the starting day itself is not counted. Because the
    result is by construction a working day, the "届满最后一日是节假日则顺延"
    rule is satisfied automatically.
    """
    if count < 0:
        raise ValueError("count must be non-negative")
    current = start
    remaining = count
    while remaining > 0:
        current += timedelta(days=1)
        if is_working_day(current):
            remaining -= 1
    return current


def working_days_remaining(today: date, deadline: date) -> int:
    """Working days ``d`` with ``today <= d <= deadline`` (0 once the deadline passed).

    When ``today`` is the deadline and a working day the answer is 1 ("今天是
    最后一天"). Bounded loop: the two dates are never more than a few months
    apart in practice, but guard against pathological inputs anyway.
    """
    if deadline < today:
        return 0
    count = 0
    current = today
    guard = 0
    while current <= deadline and guard < 4000:
        if is_working_day(current):
            count += 1
        current += timedelta(days=1)
        guard += 1
    return count


def working_calendar_payload() -> dict[str, Any]:
    """Calendar embedded in the public snapshot for the JS/TS runtime refreshers."""
    return {
        "schema_version": LEGAL_WINDOWS_SCHEMA_VERSION,
        "code": CALENDAR_OFFICIAL,
        "coverage_from": CALENDAR_COVERAGE_FROM.isoformat(),
        "coverage_to": CALENDAR_COVERAGE_TO.isoformat(),
        "holidays": sorted(day.isoformat() for day in HOLIDAYS),
        "adjusted_workdays": sorted(day.isoformat() for day in ADJUSTED_WORKDAYS),
        # Constants shared by every card's ``legal_windows`` entries. They live
        # here once instead of being repeated ~400 times in the pool.
        "legal_basis": LEGAL_BASIS_CODE,
        "verification_status": "UNVERIFIED",
        "challenge_working_days": CHALLENGE_WORKING_DAYS,
        "challenge_reply_working_days": CHALLENGE_REPLY_WORKING_DAYS,
        "complaint_working_days": COMPLAINT_WORKING_DAYS,
        "award_notice_period_working_days": AWARD_NOTICE_PERIOD_WORKING_DAYS,
    }


def _local_date(value: Any) -> date | None:
    """Best-effort Tianjin calendar date from an ISO datetime or date string."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIANJIN_TZ)
    return parsed.astimezone(TIANJIN_TZ).date()


def _as_of_date(as_of: datetime) -> date:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=TIANJIN_TZ)
    return as_of.astimezone(TIANJIN_TZ).date()


def _unknown_window(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "anchor_kind": "UNVERIFIED",
        "anchor_date": None,
        "deadline_date": None,
        "remaining_working_days": 0,
        "status": "UNKNOWN",
        "uncertainty_reason": "APPLICABILITY_ANCHOR_AND_LEGAL_SOURCE_UNVERIFIED",
    }


def _is_award_notice(facts: dict[str, Any]) -> bool:
    lifecycle = str(facts.get("lifecycle_state") or "").strip().upper()
    if lifecycle in {"AWARDED", "AWARD", "RESULT_PUBLISHED"}:
        return True
    notice_type = str(facts.get("notice_type") or "")
    return any(token in notice_type for token in ("中标", "成交", "结果公告"))


def legal_windows_for_facts(
    facts: dict[str, Any],
    as_of: datetime,
    quality_flags: list[str] | None = None,
) -> list[dict[str, Any]] | None:
    """Notice dates alone do not establish the applicable regime or legal anchor."""
    if _is_award_notice(facts):
        return [_unknown_window(RESULT_CHALLENGE)]
    if str(facts.get("lifecycle_state") or "").upper() == "PROCUREMENT_INTENT":
        return None
    if (facts.get("registration_deadline") or facts.get("registration_deadline_date")
            or str(facts.get("lifecycle_state") or "").upper() == "BIDDING"
            or "招标" in str(facts.get("notice_type") or "")):
        return [_unknown_window(DOCUMENT_CHALLENGE)]
    return None


def refresh_legal_windows(
    legal_windows: list[dict[str, Any]] | None,
    as_of: datetime,
) -> list[dict[str, Any]] | None:
    """Legacy derived dates have no verified legal basis; keep them unknown."""
    if not isinstance(legal_windows, list):
        return legal_windows
    return [
        {**{key: value for key, value in item.items() if key != "clock_start_date"}, **_unknown_window(item.get("code"))}
        if isinstance(item, dict) else item
        for item in legal_windows
    ]
