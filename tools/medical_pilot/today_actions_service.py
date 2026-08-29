from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .agnes_task_result import AgnesTaskResultStore
from .today_actions import build_today_actions
from .today_actions_dispatch import build_today_actions_agnes_dispatch


@dataclass(frozen=True)
class TodayActionsServiceCycle:
    """One backend assembly cycle for the H5-facing Today Actions response.

    ``public_today_actions`` is safe for the frontend contract. ``internal_dispatch``
    stays server-side because it contains locked model inputs and scheduling details.
    """

    public_today_actions: dict[str, Any]
    internal_dispatch: dict[str, Any]
    reused_ready_count: int
    reused_rejected_count: int

    def public_response(self) -> dict[str, Any]:
        return self.public_today_actions


def _terminal_results_for_dispatch(
    dispatch: dict[str, Any],
    *,
    result_store: AgnesTaskResultStore,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    ready: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    for payload in dispatch.get("task_payloads") or []:
        if not isinstance(payload, dict):
            continue
        task_id = payload.get("task_id")
        opportunity_id = payload.get("opportunity_id")
        if not isinstance(task_id, str) or not isinstance(opportunity_id, str):
            continue
        terminal = result_store.get(task_id)
        if terminal is None:
            continue
        if terminal.get("opportunity_id") != opportunity_id:
            raise ValueError("terminal result opportunity_id diverges from current dispatch")
        if terminal.get("model_input_sha256") != payload.get("model_input_sha256"):
            raise ValueError("terminal result model input hash diverges from current dispatch")
        if terminal.get("status") == "READY":
            output = terminal.get("validated_output")
            if not isinstance(output, dict):
                raise ValueError("READY terminal result is missing validated output")
            ready[opportunity_id] = output
        elif terminal.get("status") == "MODEL_OUTPUT_REJECTED":
            error_code = terminal.get("error_code")
            if not isinstance(error_code, str) or not error_code:
                raise ValueError("rejected terminal result is missing error code")
            rejected[opportunity_id] = error_code
        else:
            raise ValueError("unsupported terminal result status")
    return ready, rejected


def _apply_rejected_terminal_state(today: dict[str, Any], rejected: dict[str, str]) -> dict[str, Any]:
    if not rejected:
        return today
    model_requests = [
        row for row in today.get("model_requests") or []
        if isinstance(row, dict) and row.get("opportunity_id") not in rejected
    ]
    today["model_requests"] = model_requests
    today["model_request_count"] = len(model_requests)
    for card in today.get("cards") or []:
        if not isinstance(card, dict):
            continue
        opportunity_id = card.get("opportunity_id")
        if opportunity_id not in rejected:
            continue
        card["model_decision_status"] = "MODEL_OUTPUT_REJECTED"
        card["model_block_reason"] = rejected[opportunity_id]
        card["decision"] = None
    return today


def build_today_actions_service_cycle(
    *,
    profile: dict[str, Any],
    opportunities: list[dict[str, Any]],
    evidence_facts_by_opportunity: dict[str, list[dict[str, Any]]],
    result_store: AgnesTaskResultStore,
    now: datetime,
) -> TodayActionsServiceCycle:
    """Build public Today Actions and the server-only pending Agnes dispatch.

    Phase 1 computes the current immutable model-input fingerprints. Terminal results
    are reused only when their task/hash matches this exact current input. READY
    results are revalidated by ``build_today_actions`` before rendering. Rejected
    immutable outputs stay rejected and are removed from new model work. New evidence
    or confirmed profile changes alter the input hash and naturally create new work.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    profile_id = profile.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        raise ValueError("profile.profile_id is required")

    initial = build_today_actions(
        profile=profile,
        opportunities=opportunities,
        evidence_facts_by_opportunity=evidence_facts_by_opportunity,
    )
    initial_dispatch = build_today_actions_agnes_dispatch(
        profile_id=profile_id,
        today_actions=initial,
        now=now,
    )
    ready, rejected = _terminal_results_for_dispatch(initial_dispatch, result_store=result_store)

    if ready:
        current = build_today_actions(
            profile=profile,
            opportunities=opportunities,
            evidence_facts_by_opportunity=evidence_facts_by_opportunity,
            model_outputs_by_opportunity=ready,
        )
    else:
        current = initial
    current = _apply_rejected_terminal_state(current, rejected)

    internal_dispatch = build_today_actions_agnes_dispatch(
        profile_id=profile_id,
        today_actions=current,
        now=now,
    )
    return TodayActionsServiceCycle(
        public_today_actions=current,
        internal_dispatch=internal_dispatch,
        reused_ready_count=len(ready),
        reused_rejected_count=len(rejected),
    )
