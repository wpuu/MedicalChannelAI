from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .agnes_global_lease import AgnesLeaseStore, release_global_lease
from .agnes_scheduler import claim_next_agnes_task
from .model_decision_contract import (
    ACTION_LABELS,
    REASON_LABELS,
    RISK_LABELS,
    GroundedFact,
    ModelDecisionError,
    ModelDecisionInput,
    render_model_decision,
    validate_model_decision,
)


ModelCall = Callable[[dict[str, Any]], dict[str, Any]]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class TodayActionsWorkerResult:
    status: str
    task_id: str | None
    opportunity_id: str | None
    worker_id: str
    lease_id: str | None
    provider_start_allowed: bool
    lease_released: bool | None
    validated_output: dict[str, Any] | None
    rendered_decision: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    retry_after: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "status": self.status,
            "task_id": self.task_id,
            "opportunity_id": self.opportunity_id,
            "worker_id": self.worker_id,
            "lease_id": self.lease_id,
            "provider_start_allowed": self.provider_start_allowed,
            "lease_released": self.lease_released,
            "validated_output": self.validated_output,
            "rendered_decision": self.rendered_decision,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retry_after": self.retry_after,
        }


def _nonempty_strings(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ModelDecisionError("MODEL_INPUT_INVALID", f"{field_name} must be a non-empty string array")
    if len(value) != len(set(value)):
        raise ModelDecisionError("MODEL_INPUT_INVALID", f"{field_name} must not contain duplicates")
    return tuple(value)


def _hydrate_model_input(payload: dict[str, Any]) -> ModelDecisionInput:
    """Re-hydrate an already-grounded model input and fail closed on drift."""

    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        raise ModelDecisionError("MODEL_INPUT_INVALID", "model_input schema_version must be 0.1")
    opportunity_id = payload.get("opportunity_id")
    match_status = payload.get("match_status")
    recommendation_mode = payload.get("recommendation_mode")
    lifecycle_state = payload.get("lifecycle_state")
    if not all(isinstance(item, str) and item.strip() for item in (opportunity_id, match_status, recommendation_mode, lifecycle_state)):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "model_input identity/status fields are required")

    actions = _nonempty_strings(payload.get("allowed_action_types"), "allowed_action_types")
    reasons = _nonempty_strings(payload.get("allowed_reason_codes"), "allowed_reason_codes")
    risks = _nonempty_strings(payload.get("allowed_risk_codes"), "allowed_risk_codes")
    if any(item not in ACTION_LABELS for item in actions):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "allowed_action_types contains unknown enum")
    if any(item not in REASON_LABELS for item in reasons):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "allowed_reason_codes contains unknown enum")
    if any(item not in RISK_LABELS for item in risks):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "allowed_risk_codes contains unknown enum")

    raw_facts = payload.get("grounded_facts")
    if not isinstance(raw_facts, list) or not raw_facts:
        raise ModelDecisionError("MODEL_INPUT_INVALID", "grounded_facts must be non-empty")
    facts: list[GroundedFact] = []
    seen_fact_ids: set[str] = set()
    for row in raw_facts:
        if not isinstance(row, dict):
            raise ModelDecisionError("MODEL_INPUT_INVALID", "grounded fact must be object")
        values = [row.get("fact_id"), row.get("field_name"), row.get("field_value"), row.get("source_url")]
        if any(not isinstance(item, str) or not item.strip() for item in values):
            raise ModelDecisionError("MODEL_INPUT_INVALID", "grounded fact fields must be non-empty strings")
        fact_id = str(row["fact_id"])
        if fact_id in seen_fact_ids:
            raise ModelDecisionError("MODEL_INPUT_INVALID", "grounded fact ids must be unique")
        seen_fact_ids.add(fact_id)
        facts.append(
            GroundedFact(
                fact_id=fact_id,
                field_name=str(row["field_name"]),
                field_value=str(row["field_value"]),
                source_url=str(row["source_url"]),
            )
        )

    context = payload.get("confirmed_profile_context")
    budget = payload.get("input_budget")
    if not isinstance(context, dict) or not isinstance(budget, dict):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "confirmed_profile_context/input_budget must be objects")
    required_budget = (
        "source_verified_fact_count",
        "included_fact_count",
        "omitted_fact_count",
        "included_fact_chars",
        "max_facts",
        "max_fact_chars",
    )
    if any(not isinstance(budget.get(key), int) or int(budget[key]) < 0 for key in required_budget):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "input_budget fields must be non-negative integers")
    if budget["max_facts"] < 1 or budget["max_fact_chars"] < 1:
        raise ModelDecisionError("MODEL_INPUT_INVALID", "input_budget limits must be positive")
    if budget["included_fact_count"] != len(facts):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "included_fact_count does not match grounded_facts")
    if budget["source_verified_fact_count"] != budget["included_fact_count"] + budget["omitted_fact_count"]:
        raise ModelDecisionError("MODEL_INPUT_INVALID", "source/omitted fact counts are inconsistent")
    if budget["included_fact_count"] > budget["max_facts"] or budget["included_fact_chars"] > budget["max_fact_chars"]:
        raise ModelDecisionError("MODEL_INPUT_INVALID", "serialized model input exceeds its declared budget")

    return ModelDecisionInput(
        opportunity_id=str(opportunity_id),
        match_status=str(match_status),
        recommendation_mode=str(recommendation_mode),
        lifecycle_state=str(lifecycle_state),
        allowed_action_types=actions,
        allowed_reason_codes=reasons,
        allowed_risk_codes=risks,
        grounded_facts=tuple(facts),
        confirmed_profile_context=context,
        grounded_fact_source_count=int(budget["source_verified_fact_count"]),
        grounded_fact_omitted_count=int(budget["omitted_fact_count"]),
        grounded_fact_char_count=int(budget["included_fact_chars"]),
        max_grounded_facts=int(budget["max_facts"]),
        max_grounded_fact_chars=int(budget["max_fact_chars"]),
    )


def execute_next_today_actions_task(
    today_dispatch: dict[str, Any],
    *,
    store: AgnesLeaseStore,
    worker_id: str,
    now: datetime,
    model_call: ModelCall,
    clock: Clock | None = None,
) -> TodayActionsWorkerResult:
    """Claim and execute one already-authorized Today Actions model request.

    ``model_call`` is injected so this trusted orchestration layer never stores API
    keys or hard-codes provider transport. Every provider call requires a claimed
    global lease. Serialized model input is re-validated before the call, model output
    is grounded against the locked input, and the lease is released on every claimed
    path.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    if today_dispatch.get("source") != "TODAY_ACTIONS":
        raise ValueError("today_dispatch source must be TODAY_ACTIONS")
    dispatch_plan = today_dispatch.get("agnes_dispatch_plan")
    payloads = today_dispatch.get("task_payloads")
    if not isinstance(dispatch_plan, dict) or not isinstance(payloads, list):
        raise ValueError("today_dispatch plan/payloads are required")

    claim = claim_next_agnes_task(dispatch_plan, store=store, worker_id=worker_id, now=now)
    if claim.get("status") != "CLAIMED":
        return TodayActionsWorkerResult(
            status="NOT_CLAIMED",
            task_id=None,
            opportunity_id=None,
            worker_id=worker_id,
            lease_id=None,
            provider_start_allowed=False,
            lease_released=None,
            validated_output=None,
            rendered_decision=None,
            error_code=str(claim.get("status") or "CLAIM_FAILED"),
            error_message=None,
            retry_after=claim.get("retry_after"),
        )

    task = claim["task"]
    lease = claim["lease_decision"]
    task_id = str(task["task_id"])
    lease_id = str(lease["lease_id"])
    matching = [row for row in payloads if isinstance(row, dict) and row.get("task_id") == task_id]

    opportunity_id: str | None = None
    status = "WORKER_ERROR"
    validated_output: dict[str, Any] | None = None
    rendered_decision: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None

    try:
        if len(matching) != 1:
            status = "PAYLOAD_ERROR"
            error_code = "TASK_PAYLOAD_IDENTITY_INVALID"
            error_message = "claimed task must have exactly one payload"
        else:
            payload = matching[0]
            opportunity_id = payload.get("opportunity_id") if isinstance(payload.get("opportunity_id"), str) else None
            model_input_raw = payload.get("model_input")
            if not isinstance(model_input_raw, dict) or model_input_raw.get("opportunity_id") != opportunity_id:
                raise ModelDecisionError("MODEL_INPUT_INVALID", "task payload opportunity/model input mismatch")
            model_input = _hydrate_model_input(model_input_raw)

            try:
                raw_output = model_call(model_input.as_dict())
            except Exception as exc:  # deployment transport/provider error
                status = "PROVIDER_ERROR"
                error_code = "MODEL_CALL_FAILED"
                error_message = f"{type(exc).__name__}: {exc}"
            else:
                try:
                    validated_output = validate_model_decision(raw_output, model_input)
                    rendered_decision = render_model_decision(validated_output)
                    status = "READY"
                except ModelDecisionError as exc:
                    status = "MODEL_OUTPUT_REJECTED"
                    error_code = exc.code
                    error_message = str(exc)
    except ModelDecisionError as exc:
        status = "PAYLOAD_ERROR"
        error_code = exc.code
        error_message = str(exc)

    finish_clock = clock or (lambda: datetime.now(timezone.utc))
    finished_at = finish_clock()
    if finished_at.tzinfo is None or finished_at.utcoffset() is None:
        raise ValueError("clock must return timezone-aware datetime")
    lease_released = release_global_lease(
        store,
        lease_id=lease_id,
        worker_id=worker_id,
        now=finished_at,
    )
    if not lease_released:
        status = "LEASE_RELEASE_FAILED"
        error_code = "GLOBAL_LEASE_RELEASE_FAILED"
        error_message = "claimed Agnes lease could not be released by the same worker"
        validated_output = None
        rendered_decision = None

    return TodayActionsWorkerResult(
        status=status,
        task_id=task_id,
        opportunity_id=opportunity_id,
        worker_id=worker_id,
        lease_id=lease_id,
        provider_start_allowed=True,
        lease_released=lease_released,
        validated_output=validated_output,
        rendered_decision=rendered_decision,
        error_code=error_code,
        error_message=error_message,
        retry_after=None,
    )
