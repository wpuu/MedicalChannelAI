from __future__ import annotations

from typing import Any

from .collector_core import SCHEMA_VERSION
from .match_pipeline import evaluate_match_pipeline
from .priority_score import PriorityScoreError, calculate_priority_score
from .query_budget import build_query_execution_plan


MATCHED = {"MATCHED_PERSONALIZED", "MATCHED_CANDIDATE"}
NEEDS = {"NEEDS_MORE_FACTS"}


def build_daily_recommendation_plan(profile: dict[str, Any], opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the bounded, deterministic daily recommendation plan.

    This function never crawls the web and never calls a model. It assumes callers
    provide candidates from the shared VERIFIED fact index. Query Budget controls
    how many candidates may proceed to deterministic matching, model consideration,
    and final action cards. Model candidate IDs are a strict subset: only rows whose
    Match Gate explicitly allows model explanation may enter Agnes dispatch.
    """

    query_plan = build_query_execution_plan(profile, mode="INTERACTIVE_DAILY")
    budgets = query_plan["budgets"]
    deterministic_limit = min(budgets["max_db_candidates"], budgets["max_deterministic_match_candidates"])
    candidates = opportunities[:deterministic_limit]

    scored: list[dict[str, Any]] = []
    needs_more_facts = 0
    rejected_or_blocked = 0

    for item in candidates:
        match = evaluate_match_pipeline(profile, item)
        if match.status in NEEDS:
            needs_more_facts += 1
            continue
        if match.status not in MATCHED:
            rejected_or_blocked += 1
            continue
        try:
            score = calculate_priority_score(profile, item, match)
        except PriorityScoreError:
            needs_more_facts += 1
            continue
        scored.append(
            {
                "opportunity_id": item["opportunity_id"],
                "priority_score": score.score,
                "score_type": score.score_type,
                "match_status": match.status,
                "model_explanation_allowed": match.model_explanation_allowed,
                "warnings": list(score.warnings),
            }
        )

    scored.sort(key=lambda row: (-row["priority_score"], row["opportunity_id"]))
    model_eligible = [row for row in scored if row["model_explanation_allowed"] is True]
    model_candidates = model_eligible[: budgets["max_model_candidates"]]
    final_cards = scored[: budgets["max_final_action_cards"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "INTERACTIVE_DAILY",
        "input_candidate_count": len(opportunities),
        "evaluated_candidate_count": len(candidates),
        "matched_count": len(scored),
        "needs_more_facts_count": needs_more_facts,
        "rejected_or_blocked_count": rejected_or_blocked,
        "model_candidate_count": len(model_candidates),
        "final_action_card_count": len(final_cards),
        "query_plan": query_plan,
        "model_candidate_ids": [row["opportunity_id"] for row in model_candidates],
        "final_action_cards": final_cards,
    }
