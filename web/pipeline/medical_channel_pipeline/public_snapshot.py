from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .ccgp_events import validate_notice_events
from .validation import validate_records

MAX_TODAY_CARDS = 5
TIANJIN_TZ = ZoneInfo("Asia/Shanghai")
SOURCE_CATEGORY_TITLE_CONFLICT = "SOURCE_CATEGORY_TITLE_CONFLICT"

_SPECIFIC_PRODUCT_ACRONYM_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:CT|DR|MRI|DSA|PCR|POCT|IVD|LIS|PACS|RIS|HIS|GPU)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_SPECIFIC_PRODUCT_TERM_RE = re.compile(
    r"(?:数字减影血管造影|血管造影机|磁共振|彩色超声|超声诊断|胃肠动力|X线|X光机|"
    r"内窥镜|内镜|质谱|测序|透析|呼吸机|心电|脑电|病理|生化分析|免疫分析|"
    r"血液分析|采血|检验科设备|实验室设备)"
)


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _actionability(facts: dict[str, Any], as_of: datetime) -> tuple[str, int, str]:
    bid = _as_datetime(facts.get("bid_deadline"))
    registration = _as_datetime(facts.get("registration_deadline"))
    registration_date = _as_date(facts.get("registration_deadline_date"))
    if bid and bid <= as_of:
        return "ARCHIVE", 0, "NOT_ELIGIBLE"
    if registration and registration <= as_of:
        if not bid:
            return "ARCHIVE", 0, "NOT_ELIGIBLE"
        return "LATE_WINDOW", 8, "AWAITING_MODEL"
    if registration is None and registration_date is not None:
        local_date = as_of.astimezone(TIANJIN_TZ).date()
        if registration_date < local_date:
            if not bid:
                return "ARCHIVE", 0, "NOT_ELIGIBLE"
            return "LATE_WINDOW", 8, "AWAITING_MODEL"
    return "PUBLIC_OPPORTUNITY", 25, "AWAITING_MODEL"


def _next_action_deadline(facts: dict[str, Any], as_of: datetime) -> datetime | None:
    registration = _as_datetime(facts.get("registration_deadline"))
    if registration and registration > as_of:
        return registration

    registration_date = _as_date(facts.get("registration_deadline_date"))
    if registration is None and registration_date is not None:
        local_date = as_of.astimezone(TIANJIN_TZ).date()
        if registration_date >= local_date:
            return datetime.combine(registration_date, time.max, tzinfo=TIANJIN_TZ)

    bid = _as_datetime(facts.get("bid_deadline"))
    if bid and bid > as_of:
        return bid
    return None


def _deadline_urgency_points(facts: dict[str, Any], as_of: datetime) -> int:
    deadline = _next_action_deadline(facts, as_of)
    if deadline is None:
        return 0
    hours_left = (deadline - as_of).total_seconds() / 3600
    if hours_left < 0:
        return 0
    if hours_left <= 24:
        return 10
    if hours_left <= 72:
        return 9
    if hours_left <= 7 * 24:
        return 7
    if hours_left <= 14 * 24:
        return 5
    if hours_left <= 30 * 24:
        return 3
    return 1


def _amount_points(budget: int | None) -> int:
    if budget is None:
        return 0
    if budget >= 5_000_000:
        return 10
    if budget >= 3_000_000:
        return 9
    if budget >= 1_000_000:
        return 7
    if budget >= 500_000:
        return 4
    if budget > 0:
        return 2
    return 0


def _project_title_has_specific_product_signal(project_name: Any) -> bool:
    if not isinstance(project_name, str):
        return False
    title = project_name.strip()
    if not title:
        return False
    return bool(_SPECIFIC_PRODUCT_ACRONYM_RE.search(title) or _SPECIFIC_PRODUCT_TERM_RE.search(title))


def _product_specificity_points(
    facts: dict[str, Any],
    quality_flags: list[str] | None = None,
) -> int:
    points = 0
    items = facts.get("product_items") or []
    categories = facts.get("product_categories") or []
    flags = set(quality_flags or [])
    if isinstance(items, list) and items:
        points += 4
    elif _project_title_has_specific_product_signal(facts.get("project_name")):
        # A verified official title can safely establish a product family even
        # when the parser has not extracted a structured line item. This is a
        # deterministic fallback, not an AI inference.
        points += 4
    # Preserve source categories for audit/display, but an explicit conflict
    # with the verified project title must never increase automated ranking.
    if SOURCE_CATEGORY_TITLE_CONFLICT not in flags and isinstance(categories, list) and categories:
        points += 2
    if facts.get("department"):
        points += 1
    if facts.get("procurement_method"):
        points += 1
    return min(8, points)


def _publication_freshness_points(facts: dict[str, Any], as_of: datetime) -> int:
    value = facts.get("published_at")
    if not value:
        return 0
    try:
        published_date = date.fromisoformat(str(value)[:10])
    except ValueError:
        return 0
    local_date = as_of.astimezone(TIANJIN_TZ).date()
    age_days = (local_date - published_date).days
    if age_days < 0:
        return 0
    if age_days <= 1:
        return 7
    if age_days <= 3:
        return 6
    if age_days <= 7:
        return 5
    if age_days <= 14:
        return 3
    if age_days <= 30:
        return 1
    return 0


def _public_score_components(
    facts: dict[str, Any],
    as_of: datetime,
    quality_flags: list[str] | None = None,
) -> dict[str, int]:
    _, intervention_points, _ = _actionability(facts, as_of)
    return {
        "INTERVENTION_STAGE": intervention_points,
        "DEADLINE_URGENCY": _deadline_urgency_points(facts, as_of),
        "PROJECT_AMOUNT": _amount_points(facts.get("budget_cny")),
        "PRODUCT_SPECIFICITY": _product_specificity_points(facts, quality_flags),
        "PUBLICATION_FRESHNESS": _publication_freshness_points(facts, as_of),
    }


def _event_is_effective(event: dict[str, Any], as_of: datetime) -> bool:
    published = datetime.fromisoformat(event["published_at"]).date()
    return published <= as_of.date()


def _build_event_states(
    notice_events: list[dict[str, Any]],
    as_of: datetime,
) -> dict[str, dict[str, Any]]:
    events = sorted(
        validate_notice_events(notice_events),
        key=lambda event: (event["published_at"], event["event_id"]),
    )
    states: dict[str, dict[str, Any]] = {}
    for event in events:
        if not _event_is_effective(event, as_of):
            continue
        project_number = event["project_number"].strip().lower()
        state = states.setdefault(
            project_number,
            {
                "terminated": False,
                "fact_overrides": {},
                "unresolved_fact_paths": set(),
                "evidence_source_urls": [],
                "applied_event_ids": [],
            },
        )
        source_url = event["source_url"]
        if source_url not in state["evidence_source_urls"]:
            state["evidence_source_urls"].append(source_url)
        state["applied_event_ids"].append(event["event_id"])

        if event["event_type"] == "TERMINATION":
            state["terminated"] = True
            continue

        changed_paths = set(event.get("changed_fact_paths") or [])
        overrides = event.get("fact_overrides") or {}
        unresolved = set(event.get("unresolved_fact_paths") or [])

        if event.get("requires_reconciliation") and not changed_paths and not unresolved:
            unresolved.add("__unparsed_correction__")

        for path in changed_paths:
            if path in overrides:
                state["fact_overrides"][path] = overrides[path]
                state["unresolved_fact_paths"].discard(path)
            else:
                state["unresolved_fact_paths"].add(path)
        state["unresolved_fact_paths"].update(unresolved)

    return states


def _apply_event_state(
    record: dict[str, Any],
    event_state: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not event_state:
        return record, []
    if event_state["terminated"] or event_state["unresolved_fact_paths"]:
        return None, []

    updated = deepcopy(record)
    facts = updated["facts"]
    applied_paths: list[str] = []
    for path, value in event_state["fact_overrides"].items():
        if not path.startswith("facts."):
            continue
        key = path.split(".", 1)[1]
        facts[key] = value
        applied_paths.append(path)

    if applied_paths:
        flags = list(updated.get("quality_flags") or [])
        if "OFFICIAL_CORRECTION_APPLIED" not in flags:
            flags.append("OFFICIAL_CORRECTION_APPLIED")
        updated["quality_flags"] = flags
    return updated, list(event_state["evidence_source_urls"])


def _record_evidence_urls(record: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    primary = record["source"]["url"]
    urls.append(primary)
    for item in record.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        url = item.get("source_url")
        if isinstance(url, str) and url and url not in urls:
            urls.append(url)
    return urls


def _public_card(
    record: dict[str, Any],
    rank: int,
    as_of: datetime,
    correction_evidence_urls: list[str] | None = None,
) -> dict[str, Any]:
    facts = record["facts"]
    quality_flags = list(record.get("quality_flags") or [])
    mode, _, model_status = _actionability(facts, as_of)
    components = _public_score_components(facts, as_of, quality_flags)
    public_score = sum(components.values())
    public_facts = {
        "project_number": facts.get("project_number"),
        "project_name": facts.get("project_name"),
        "buyer_name": facts.get("buyer_name"),
        "hospital_name": facts.get("hospital_name"),
        "department": facts.get("department"),
        "region": facts.get("region"),
        "lifecycle_state": facts.get("lifecycle_state"),
        "notice_type": facts.get("notice_type"),
        "published_at": facts.get("published_at"),
        "published_at_precision": "DAY" if facts.get("published_at") else None,
        "registration_deadline": facts.get("registration_deadline"),
        "registration_deadline_date": facts.get("registration_deadline_date"),
        "registration_deadline_precision": (
            "MINUTE" if facts.get("registration_deadline") else "DAY" if facts.get("registration_deadline_date") else None
        ),
        "bid_deadline": facts.get("bid_deadline"),
        "expected_procurement_at": facts.get("expected_procurement_at"),
        "expected_procurement_precision": facts.get("expected_procurement_precision"),
        "budget": ({"amount_cny": facts["budget_cny"], "currency": "CNY"} if facts.get("budget_cny") is not None else None),
        "procurement_method": facts.get("procurement_method"),
        "product_categories": facts.get("product_categories") or [],
        "product_items": facts.get("product_items") or [],
        "public_contact": facts.get("public_contact"),
        "quality_flags": quality_flags,
        "verification_status": "VERIFIED",
        "coverage_status": "PARTIAL",
    }
    evidence_source_urls = _record_evidence_urls(record)
    for url in correction_evidence_urls or []:
        if url not in evidence_source_urls:
            evidence_source_urls.append(url)

    return {
        "rank": rank,
        "opportunity_id": record["opportunity_id"],
        "facts": public_facts,
        "evidence_source_urls": evidence_source_urls,
        "customer_context": {
            "context_type": "CUSTOMER_PRIVATE_FACTS",
            "business_role": None,
            "hospital_relationship": None,
            "matching_product_capabilities": [],
            "partnering_policy": {
                "can_seek_temporary_manufacturer": None,
                "can_cooperate_with_channel_partner": None,
                "can_do_rental_projects": None,
            },
        },
        "priority": {
            "schema_version": "0.1",
            "score": public_score,
            "score_type": "ZERO_CONFIG_PUBLIC_FACTS_V2",
            "components": [
                {
                    "code": "PRODUCT_EXECUTION_CAPABILITY",
                    "points": 0,
                    "max_points": 25,
                    "basis": "NO_CUSTOMER_PROFILE_IN_ZERO_CONFIG_MODE",
                    "profile_paths": [],
                    "opportunity_paths": [],
                },
                {
                    "code": "RELATIONSHIP",
                    "points": 0,
                    "max_points": 10,
                    "basis": "NO_CUSTOMER_CONFIRMED_RELATIONSHIP",
                    "profile_paths": [],
                    "opportunity_paths": [],
                },
                {
                    "code": "EXECUTION_FLEXIBILITY",
                    "points": 0,
                    "max_points": 5,
                    "basis": "NO_CUSTOMER_EXECUTION_POLICY_IN_ZERO_CONFIG_MODE",
                    "profile_paths": [],
                    "opportunity_paths": [],
                },
                {
                    "code": "INTERVENTION_STAGE",
                    "points": components["INTERVENTION_STAGE"],
                    "max_points": 25,
                    "basis": mode,
                    "profile_paths": [],
                    "opportunity_paths": [
                        "facts.registration_deadline",
                        "facts.registration_deadline_date",
                        "facts.bid_deadline",
                    ],
                },
                {
                    "code": "DEADLINE_URGENCY",
                    "points": components["DEADLINE_URGENCY"],
                    "max_points": 10,
                    "basis": "NEXT_ACTIONABLE_DEADLINE",
                    "profile_paths": [],
                    "opportunity_paths": [
                        "facts.registration_deadline",
                        "facts.registration_deadline_date",
                        "facts.bid_deadline",
                    ],
                },
                {
                    "code": "PROJECT_AMOUNT",
                    "points": components["PROJECT_AMOUNT"],
                    "max_points": 10,
                    "basis": "PUBLIC_BUDGET_ONLY",
                    "profile_paths": [],
                    "opportunity_paths": ["facts.budget_cny"],
                },
                {
                    "code": "PRODUCT_SPECIFICITY",
                    "points": components["PRODUCT_SPECIFICITY"],
                    "max_points": 8,
                    "basis": "VERIFIED_PRODUCT_IDENTITY_AND_EXECUTION_DETAIL",
                    "profile_paths": [],
                    "opportunity_paths": [
                        "facts.project_name",
                        "facts.product_items",
                        "facts.product_categories",
                        "facts.department",
                        "facts.procurement_method",
                    ],
                },
                {
                    "code": "PUBLICATION_FRESHNESS",
                    "points": components["PUBLICATION_FRESHNESS"],
                    "max_points": 7,
                    "basis": "OFFICIAL_PUBLICATION_RECENCY",
                    "profile_paths": [],
                    "opportunity_paths": ["facts.published_at"],
                },
            ],
            "warnings": ["ZERO_CONFIG_PUBLIC_FACTS_ONLY", *quality_flags],
            "interpretation": "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY",
        },
        "match_status": "MATCHED_CANDIDATE",
        "recommendation_mode": mode,
        "model_decision_status": model_status,
        "model_block_reason": None,
        "decision": None,
    }


def _published_sort_timestamp(facts: dict[str, Any]) -> float:
    value = facts.get("published_at")
    if not value:
        return 0.0
    try:
        published = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=TIANJIN_TZ)
        return published.timestamp()
    except ValueError:
        try:
            published_date = date.fromisoformat(str(value)[:10])
            return datetime.combine(published_date, time.min, tzinfo=TIANJIN_TZ).timestamp()
        except ValueError:
            return 0.0


def build_public_snapshot(
    records: list[dict[str, Any]],
    as_of: datetime,
    notice_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    validated = validate_records(records)
    event_states = _build_event_states(notice_events or [], as_of)

    sortable: list[tuple[int, float, float, str, dict[str, Any], list[str]]] = []
    for record in validated:
        facts = record["facts"]
        project_number = str(facts.get("project_number") or "").strip().lower()
        event_state = event_states.get(project_number) if project_number else None
        effective_record, correction_urls = _apply_event_state(record, event_state)
        if effective_record is None:
            continue

        effective_facts = effective_record["facts"]
        mode, _, _ = _actionability(effective_facts, as_of)
        if mode == "ARCHIVE":
            continue
        score = sum(
            _public_score_components(
                effective_facts,
                as_of,
                list(effective_record.get("quality_flags") or []),
            ).values()
        )
        deadline = _next_action_deadline(effective_facts, as_of)
        deadline_sort = deadline.timestamp() if deadline else float("inf")
        published_sort = -_published_sort_timestamp(effective_facts)
        sortable.append(
            (
                -score,
                deadline_sort,
                published_sort,
                effective_record["opportunity_id"],
                effective_record,
                correction_urls,
            )
        )

    sortable.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    opportunity_pool = [
        _public_card(item[4], rank + 1, as_of, item[5])
        for rank, item in enumerate(sortable)
    ]
    cards = opportunity_pool[:MAX_TODAY_CARDS]
    return {
        "schema_version": "0.1",
        "mode": "TODAY_ACTIONS",
        "snapshot_as_of": as_of.isoformat(),
        "input_candidate_count": len(validated),
        "matched_count": len(opportunity_pool),
        "card_count": len(cards),
        "opportunity_pool_count": len(opportunity_pool),
        "model_request_count": 0,
        "coverage_warning": "PARTIAL_OR_SOURCE_SPECIFIC_COVERAGE_MAY_APPLY",
        "cards": cards,
        "opportunity_pool": opportunity_pool,
    }
