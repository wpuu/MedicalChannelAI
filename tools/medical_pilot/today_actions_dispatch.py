from __future__ import annotations

from datetime import datetime
from typing import Any

from .agnes_dispatch import build_agnes_dispatch_plan


def build_today_actions_agnes_dispatch(
    *,
    profile_id: str,
    today_actions: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Bind grounded Today Actions model requests to the shared Agnes dispatch plan.

    The bridge never creates a model candidate. It only schedules requests already
    admitted by ``build_today_actions`` after deterministic Top5 selection and
    grounding checks. Model inputs remain keyed to stable task IDs for the worker.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ValueError("profile_id is required")
    if today_actions.get("mode") != "TODAY_ACTIONS":
        raise ValueError("today_actions must use TODAY_ACTIONS mode")

    requests = today_actions.get("model_requests")
    cards = today_actions.get("cards")
    if not isinstance(requests, list) or not isinstance(cards, list):
        raise ValueError("today_actions cards/model_requests must be arrays")
    if len(requests) > 5:
        raise ValueError("Today Actions cannot dispatch more than five model requests")

    card_ids = {
        card.get("opportunity_id")
        for card in cards
        if isinstance(card, dict) and isinstance(card.get("opportunity_id"), str)
    }
    seen_opportunity_ids: set[str] = set()
    tasks: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    local_day = now.date().isoformat()

    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("model request must be an object")
        opportunity_id = request.get("opportunity_id")
        model_input = request.get("model_input")
        if not isinstance(opportunity_id, str) or not opportunity_id:
            raise ValueError("model request opportunity_id is required")
        if opportunity_id in seen_opportunity_ids:
            raise ValueError("model request opportunity_id must be unique")
        if opportunity_id not in card_ids:
            raise ValueError("model request must belong to a final Today Actions card")
        if not isinstance(model_input, dict) or model_input.get("opportunity_id") != opportunity_id:
            raise ValueError("model_input must match the model request opportunity_id")

        seen_opportunity_ids.add(opportunity_id)
        task_id = f"today|{profile_id}|{local_day}|{opportunity_id}"
        tasks.append(
            {
                "task_id": task_id,
                "task_type": "DAILY_TOP5_EXPLANATION",
                "requested_at": now.isoformat(),
            }
        )
        payloads.append(
            {
                "task_id": task_id,
                "opportunity_id": opportunity_id,
                "model_input": model_input,
            }
        )

    dispatch_plan = build_agnes_dispatch_plan(tasks, now=now)
    dispatch_ids = {item["task_id"] for item in dispatch_plan["items"]}
    payload_ids = {item["task_id"] for item in payloads}
    if dispatch_ids != payload_ids:
        raise RuntimeError("dispatch plan and payload identities diverged")

    return {
        "schema_version": "0.1",
        "source": "TODAY_ACTIONS",
        "profile_id": profile_id,
        "model_request_count": len(payloads),
        "agnes_dispatch_plan": dispatch_plan,
        "task_payloads": payloads,
    }
