from pathlib import Path

path = Path('web/pipeline/medical_channel_pipeline/public_snapshot.py')
source = path.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global source
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, got {count}')
    source = source.replace(old, new, 1)


replace_once(
    'from datetime import date, datetime, time, timezone\n',
    'from datetime import date, datetime, time, timedelta, timezone\n',
    'timedelta-import',
)
replace_once(
    'SOURCE_CATEGORY_TITLE_CONFLICT = "SOURCE_CATEGORY_TITLE_CONFLICT"\n',
    'SOURCE_CATEGORY_TITLE_CONFLICT = "SOURCE_CATEGORY_TITLE_CONFLICT"\n'
    'RELATIVE_REGISTRATION_WINDOW_7_DAYS = "RELATIVE_REGISTRATION_WINDOW_7_DAYS"\n',
    'relative-window-constant',
)
replace_once(
    'def _actionability(facts: dict[str, Any], as_of: datetime) -> tuple[str, int, str]:\n',
    'def _relative_registration_deadline(\n'
    '    facts: dict[str, Any],\n'
    '    quality_flags: list[str] | None = None,\n'
    ') -> datetime | None:\n'
    '    if RELATIVE_REGISTRATION_WINDOW_7_DAYS not in set(quality_flags or []):\n'
    '        return None\n'
    '    published = facts.get("published_at")\n'
    '    if not published:\n'
    '        return None\n'
    '    try:\n'
    '        published_date = date.fromisoformat(str(published)[:10])\n'
    '    except ValueError:\n'
    '        return None\n'
    '    # Operational bound only. The public fact fields intentionally keep the\n'
    '    # official deadline empty because the notice does not publish an exact\n'
    '    # cutoff timestamp. Using end-of-day after seven days is conservative\n'
    '    # for action ranking and must never be rendered as an official deadline.\n'
    '    return datetime.combine(published_date + timedelta(days=7), time.max, tzinfo=TIANJIN_TZ)\n'
    '\n'
    '\n'
    'def _actionability(\n'
    '    facts: dict[str, Any],\n'
    '    as_of: datetime,\n'
    '    quality_flags: list[str] | None = None,\n'
    ') -> tuple[str, int, str]:\n',
    'relative-window-helper',
)
replace_once(
    '    if registration is None and registration_date is not None:\n'
    '        local_date = as_of.astimezone(TIANJIN_TZ).date()\n'
    '        if registration_date < local_date:\n'
    '            if not bid:\n'
    '                return "ARCHIVE", 0, "NOT_ELIGIBLE"\n'
    '            return "LATE_WINDOW", 8, "AWAITING_MODEL"\n'
    '    return "PUBLIC_OPPORTUNITY", 25, "AWAITING_MODEL"\n',
    '    if registration is None and registration_date is not None:\n'
    '        local_date = as_of.astimezone(TIANJIN_TZ).date()\n'
    '        if registration_date < local_date:\n'
    '            if not bid:\n'
    '                return "ARCHIVE", 0, "NOT_ELIGIBLE"\n'
    '            return "LATE_WINDOW", 8, "AWAITING_MODEL"\n'
    '    relative_deadline = _relative_registration_deadline(facts, quality_flags)\n'
    '    if relative_deadline is not None and relative_deadline <= as_of:\n'
    '        return "ARCHIVE", 0, "NOT_ELIGIBLE"\n'
    '    return "PUBLIC_OPPORTUNITY", 25, "AWAITING_MODEL"\n',
    'actionability-relative-expiry',
)
replace_once(
    'def _next_action_deadline(facts: dict[str, Any], as_of: datetime) -> datetime | None:\n',
    'def _next_action_deadline(\n'
    '    facts: dict[str, Any],\n'
    '    as_of: datetime,\n'
    '    quality_flags: list[str] | None = None,\n'
    ') -> datetime | None:\n',
    'next-deadline-signature',
)
replace_once(
    '    bid = _as_datetime(facts.get("bid_deadline"))\n'
    '    if bid and bid > as_of:\n'
    '        return bid\n'
    '    return None\n'
    '\n'
    '\n'
    'def _deadline_urgency_points(facts: dict[str, Any], as_of: datetime) -> int:\n'
    '    deadline = _next_action_deadline(facts, as_of)\n',
    '    bid = _as_datetime(facts.get("bid_deadline"))\n'
    '    if bid and bid > as_of:\n'
    '        return bid\n'
    '    relative_deadline = _relative_registration_deadline(facts, quality_flags)\n'
    '    if relative_deadline is not None and relative_deadline > as_of:\n'
    '        return relative_deadline\n'
    '    return None\n'
    '\n'
    '\n'
    'def _deadline_urgency_points(\n'
    '    facts: dict[str, Any],\n'
    '    as_of: datetime,\n'
    '    quality_flags: list[str] | None = None,\n'
    ') -> int:\n'
    '    deadline = _next_action_deadline(facts, as_of, quality_flags)\n',
    'urgency-relative-deadline',
)
replace_once(
    '    _, intervention_points, _ = _actionability(facts, as_of)\n'
    '    return {\n'
    '        "INTERVENTION_STAGE": intervention_points,\n'
    '        "DEADLINE_URGENCY": _deadline_urgency_points(facts, as_of),\n',
    '    _, intervention_points, _ = _actionability(facts, as_of, quality_flags)\n'
    '    return {\n'
    '        "INTERVENTION_STAGE": intervention_points,\n'
    '        "DEADLINE_URGENCY": _deadline_urgency_points(facts, as_of, quality_flags),\n',
    'score-relative-window',
)
replace_once(
    '    mode, _, model_status = _actionability(facts, as_of)\n',
    '    mode, _, model_status = _actionability(facts, as_of, quality_flags)\n',
    'public-card-actionability',
)
replace_once(
    '        mode, _, _ = _actionability(effective_facts, as_of)\n',
    '        effective_flags = list(effective_record.get("quality_flags") or [])\n'
    '        mode, _, _ = _actionability(effective_facts, as_of, effective_flags)\n',
    'build-actionability',
)
replace_once(
    '        deadline = _next_action_deadline(effective_facts, as_of)\n',
    '        deadline = _next_action_deadline(effective_facts, as_of, effective_flags)\n',
    'build-sort-deadline',
)

path.write_text(source, encoding='utf-8')
