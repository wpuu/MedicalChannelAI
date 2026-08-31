from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .ccgp_events import validate_notice_events
from .validation import validate_records

MAX_TODAY_CARDS = 5
TIANJIN_TZ = ZoneInfo("Asia/Shanghai")


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
        return "LATE_WINDOW", 15, "AWAITING_MODEL"
    if registration is None and registration_date is not None:
        local_date = as_of.astimezone(TIANJIN_TZ).date()
        if registration_date < local_date:
            if not bid:
                return "ARCHIVE", 0, "NOT_ELIGIBLE"
            return "LATE_WINDOW", 15, "AWAITING_MODEL"
    return "PUBLIC_OPPORTUNITY", 40, "AWAITING_MODEL"


def _amount_points(budget: int | None) -> int:
    if budget is None:
        return 0
    if budget >= 5_000_000:
        return 20
    if budget >= 3_000_000:
        return 18
    if budget >= 1_000_000:
        return 14
    if budget >= 500_000:
        return 8
    return 4


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


def _public_card(
    record: dict[str, Any],
    rank: int,
    as_of: datetime,
    correction_evidence_urls: list[str] | None = None,
) -> dict[str, Any]:
    facts = record["facts"]
    mode, intervention_points, model_status = _actionability(facts, as_of)
    amount_points = _amount_points(facts.get("budget_cny"))
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
        "verification_status": "VERIFIED",
        "coverage_status": "PARTIAL",
    }
    evidence_source_urls = [record["source"]["url"]]
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
            "score": amount_points + intervention_points,
            "score_type": "ZERO_CONFIG_PUBLIC_FACTS_ONLY",
            "components": [
                {
                    "code": "PRODUCT_EXECUTION_CAPABILITY",
                    "points": 0,
                    "max_points": 30,
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
                    "code": "INTERVENTION_STAGE",
                    "points": intervention_points,
                    "max_points": 40,
                    "basis": mode,
                    "profile_paths": [],
                    "opportunity_paths": [
                        "facts.registration_deadline",
                        "facts.registration_deadline_date",
                        "facts.bid_deadline",
                    ],
                },
                {
                    "code": "PROJECT_AMOUNT",
                    "points": amount_points,
                    "max_points": 20,
                    "basis": "PUBLIC_BUDGET_ONLY",
                    "profile_paths": [],
                    "opportunity_paths": ["facts.budget_cny"],
                },
            ],
            "warnings": ["ZERO_CONFIG_PUBLIC_FACTS_ONLY", *(record.get("quality_flags") or [])],
            "interpretation": "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY",
        },
        "match_status": "MATCHED_CANDIDATE",
        "recommendation_mode": mode,
        "model_decision_status": model_status,
        "model_block_reason": None,
        "decision": None,
    }


def build_public_snapshot(
    records: list[dict[str, Any]],
    as_of: datetime,
    notice_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    validated = validate_records(records)
    event_states = _build_event_states(notice_events or [], as_of)

    sortable: list[tuple[int, str, dict[str, Any], list[str]]] = []
    for record in validated:
        facts = record["facts"]
        project_number = str(facts.get("project_number") or "").strip().lower()
        event_state = event_states.get(project_number) if project_number else None
        effective_record, correction_urls = _apply_event_state(record, event_state)
        if effective_record is None:
            continue

        effective_facts = effective_record["facts"]
        mode, intervention, _ = _actionability(effective_facts, as_of)
        if mode == "ARCHIVE":
            continue
        score = intervention + _amount_points(effective_facts.get("budget_cny"))
        sortable.append((-score, effective_record["opportunity_id"], effective_record, correction_urls))

    sortable.sort(key=lambda item: (item[0], item[1]))
    opportunity_pool = [
        _public_card(item[2], rank + 1, as_of, item[3])
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
