from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .validation import validate_records


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _actionability(facts: dict[str, Any], as_of: datetime) -> tuple[str, int, str]:
    bid = _as_datetime(facts.get("bid_deadline"))
    registration = _as_datetime(facts.get("registration_deadline"))
    if bid and bid < as_of:
        return "ARCHIVE", 0, "NOT_ELIGIBLE"
    if registration and registration < as_of:
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


def _public_card(record: dict[str, Any], rank: int, as_of: datetime) -> dict[str, Any]:
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
    source_url = record["source"]["url"]
    return {
        "rank": rank,
        "opportunity_id": record["opportunity_id"],
        "facts": public_facts,
        "evidence_source_urls": [source_url],
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
                    "opportunity_paths": ["facts.registration_deadline", "facts.bid_deadline"],
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
            "warnings": ["ZERO_CONFIG_PUBLIC_FACTS_ONLY"],
            "interpretation": "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY",
        },
        "match_status": "MATCHED_CANDIDATE",
        "recommendation_mode": mode,
        "model_decision_status": model_status,
        "model_block_reason": None,
        "decision": None,
    }


def build_public_snapshot(records: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    validated = validate_records(records)
    sortable = []
    for record in validated:
        facts = record["facts"]
        mode, intervention, _ = _actionability(facts, as_of)
        sortable.append((mode == "ARCHIVE", -(intervention + _amount_points(facts.get("budget_cny"))), record))
    sortable.sort(key=lambda item: (item[0], item[1], item[2]["opportunity_id"]))
    cards = [_public_card(item[2], rank + 1, as_of) for rank, item in enumerate(sortable)]
    matched_count = sum(1 for card in cards if card["recommendation_mode"] != "ARCHIVE")
    return {
        "schema_version": "0.1",
        "mode": "TODAY_ACTIONS",
        "input_candidate_count": len(cards),
        "matched_count": matched_count,
        "card_count": len(cards),
        "model_request_count": 0,
        "coverage_warning": "PARTIAL_OR_SOURCE_SPECIFIC_COVERAGE_MAY_APPLY",
        "cards": cards,
    }
