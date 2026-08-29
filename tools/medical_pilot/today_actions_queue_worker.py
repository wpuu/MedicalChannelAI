from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from .agnes_dispatch import load_agnes_dispatch_policy
from .agnes_dispatch_queue import AgnesDispatchQueue, validate_queue_item
from .agnes_global_lease import AgnesLeaseStore
from .agnes_task_result import AgnesTaskResultStore
from .today_actions_worker import TodayActionsWorkerResult, execute_next_today_actions_task


ModelCall = Callable[[dict[str, Any]], dict[str, Any]]


def _dispatch_from_queue_item(item: dict[str, Any]) -> dict[str, Any]:
    validate_queue_item(item)
    policy = load_agnes_dispatch_policy()
    dispatch_item = item["dispatch_item"]
    return {
        "schema_version": "0.1",
        "source": "TODAY_ACTIONS",
        "profile_id": item["profile_id"],
        "model_request_count": 1,
        "agnes_dispatch_plan": {
            "schema_version": "0.1",
            "provider": policy["provider"],
            "model": policy["model"],
            "planned_at": item["enqueued_at"],
            "max_request_starts_per_minute": int(policy["max_request_starts_per_minute"]),
            "minimum_start_spacing_seconds": int(policy["minimum_start_spacing_seconds"]),
            "max_in_flight": int(policy["max_in_flight"]),
            "requires_persistent_global_lease": True,
            "dispatch_does_not_override_model_admission": True,
            "items": [dispatch_item],
        },
        "task_payloads": [
            {
                "task_id": item["task_id"],
                "opportunity_id": item["opportunity_id"],
                "model_input_sha256": item["model_input_sha256"],
                "model_input": item["model_input"],
            }
        ],
    }


def execute_next_queued_today_actions_task(
    *,
    queue: AgnesDispatchQueue,
    lease_store: AgnesLeaseStore,
    result_store: AgnesTaskResultStore,
    worker_id: str,
    now: datetime,
    model_call: ModelCall,
    clock=None,
) -> TodayActionsWorkerResult:
    """Execute one earliest queue item through the existing trusted worker.

    Queue order does not override Agnes task priority/not_before/global capacity; the
    reconstructed single-task dispatch is still adjudicated by the scheduler/lease.
    Terminal READY/REJECTED/ALREADY_COMPLETED work is removed from the queue. Retryable
    provider/capacity states remain queued for a later scheduler tick.
    """

    rows = queue.list_pending(limit=100)
    if not rows:
        return TodayActionsWorkerResult(
            status="NOT_CLAIMED",
            task_id=None,
            opportunity_id=None,
            worker_id=worker_id,
            lease_id=None,
            provider_start_allowed=False,
            lease_released=None,
            terminal_result_reused=False,
            model_input_sha256=None,
            validated_output=None,
            rendered_decision=None,
            error_code="QUEUE_EMPTY",
            error_message=None,
            retry_after=None,
        )

    # Preserve the shared model priority semantics even if rows were enqueued at
    # slightly different times. not_before is the secondary key.
    rows.sort(
        key=lambda row: (
            int(row["dispatch_item"].get("priority", 999)),
            str(row["dispatch_item"].get("not_before") or ""),
            row["task_id"],
        )
    )
    selected = rows[0]
    dispatch = _dispatch_from_queue_item(selected)
    result = execute_next_today_actions_task(
        dispatch,
        store=lease_store,
        result_store=result_store,
        worker_id=worker_id,
        now=now,
        model_call=model_call,
        clock=clock,
    )

    if result.status in {"READY", "MODEL_OUTPUT_REJECTED", "ALREADY_COMPLETED"}:
        queue.delete(selected["task_id"])
    return result
