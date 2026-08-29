from __future__ import annotations

from typing import Any

from .collector_core import SCHEMA_VERSION
from .daily_recommendations import build_daily_recommendation_plan
from .match_pipeline import evaluate_match_pipeline
from .model_decision_contract import (
    ModelDecisionError,
    build_model_decision_input,
    render_model_decision,
    validate_model_decision,
)
from .priority_score import PriorityScoreError, calculate_priority_score


MODEL_READY = {"MATCHED_PERSONALIZED", "MATCHED_CANDIDATE"}


def _verified_evidence_urls(facts: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if fact.get("fact_type") != "OFFICIAL_PUBLIC_FACT":
            continue
        if fact.get("verification_status") != "VERIFIED":
            continue
        if fact.get("model_generated") is not False:
            continue
        url = fact.get("source_url")
        if not isinstance(url, str) or not url.strip() or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _factual_snapshot(opportunity: dict[str, Any]) -> dict[str, Any]:
    """Return display facts only from the verified opportunity object.

    No prose is generated here. A missing value remains null/empty rather than being
    inferred from hospital name, product taxonomy, or model output.
    """

    return {
        "project_number": opportunity.get("project_number"),
        "project_name": opportunity.get("project_name"),
        "buyer_name": opportunity.get("buyer_name"),
        "hospital_name": opportunity.get("hospital_name"),
        "department": opportunity.get("department"),
        "region": opportunity.get("region"),
        "lifecycle_state": opportunity.get("lifecycle_state"),
        "notice_type": opportunity.get("notice_type"),
        "published_at": opportunity.get("published_at"),
        "published_at_precision": opportunity.get("published_at_precision"),
        "registration_deadline": opportunity.get("registration_deadline"),
        "bid_deadline": opportunity.get("bid_deadline"),
        "expected_procurement_at": opportunity.get("expected_procurement_at"),
        "expected_procurement_precision": opportunity.get("expected_procurement_precision"),
        "budget": opportunity.get("budget"),
        "procurement_method": opportunity.get("procurement_method"),
        "product_categories": list(opportunity.get("product_categories") or []),
        "product_items": list(opportunity.get("product_items") or []),
        "public_contact": opportunity.get("public_contact"),
        "verification_status": opportunity.get("verification_status"),
        "coverage_status": opportunity.get("coverage_status"),
    }


def _confirmed_relationship(profile: dict[str, Any], hospital_name: Any) -> dict[str, Any] | None:
    if not isinstance(hospital_name, str) or not hospital_name.strip():
        return None
    for relationship in profile.get("hospital_relationships") or []:
        if not isinstance(relationship, dict):
            continue
        if relationship.get("confirmed_by_customer") is not True:
            continue
        if relationship.get("hospital_name") != hospital_name:
            continue
        return {
            "hospital_name": hospital_name,
            "department": relationship.get("department"),
            "relationship_strength": relationship.get("relationship_strength"),
            "owner": relationship.get("owner"),
            "confirmed_by_customer": True,
            "last_confirmed_at": relationship.get("last_confirmed_at"),
        }
    return None


def _matching_capabilities(profile: dict[str, Any], opportunity: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        item
        for item in opportunity.get("product_labels") or []
        if isinstance(item, str) and item.strip()
    }
    result: list[dict[str, Any]] = []
    for capability in profile.get("product_capabilities") or []:
        if not isinstance(capability, dict):
            continue
        taxonomy_ids = {
            item
            for item in capability.get("taxonomy_ids") or []
            if isinstance(item, str) and item.strip()
        }
        matched = sorted(labels.intersection(taxonomy_ids))
        if not matched:
            continue
        result.append(
            {
                "category": capability.get("category"),
                "subcategory": capability.get("subcategory"),
                "matched_taxonomy_ids": matched,
                "brands": list(capability.get("brands") or []),
                "capability_type": capability.get("capability_type"),
            }
        )
    return result


def _customer_context(profile: dict[str, Any], opportunity: dict[str, Any]) -> dict[str, Any]:
    """Return only customer-confirmed/private operating context.

    This block is deliberately separate from official procurement facts. It may
    contain the customer's own relationship assets and product capabilities, but it
    must never be represented as an official hospital or procurement statement.
    """

    partnering = profile.get("partnering_policy") if isinstance(profile.get("partnering_policy"), dict) else {}
    return {
        "context_type": "CUSTOMER_PRIVATE_FACTS",
        "business_role": profile.get("business_role"),
        "hospital_relationship": _confirmed_relationship(profile, opportunity.get("hospital_name")),
        "matching_product_capabilities": _matching_capabilities(profile, opportunity),
        "partnering_policy": {
            "can_seek_temporary_manufacturer": partnering.get("can_seek_temporary_manufacturer"),
            "can_cooperate_with_channel_partner": partnering.get("can_cooperate_with_channel_partner"),
            "can_do_rental_projects": partnering.get("can_do_rental_projects"),
        },
    }


def build_today_actions(
    *,
    profile: dict[str, Any],
    opportunities: list[dict[str, Any]],
    evidence_facts_by_opportunity: dict[str, list[dict[str, Any]]],
    model_outputs_by_opportunity: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the bounded Today Actions backend contract.

    Deterministic matching and priority ranking happen first. Only the final Top 5
    cards may request an Agnes decision. Official facts, customer-private operating
    context, deterministic business priority, and model judgment are emitted in
    separate fields so the UI cannot accidentally present one provenance as another.

    The function does not call Agnes. When a model output is supplied, it is accepted
    only after ``validate_model_decision`` verifies enums and grounded references.
    Invalid model output is rejected and never rendered to the card.
    """

    model_outputs = model_outputs_by_opportunity or {}
    daily_plan = build_daily_recommendation_plan(profile, opportunities)
    opportunity_by_id = {
        item.get("opportunity_id"): item
        for item in opportunities
        if isinstance(item, dict) and isinstance(item.get("opportunity_id"), str)
    }

    cards: list[dict[str, Any]] = []
    model_requests: list[dict[str, Any]] = []

    for rank, plan_card in enumerate(daily_plan["final_action_cards"], start=1):
        opportunity_id = plan_card["opportunity_id"]
        opportunity = opportunity_by_id.get(opportunity_id)
        if opportunity is None:
            continue

        match = evaluate_match_pipeline(profile, opportunity)
        if match.status not in MODEL_READY:
            continue
        try:
            score = calculate_priority_score(profile, opportunity, match)
        except PriorityScoreError:
            continue

        facts = evidence_facts_by_opportunity.get(opportunity_id) or []
        card: dict[str, Any] = {
            "rank": rank,
            "opportunity_id": opportunity_id,
            "facts": _factual_snapshot(opportunity),
            "evidence_source_urls": _verified_evidence_urls(facts),
            "customer_context": _customer_context(profile, opportunity),
            "priority": score.as_dict(),
            "match_status": match.status,
            "recommendation_mode": match.recommendation_mode,
            "model_decision_status": "NOT_ELIGIBLE",
            "model_block_reason": None,
            "decision": None,
        }

        if not match.model_explanation_allowed:
            cards.append(card)
            continue

        try:
            model_input = build_model_decision_input(
                profile=profile,
                opportunity=opportunity,
                match_result=match,
                evidence_facts=facts,
            )
        except ModelDecisionError as exc:
            card["model_decision_status"] = "BLOCKED_GROUNDING"
            card["model_block_reason"] = exc.code
            cards.append(card)
            continue

        supplied_output = model_outputs.get(opportunity_id)
        if supplied_output is None:
            card["model_decision_status"] = "AWAITING_MODEL"
            model_requests.append(
                {
                    "opportunity_id": opportunity_id,
                    "model_input": model_input.as_dict(),
                }
            )
            cards.append(card)
            continue

        try:
            validated = validate_model_decision(supplied_output, model_input)
        except ModelDecisionError as exc:
            card["model_decision_status"] = "MODEL_OUTPUT_REJECTED"
            card["model_block_reason"] = exc.code
            cards.append(card)
            continue

        card["model_decision_status"] = "READY"
        card["decision"] = render_model_decision(validated)
        cards.append(card)

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "TODAY_ACTIONS",
        "input_candidate_count": daily_plan["input_candidate_count"],
        "matched_count": daily_plan["matched_count"],
        "card_count": len(cards),
        "model_request_count": len(model_requests),
        "coverage_warning": "PARTIAL_OR_SOURCE_SPECIFIC_COVERAGE_MAY_APPLY",
        "cards": cards,
        "model_requests": model_requests,
    }
