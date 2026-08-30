from __future__ import annotations

import hashlib
from typing import Any

from .collector_core import SCHEMA_VERSION
from .match_pipeline import evaluate_match_pipeline
from .priority_score import PriorityScoreError, calculate_priority_score


ALLOWED_EVENT_TYPES = {
    "NEW_VERIFIED_OPPORTUNITY",
    "LIFECYCLE_STATE_CHANGED",
    "DEADLINE_CHANGED",
    "AWARD_PUBLISHED",
}

MATCHED = {"MATCHED_PERSONALIZED", "MATCHED_CANDIDATE"}
NEEDS_MORE_FACTS = {"NEEDS_MORE_FACTS"}


def _dedupe_key(profile_id: str, opportunity_id: str, material_event_id: str, event_type: str) -> str:
    payload = "|".join((profile_id, opportunity_id, material_event_id, event_type)).encode("utf-8")
    return "subeval_" + hashlib.sha256(payload).hexdigest()


def _reason_codes(match: Any) -> list[str]:
    result: list[str] = []
    for reason in getattr(match, "reasons", ()) or ():
        code = getattr(reason, "code", None)
        if isinstance(code, str) and code and code not in result:
            result.append(code)
    return result


def evaluate_subscription_event(
    *,
    profile: dict[str, Any],
    opportunity: dict[str, Any],
    material_event_id: str,
    event_type: str,
    immediate_priority_score_threshold: int = 80,
) -> dict[str, Any]:
    """Evaluate one material VERIFIED opportunity event against one customer profile.

    This function does not crawl and does not call a model. It converts the existing
    deterministic match/priority pipeline into a push decision. Candidate-only matches
    may enter the daily digest, but immediate alerts require a fully confirmed profile.
    """

    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"unsupported subscription event type: {event_type}")
    if not isinstance(material_event_id, str) or not material_event_id.strip():
        raise ValueError("material_event_id is required")
    if not isinstance(immediate_priority_score_threshold, int) or not 0 <= immediate_priority_score_threshold <= 100:
        raise ValueError("immediate_priority_score_threshold must be an integer from 0 to 100")

    profile_id = str(profile.get("profile_id") or "")
    opportunity_id = str(opportunity.get("opportunity_id") or "")
    if not profile_id or not opportunity_id:
        raise ValueError("profile_id and opportunity_id are required")

    match = evaluate_match_pipeline(profile, opportunity)
    reasons = _reason_codes(match)
    priority_score: int | None = None

    if match.status in MATCHED:
        try:
            score = calculate_priority_score(profile, opportunity, match)
        except PriorityScoreError as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "profile_id": profile_id,
                "opportunity_id": opportunity_id,
                "material_event_id": material_event_id,
                "event_type": event_type,
                "evaluation_status": "NEEDS_MORE_FACTS",
                "delivery_class": "ENRICHMENT_ONLY",
                "priority_score": None,
                "score_interpretation": "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY",
                "model_explanation_allowed": False,
                "dedupe_key": _dedupe_key(profile_id, opportunity_id, material_event_id, event_type),
                "reasons": list(dict.fromkeys(reasons + [exc.code])),
            }

        priority_score = score.score
        fully_confirmed = match.status == "MATCHED_PERSONALIZED"
        immediate = fully_confirmed and priority_score >= immediate_priority_score_threshold
        delivery_class = "IMMEDIATE_HIGH_PRIORITY" if immediate else "DAILY_DIGEST"
        reasons.append("PRIORITY_THRESHOLD_MET" if immediate else "MATCHED_FOR_DIGEST")
        return {
            "schema_version": SCHEMA_VERSION,
            "profile_id": profile_id,
            "opportunity_id": opportunity_id,
            "material_event_id": material_event_id,
            "event_type": event_type,
            "evaluation_status": "MATCHED",
            "delivery_class": delivery_class,
            "priority_score": priority_score,
            "score_interpretation": "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY",
            "model_explanation_allowed": bool(match.model_explanation_allowed),
            "dedupe_key": _dedupe_key(profile_id, opportunity_id, material_event_id, event_type),
            "reasons": list(dict.fromkeys(reasons)),
        }

    if match.status in NEEDS_MORE_FACTS:
        delivery_class = "ENRICHMENT_ONLY"
        evaluation_status = "NEEDS_MORE_FACTS"
    else:
        delivery_class = "NO_NOTIFY"
        evaluation_status = "REJECTED_OR_BLOCKED"

    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "opportunity_id": opportunity_id,
        "material_event_id": material_event_id,
        "event_type": event_type,
        "evaluation_status": evaluation_status,
        "delivery_class": delivery_class,
        "priority_score": priority_score,
        "score_interpretation": "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY",
        "model_explanation_allowed": False,
        "dedupe_key": _dedupe_key(profile_id, opportunity_id, material_event_id, event_type),
        "reasons": reasons or [match.status],
    }
