from __future__ import annotations

from datetime import datetime
from typing import Any

from .agnes_dispatch import build_agnes_dispatch_plan


def build_daily_agnes_dispatch_plan(
    *,
    profile_id: str,
    daily_plan: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Convert already-authorized daily model candidates into one staggered Agnes plan.

    This function never adds new candidates and never overrides Match/model-admission
    gates. The same profile/day/opportunity generates a stable task identity.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ValueError("profile_id is required")
    if daily_plan.get("mode") != "INTERACTIVE_DAILY":
        raise ValueError("daily_plan must be INTERACTIVE_DAILY")

    ids = daily_plan.get("model_candidate_ids")
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("daily_plan model_candidate_ids must be a string array")
    if len(ids) != len(set(ids)):
        raise ValueError("daily_plan model_candidate_ids must be unique")

    local_day = now.date().isoformat()
    tasks = [
        {
            "task_id": f"daily|{profile_id}|{local_day}|{opportunity_id}",
            "task_type": "DAILY_TOP5_EXPLANATION",
            "requested_at": now.isoformat(),
        }
        for opportunity_id in ids
    ]
    plan = build_agnes_dispatch_plan(tasks, now=now)
    return {
        **plan,
        "source": "DAILY_RECOMMENDATION_PLAN",
        "profile_id": profile_id,
        "source_model_candidate_count": len(ids),
    }
