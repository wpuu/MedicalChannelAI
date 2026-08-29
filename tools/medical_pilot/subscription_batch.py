from __future__ import annotations

from typing import Any

from .collector_core import SCHEMA_VERSION
from .material_event import validate_material_event_envelope
from .subscription_engine import ALLOWED_EVENT_TYPES, evaluate_subscription_event
from .subscription_notification import route_subscription_notification
from .subscription_prefilter import build_profile_subscription_index, prefilter_profiles_for_opportunity


def process_subscription_event_batch(
    *,
    profiles: list[dict[str, Any]],
    opportunity: dict[str, Any],
    material_event_id: str,
    event_type: str,
    latest_followups_by_profile: dict[str, dict[str, Any]] | None = None,
    batch_offset: int = 0,
    batch_limit: int = 500,
    immediate_priority_score_threshold: int = 80,
) -> dict[str, Any]:
    """Low-level bounded subscription processor.

    Callers at the service/event boundary should use
    process_verified_material_event_batch(), which validates the persisted VERIFIED
    event envelope first. This lower-level function is retained for deterministic
    composition and tests. It never crawls and never calls a model.
    """

    if not isinstance(batch_offset, int) or batch_offset < 0:
        raise ValueError("batch_offset must be a non-negative integer")
    if not isinstance(batch_limit, int) or not 1 <= batch_limit <= 1000:
        raise ValueError("batch_limit must be an integer from 1 to 1000")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"unsupported subscription event type: {event_type}")
    if not isinstance(material_event_id, str) or not material_event_id.strip():
        raise ValueError("material_event_id is required")

    opportunity_id = str(opportunity.get("opportunity_id") or "")
    if not opportunity_id:
        raise ValueError("opportunity_id is required")

    profile_map = {
        str(profile.get("profile_id")): profile
        for profile in profiles
        if isinstance(profile, dict) and isinstance(profile.get("profile_id"), str) and profile.get("profile_id")
    }
    index = build_profile_subscription_index(profiles)
    prefilter = prefilter_profiles_for_opportunity(index, opportunity)

    if prefilter["status"] != "READY":
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "NEEDS_MORE_FACTS",
            "opportunity_id": opportunity_id,
            "material_event_id": material_event_id,
            "event_type": event_type,
            "candidate_profile_count": 0,
            "processed_profile_count": 0,
            "batch_offset": batch_offset,
            "batch_limit": batch_limit,
            "next_offset": None,
            "dispatches": [],
            "required_next_facts": prefilter["required_next_facts"],
            "interpretation": "BOUNDED_PREFILTERED_BATCH_FINAL_MATCH_REQUIRED",
        }

    candidate_ids = list(prefilter["candidate_profile_ids"])
    selected_ids = candidate_ids[batch_offset : batch_offset + batch_limit]
    followups = latest_followups_by_profile or {}
    dispatches: list[dict[str, Any]] = []

    for profile_id in selected_ids:
        profile = profile_map.get(profile_id)
        if profile is None:
            continue
        evaluation = evaluate_subscription_event(
            profile=profile,
            opportunity=opportunity,
            material_event_id=material_event_id,
            event_type=event_type,
            immediate_priority_score_threshold=immediate_priority_score_threshold,
        )
        route = route_subscription_notification(
            evaluation,
            latest_followup=followups.get(profile_id),
        )
        dispatches.append(
            {
                "profile_id": profile_id,
                "dedupe_key": evaluation["dedupe_key"],
                "routing_status": route["routing_status"],
                "audience": route["audience"],
                "target_owner": route["target_owner"],
                "should_notify": route["should_notify"],
            }
        )

    consumed_to = batch_offset + len(selected_ids)
    next_offset = consumed_to if consumed_to < len(candidate_ids) else None
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "READY",
        "opportunity_id": opportunity_id,
        "material_event_id": material_event_id,
        "event_type": event_type,
        "candidate_profile_count": len(candidate_ids),
        "processed_profile_count": len(dispatches),
        "batch_offset": batch_offset,
        "batch_limit": batch_limit,
        "next_offset": next_offset,
        "dispatches": dispatches,
        "required_next_facts": [],
        "interpretation": "BOUNDED_PREFILTERED_BATCH_FINAL_MATCH_REQUIRED",
    }


def process_verified_material_event_batch(
    *,
    profiles: list[dict[str, Any]],
    opportunity: dict[str, Any],
    material_event: dict[str, Any],
    latest_followups_by_profile: dict[str, dict[str, Any]] | None = None,
    batch_offset: int = 0,
    batch_limit: int = 500,
    immediate_priority_score_threshold: int = 80,
) -> dict[str, Any]:
    """Public service boundary: validate VERIFIED event envelope before dispatch."""

    event = validate_material_event_envelope(material_event)
    opportunity_id = opportunity.get("opportunity_id")
    if event["opportunity_id"] != opportunity_id:
        raise ValueError("material event opportunity_id does not match opportunity")
    return process_subscription_event_batch(
        profiles=profiles,
        opportunity=opportunity,
        material_event_id=event["material_event_id"],
        event_type=event["event_type"],
        latest_followups_by_profile=latest_followups_by_profile,
        batch_offset=batch_offset,
        batch_limit=batch_limit,
        immediate_priority_score_threshold=immediate_priority_score_threshold,
    )
