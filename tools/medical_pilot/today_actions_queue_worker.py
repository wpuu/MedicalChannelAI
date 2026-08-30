from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .agnes_dispatch import load_agnes_dispatch_policy
from .agnes_dispatch_queue import AgnesDispatchQueue, validate_queue_item
from .agnes_global_lease import AgnesLeaseStore
from .agnes_task_result import AgnesTaskResultStore
from .today_actions_worker import TodayActionsWorkerResult, execute_next_today_actions_task


ModelCall = Callable[[dict[str, Any]], dict[str, Any]]


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("queue dispatch not_before must include timezone")
    return parsed.astimezone(timezone.utc)


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


def _not_claimed(worker_id: str, code: str, retry_after: str | None = None) -> TodayActionsWorkerResult:
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
        error_code=code,
        error_message=None,
        retry_after=retry_after,
    )


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
    """Execute one due queue item through the existing trusted Worker.

    A future high-priority item must not block a lower-priority item that is already
    due. Due tasks are filtered first, then ordered by model priority/not_before/task.
    The global lease remains the final provider-start authority. Terminal work is
    removed from the queue; retryable provider/capacity states stay queued.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    rows = queue.list_pending(limit=100)
    if not rows:
        return _not_claimed(worker_id, "QUEUE_EMPTY")

    current = now.astimezone(timezone.utc)
    normalized: list[tuple[int, datetime, str, dict[str, Any]]] = []
    for row in rows:
        validate_queue_item(row)
        not_before = _aware(str(row["dispatch_item"].get("not_before") or ""))
        normalized.append(
            (
                int(row["dispatch_item"].get("priority", 999)),
                not_before,
                row["task_id"],
                row,
            )
        )

    due = [entry for entry in normalized if entry[1] <= current]
    if not due:
        next_time = min(entry[1] for entry in normalized)
        return _not_claimed(worker_id, "QUEUE_NO_DUE_TASK", next_time.isoformat())

    due.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
    selected = due[0][3]
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
