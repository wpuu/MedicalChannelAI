from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .agnes_global_lease import AgnesLeaseStore, LeaseDecision, acquire_global_lease


GLOBAL_DEFERRED = {
    "DEFERRED_IN_FLIGHT",
    "DEFERRED_RPM",
    "DEFERRED_SPACING",
    "DEFERRED_CONTENTION",
}


def _aware(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed


def claim_next_agnes_task(
    dispatch_plan: dict[str, Any],
    *,
    store: AgnesLeaseStore,
    worker_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Claim the next due Agnes task only after obtaining the persistent global lease.

    This is the provider-start scheduler boundary. It never creates model tasks and
    cannot override upstream admission. A worker may call Agnes only when this returns
    status=CLAIMED with provider_start_allowed=true.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if dispatch_plan.get("provider") != "AGNES" or dispatch_plan.get("model") != "agnes-2.5-flash":
        raise ValueError("dispatch plan provider/model mismatch")
    if dispatch_plan.get("requires_persistent_global_lease") is not True:
        raise ValueError("dispatch plan must require persistent global lease")
    if dispatch_plan.get("dispatch_does_not_override_model_admission") is not True:
        raise ValueError("dispatch plan admission invariant missing")
    items = dispatch_plan.get("items")
    if not isinstance(items, list):
        raise ValueError("dispatch plan items must be a list")

    current = now.astimezone(timezone.utc)
    normalized: list[tuple[int, datetime, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in items:
        if not isinstance(row, dict):
            raise ValueError("dispatch item must be object")
        task_id = str(row.get("task_id") or "")
        if not task_id or task_id in seen:
            raise ValueError("dispatch task_id must be non-empty and unique")
        seen.add(task_id)
        priority = row.get("priority")
        if not isinstance(priority, int):
            raise ValueError("dispatch priority must be integer")
        not_before = _aware(str(row.get("not_before") or ""), "not_before").astimezone(timezone.utc)
        normalized.append((priority, not_before, task_id, row))
    normalized.sort(key=lambda value: (value[0], value[1], value[2]))

    due = [value for value in normalized if value[1] <= current]
    if not due:
        next_time = min((value[1] for value in normalized), default=None)
        return {
            "schema_version": "0.1",
            "status": "NO_DUE_TASK",
            "provider_start_allowed": False,
            "task": None,
            "lease_decision": None,
            "retry_after": next_time.isoformat() if next_time else None,
        }

    duplicate_retry_after: list[datetime] = []
    for _, _, _, row in due:
        decision: LeaseDecision = acquire_global_lease(
            store,
            dispatch_item=row,
            worker_id=worker_id,
            now=now,
        )
        if decision.status == "GRANTED":
            return {
                "schema_version": "0.1",
                "status": "CLAIMED",
                "provider_start_allowed": True,
                "task": row,
                "lease_decision": decision.as_dict(),
                "retry_after": None,
            }
        if decision.status == "DEFERRED_DUPLICATE_ACTIVE":
            if decision.retry_after:
                duplicate_retry_after.append(_aware(decision.retry_after, "retry_after").astimezone(timezone.utc))
            continue
        if decision.status in GLOBAL_DEFERRED:
            return {
                "schema_version": "0.1",
                "status": "GLOBAL_CAPACITY_DEFERRED",
                "provider_start_allowed": False,
                "task": None,
                "lease_decision": decision.as_dict(),
                "retry_after": decision.retry_after,
            }
        if decision.status == "DEFERRED_NOT_BEFORE":
            # The scheduler pre-filtered due items. Seeing this means clock/plan state
            # changed under us; fail closed rather than starting the provider.
            return {
                "schema_version": "0.1",
                "status": "PLAN_TIME_DEFERRED",
                "provider_start_allowed": False,
                "task": None,
                "lease_decision": decision.as_dict(),
                "retry_after": decision.retry_after,
            }
        raise ValueError(f"unsupported lease decision status: {decision.status}")

    next_future = [value[1] for value in normalized if value[1] > current]
    retry_candidates = duplicate_retry_after + next_future
    retry_after = min(retry_candidates).isoformat() if retry_candidates else None
    return {
        "schema_version": "0.1",
        "status": "NO_CLAIMABLE_DUE_TASK",
        "provider_start_allowed": False,
        "task": None,
        "lease_decision": None,
        "retry_after": retry_after,
    }
