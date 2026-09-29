"""Statutory challenge windows (质疑期) derived from public notice facts.

Legal basis (all deadlines are counted in *working days*):

* 《政府采购质疑和投诉办法》(财政部令第94号)
  - 第十条  供应商可以在知道或者应知其权益受到损害之日起 7 个工作日内提出质疑。
  - 第十一条 对采购文件提出质疑的，应当在获取采购文件或者采购文件公告期限届满之日起
             7 个工作日内提出。
  - 第十三条 采购人、采购代理机构应当在收到质疑函后 7 个工作日内作出答复。
  - 第十七条 对答复不满意或未在规定时间内答复的，可以在答复期满后 15 个工作日内投诉。
  - 第四十二条 期间开始之日不计算在期间内；届满最后一日是节假日的，顺延至节假日后第一日。
* 《政府采购法实施条例》第五十三条  对中标或者成交结果提出质疑的，"应知之日"为
  中标或者成交结果公告期限届满之日。
* 《政府采购货物和服务招标投标管理办法》(财政部令第87号) 第六十九条  中标公告期限为 1 个工作日。

Everything produced here is a *derived estimate* ("推算"), never an official
deadline and never legal advice. The UI must label it as such and must point
the user to the notice text and the finance department for the binding answer.

The working-day calendar is the State Council holiday schedule (国务院办公厅
节假日安排通知). It is the single source of truth for both the Python snapshot
builder and the JS/TS runtime refreshers, which receive it embedded in the
snapshot (``working_calendar``) instead of carrying their own copies.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TIANJIN_TZ = ZoneInfo("Asia/Shanghai")

LEGAL_WINDOWS_SCHEMA_VERSION = "0.1"
LEGAL_BASIS_CODE = "MOF_ORDER_94"

CHALLENGE_WORKING_DAYS = 7          # 94号令 第十条 / 第十一条
CHALLENGE_REPLY_WORKING_DAYS = 7    # 94号令 第十三条
COMPLAINT_WORKING_DAYS = 15         # 94号令 第十七条
AWARD_NOTICE_PERIOD_WORKING_DAYS = 1  # 87号令 第六十九条

DOCUMENT_CHALLENGE = "DOCUMENT_CHALLENGE"
RESULT_CHALLENGE = "RESULT_CHALLENGE"

CALENDAR_OFFICIAL = "CN_STATE_COUNCIL_2025_2026"
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


def _window(
    code: str,
    anchor_kind: str,
    anchor: date,
    lead_working_days: int,
    today: date,
) -> dict[str, Any]:
    # ``lead_working_days`` models a statutory notice period that must expire
    # before the challenge clock starts (e.g. 中标公告期限 1 个工作日).
    clock_start = add_working_days(anchor, lead_working_days) if lead_working_days else anchor
    deadline = add_working_days(clock_start, CHALLENGE_WORKING_DAYS)
    remaining = working_days_remaining(today, deadline)
    covered = calendar_covers(anchor) and calendar_covers(deadline)
    # Compact on purpose: the pool carries ~400 cards and the runtime-cache
    # publisher enforces a hard byte budget on the whole snapshot.
    item: dict[str, Any] = {
        "code": code,
        "anchor_kind": anchor_kind,
        "anchor_date": anchor.isoformat(),
        "deadline_date": deadline.isoformat(),
        "remaining_working_days": remaining,
        "status": "OPEN" if remaining > 0 else "CLOSED",
    }
    if clock_start != anchor:
        item["clock_start_date"] = clock_start.isoformat()
    if not covered:
        item["calendar"] = CALENDAR_WEEKENDS_ONLY
    return item


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
    """Compute the challenge windows that can be derived from public facts.

    Returns a list of window items, or ``None`` when nothing can be derived
    (e.g. procurement intents) so callers can keep the card payload compact.
    Constant metadata (legal basis, statutory day counts, calendar) is emitted
    once per snapshot by :func:`working_calendar_payload`.
    """
    del quality_flags  # reserved for relative-window handling; not used yet
    today = _as_of_date(as_of)
    items: list[dict[str, Any]] = []

    if _is_award_notice(facts):
        published = _local_date(facts.get("published_at"))
        if published is not None:
            # 实施条例 §53: 应知之日 = 中标/成交结果公告期限届满之日; 87号令 §69: 公告期限 1 个工作日.
            items.append(
                _window(
                    RESULT_CHALLENGE,
                    "AWARD_NOTICE_PERIOD_END",
                    published,
                    AWARD_NOTICE_PERIOD_WORKING_DAYS,
                    today,
                )
            )
    else:
        registration = _local_date(facts.get("registration_deadline")) or _local_date(
            facts.get("registration_deadline_date")
        )
        if registration is not None:
            # 94号令 §11: 获取采购文件或采购文件公告期限届满之日起 7 个工作日。
            # We only know the acquisition cutoff, so this is the *latest*
            # possible deadline; a supplier who obtained the documents earlier
            # has an earlier deadline. The UI states this explicitly.
            items.append(
                _window(
                    DOCUMENT_CHALLENGE,
                    "DOCUMENT_ACQUISITION_END",
                    registration,
                    0,
                    today,
                )
            )

    return items or None


def refresh_legal_windows(
    legal_windows: list[dict[str, Any]] | None,
    as_of: datetime,
) -> list[dict[str, Any]] | None:
    """Recompute ``remaining_working_days``/``status`` for existing window items.

    Mirrors what the JS/TS runtime refreshers do between daily snapshot builds.
    Kept here so the Python and JS behaviour can be tested against each other.
    """
    if not isinstance(legal_windows, list):
        return legal_windows
    today = _as_of_date(as_of)
    items = []
    for item in legal_windows:
        deadline = _local_date(item.get("deadline_date")) if isinstance(item, dict) else None
        if deadline is None:
            items.append(dict(item) if isinstance(item, dict) else item)
            continue
        remaining = working_days_remaining(today, deadline)
        items.append({**item, "remaining_working_days": remaining, "status": "OPEN" if remaining > 0 else "CLOSED"})
    return items
