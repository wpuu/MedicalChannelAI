from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .agnes_dispatch_queue import AgnesDispatchQueue, queue_today_actions_dispatch
from .agnes_task_result import AgnesTaskResultStore
from .query_budget import build_query_execution_plan
from .today_actions_service import TodayActionsServiceCycle, build_today_actions_service_cycle


class TodayActionsRepository(Protocol):
    """Server-side data port; implementations must enforce tenant ownership."""

    def load_profile(self, tenant_id: str, profile_id: str) -> dict[str, Any] | None: ...

    def list_opportunities(
        self,
        tenant_id: str,
        profile: dict[str, Any],
        *,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def load_evidence(
        self,
        tenant_id: str,
        opportunity_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]: ...


@dataclass(frozen=True)
class TodayActionsApiResponse:
    status_code: int
    body: dict[str, Any]


def _validate_identity(tenant_id: str, profile_id: str) -> None:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ValueError("profile_id is required")


def build_today_actions_api_response(
    *,
    tenant_id: str,
    profile_id: str,
    repository: TodayActionsRepository,
    result_store: AgnesTaskResultStore,
    now: datetime,
    dispatch_queue: AgnesDispatchQueue | None = None,
) -> TodayActionsApiResponse:
    """Application boundary for GET /today.

    Tenant/profile ownership is resolved server-side, candidate retrieval is bounded
    by Query Budget, and only the Public View crosses the response boundary. Pending
    Agnes work is optionally written to the server-only idempotent dispatch queue;
    repeated browser refreshes therefore do not multiply identical model jobs.
    """

    _validate_identity(tenant_id, profile_id)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    profile = repository.load_profile(tenant_id, profile_id)
    if profile is None:
        return TodayActionsApiResponse(404, {"error": "PROFILE_NOT_FOUND"})
    if profile.get("profile_id") != profile_id or profile.get("tenant_id") != tenant_id:
        return TodayActionsApiResponse(404, {"error": "PROFILE_NOT_FOUND"})

    query_plan = build_query_execution_plan(profile, mode="INTERACTIVE_DAILY")
    limit = int(query_plan["budgets"]["max_db_candidates"])
    opportunities = repository.list_opportunities(tenant_id, profile, limit=limit)
    if not isinstance(opportunities, list):
        raise ValueError("repository.list_opportunities must return a list")
    if len(opportunities) > limit:
        opportunities = opportunities[:limit]

    ids = [
        item.get("opportunity_id")
        for item in opportunities
        if isinstance(item, dict) and isinstance(item.get("opportunity_id"), str)
    ]
    evidence = repository.load_evidence(tenant_id, ids)
    if not isinstance(evidence, dict):
        raise ValueError("repository.load_evidence must return a mapping")

    cycle: TodayActionsServiceCycle = build_today_actions_service_cycle(
        profile=profile,
        opportunities=opportunities,
        evidence_facts_by_opportunity=evidence,
        result_store=result_store,
        now=now,
    )
    if dispatch_queue is not None and cycle.internal_dispatch.get("model_request_count", 0) > 0:
        queue_today_actions_dispatch(dispatch_queue, cycle.internal_dispatch, enqueued_at=now)

    public = cycle.public_response()
    if "model_requests" in public or "agnes_dispatch_plan" in public or "task_payloads" in public:
        raise RuntimeError("internal model orchestration leaked into Today Actions public response")
    return TodayActionsApiResponse(200, public)


def get_today_opportunity_api_response(
    *,
    tenant_id: str,
    profile_id: str,
    opportunity_id: str,
    repository: TodayActionsRepository,
    result_store: AgnesTaskResultStore,
    now: datetime,
    dispatch_queue: AgnesDispatchQueue | None = None,
) -> TodayActionsApiResponse:
    """Application boundary for GET /opportunity/:id within the current Today Top5."""

    if not isinstance(opportunity_id, str) or not opportunity_id.strip():
        raise ValueError("opportunity_id is required")
    today = build_today_actions_api_response(
        tenant_id=tenant_id,
        profile_id=profile_id,
        repository=repository,
        result_store=result_store,
        now=now,
        dispatch_queue=dispatch_queue,
    )
    if today.status_code != 200:
        return today
    for card in today.body.get("cards") or []:
        if isinstance(card, dict) and card.get("opportunity_id") == opportunity_id:
            return TodayActionsApiResponse(200, card)
    return TodayActionsApiResponse(404, {"error": "OPPORTUNITY_NOT_FOUND"})
