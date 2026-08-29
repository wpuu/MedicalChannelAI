from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .agnes_global_lease import AgnesLeaseStore, release_global_lease
from .agnes_scheduler import claim_next_agnes_task
from .agnes_task_result import AgnesTaskResultStore, build_terminal_result
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
from .today_actions_dispatch import model_input_sha256


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
    terminal_result_reused: bool
    model_input_sha256: str | None
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
            "terminal_result_reused": self.terminal_result_reused,
            "model_input_sha256": self.model_input_sha256,
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
        facts.append(GroundedFact(fact_id, str(row["field_name"]), str(row["field_value"]), str(row["source_url"])))

    context = payload.get("confirmed_profile_context")
    budget = payload.get("input_budget")
    if not isinstance(context, dict) or not isinstance(budget, dict):
        raise ModelDecisionError("MODEL_INPUT_INVALID", "confirmed_profile_context/input_budget must be objects")
    keys = ("source_verified_fact_count", "included_fact_count", "omitted_fact_count", "included_fact_chars", "max_facts", "max_fact_chars")
    if any(not isinstance(budget.get(key), int) or int(budget[key]) < 0 for key in keys):
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
        opportunity_id=str(opportunity_id), match_status=str(match_status), recommendation_mode=str(recommendation_mode),
        lifecycle_state=str(lifecycle_state), allowed_action_types=actions, allowed_reason_codes=reasons,
        allowed_risk_codes=risks, grounded_facts=tuple(facts), confirmed_profile_context=context,
        grounded_fact_source_count=int(budget["source_verified_fact_count"]), grounded_fact_omitted_count=int(budget["omitted_fact_count"]),
        grounded_fact_char_count=int(budget["included_fact_chars"]), max_grounded_facts=int(budget["max_facts"]),
        max_grounded_fact_chars=int(budget["max_fact_chars"]),
    )


def _payload_map(today_dispatch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payloads = today_dispatch.get("task_payloads")
    if not isinstance(payloads, list):
        raise ValueError("today_dispatch task_payloads are required")
    result: dict[str, dict[str, Any]] = {}
    for row in payloads:
        if not isinstance(row, dict):
            raise ValueError("task payload must be object")
        task_id, opportunity_id = row.get("task_id"), row.get("opportunity_id")
        model_input, declared_hash = row.get("model_input"), row.get("model_input_sha256")
        if not isinstance(task_id, str) or not task_id or task_id in result:
            raise ValueError("task payload task_id must be non-empty and unique")
        if not isinstance(opportunity_id, str) or not opportunity_id:
            raise ValueError("task payload opportunity_id is required")
        if not isinstance(model_input, dict) or model_input.get("opportunity_id") != opportunity_id:
            raise ValueError("task payload model_input/opportunity_id mismatch")
        actual_hash = model_input_sha256(model_input)
        if declared_hash != actual_hash:
            raise ValueError("task payload model_input_sha256 mismatch")
        if not task_id.endswith("|" + actual_hash[:24]):
            raise ValueError("task_id is not bound to model_input_sha256")
        _hydrate_model_input(model_input)
        result[task_id] = row
    return result


def _filtered_dispatch_plan(dispatch_plan: dict[str, Any], *, result_store: AgnesTaskResultStore) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    items = dispatch_plan.get("items")
    if not isinstance(items, list):
        raise ValueError("dispatch plan items must be an array")
    retained, completed = [], []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("task_id"), str):
            raise ValueError("dispatch item identity invalid")
        terminal = result_store.get(item["task_id"])
        (retained if terminal is None else completed).append(item if terminal is None else terminal)
    filtered = copy.deepcopy(dispatch_plan)
    filtered["items"] = retained
    return filtered, completed


def _reuse_terminal_result(terminal: dict[str, Any], *, worker_id: str, lease_id: str | None = None, lease_released: bool | None = None) -> TodayActionsWorkerResult:
    return TodayActionsWorkerResult(
        status="ALREADY_COMPLETED", task_id=terminal.get("task_id"), opportunity_id=terminal.get("opportunity_id"), worker_id=worker_id,
        lease_id=lease_id, provider_start_allowed=False, lease_released=lease_released, terminal_result_reused=True,
        model_input_sha256=terminal.get("model_input_sha256"), validated_output=terminal.get("validated_output"),
        rendered_decision=terminal.get("rendered_decision"), error_code=terminal.get("error_code"), error_message=None, retry_after=None,
    )


def execute_next_today_actions_task(today_dispatch: dict[str, Any], *, store: AgnesLeaseStore, result_store: AgnesTaskResultStore,
                                    worker_id: str, now: datetime, model_call: ModelCall, clock: Clock | None = None) -> TodayActionsWorkerResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    if today_dispatch.get("source") != "TODAY_ACTIONS":
        raise ValueError("today_dispatch source must be TODAY_ACTIONS")
    dispatch_plan = today_dispatch.get("agnes_dispatch_plan")
    if not isinstance(dispatch_plan, dict):
        raise ValueError("today_dispatch agnes_dispatch_plan is required")

    payload_map = _payload_map(today_dispatch)
    dispatch_ids = {row.get("task_id") for row in dispatch_plan.get("items") or [] if isinstance(row, dict)}
    if dispatch_ids != set(payload_map):
        raise ValueError("dispatch plan and task payload identities diverged")

    filtered_plan, completed = _filtered_dispatch_plan(dispatch_plan, result_store=result_store)
    if not filtered_plan["items"]:
        if completed:
            return _reuse_terminal_result(completed[0], worker_id=worker_id)
        return TodayActionsWorkerResult("NOT_CLAIMED", None, None, worker_id, None, False, None, False, None, None, None, "NO_TASKS", None, None)

    claim = claim_next_agnes_task(filtered_plan, store=store, worker_id=worker_id, now=now)
    if claim.get("status") != "CLAIMED":
        return TodayActionsWorkerResult("NOT_CLAIMED", None, None, worker_id, None, False, None, False, None, None, None,
                                        str(claim.get("status") or "CLAIM_FAILED"), None, claim.get("retry_after"))

    task, lease = claim["task"], claim["lease_decision"]
    task_id, lease_id = str(task["task_id"]), str(lease["lease_id"])
    payload = payload_map[task_id]
    opportunity_id, input_hash = str(payload["opportunity_id"]), str(payload["model_input_sha256"])
    finish_clock = clock or (lambda: datetime.now(timezone.utc))

    raced_terminal = result_store.get(task_id)
    if raced_terminal is not None:
        finished_at = finish_clock()
        if finished_at.tzinfo is None or finished_at.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        released = release_global_lease(store, lease_id=lease_id, worker_id=worker_id, now=finished_at)
        return _reuse_terminal_result(raced_terminal, worker_id=worker_id, lease_id=lease_id, lease_released=released)

    status, validated_output, rendered_decision, error_code, error_message = "WORKER_ERROR", None, None, None, None
    model_input_raw = payload["model_input"]
    try:
        if model_input_sha256(model_input_raw) != input_hash or not task_id.endswith("|" + input_hash[:24]):
            raise ModelDecisionError("MODEL_INPUT_HASH_MISMATCH", "model input fingerprint no longer matches dispatch identity")
        model_input = _hydrate_model_input(model_input_raw)
        try:
            raw_output = model_call(model_input.as_dict())
        except Exception as exc:
            status = "PROVIDER_ERROR"
            error_code = str(getattr(exc, "error_class", None) or "MODEL_CALL_FAILED")
            error_message = f"{type(exc).__name__}: {exc}"
        else:
            try:
                validated_output = validate_model_decision(raw_output, model_input)
                rendered_decision = render_model_decision(validated_output)
                status = "READY"
            except ModelDecisionError as exc:
                status, error_code, error_message = "MODEL_OUTPUT_REJECTED", exc.code, str(exc)
    except ModelDecisionError as exc:
        status, error_code, error_message = "PAYLOAD_ERROR", exc.code, str(exc)

    finished_at = finish_clock()
    if finished_at.tzinfo is None or finished_at.utcoffset() is None:
        raise ValueError("clock must return timezone-aware datetime")

    if status in {"READY", "MODEL_OUTPUT_REJECTED"}:
        terminal = build_terminal_result(
            task_id=task_id, opportunity_id=opportunity_id, model_input_sha256=input_hash, status=status,
            completed_at=finished_at, validated_output=validated_output, rendered_decision=rendered_decision, error_code=error_code,
        )
        if not result_store.put_if_absent(task_id, terminal):
            existing = result_store.get(task_id)
            if existing is not None:
                validated_output, rendered_decision, error_code = existing.get("validated_output"), existing.get("rendered_decision"), existing.get("error_code")
                error_message, status = None, "ALREADY_COMPLETED"

    lease_released = release_global_lease(store, lease_id=lease_id, worker_id=worker_id, now=finished_at)
    if not lease_released:
        status, error_code, error_message = "LEASE_RELEASE_FAILED", "GLOBAL_LEASE_RELEASE_FAILED", "claimed Agnes lease could not be released by the same worker"
        validated_output, rendered_decision = None, None

    return TodayActionsWorkerResult(
        status, task_id, opportunity_id, worker_id, lease_id, True, lease_released, status == "ALREADY_COMPLETED", input_hash,
        validated_output, rendered_decision, error_code, error_message, None,
    )
