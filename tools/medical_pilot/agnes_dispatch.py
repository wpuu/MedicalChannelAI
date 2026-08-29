from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).with_name("agnes_dispatch.v0.1.json")


@dataclass(frozen=True)
class AgnesDispatchItem:
    task_id: str
    task_type: str
    priority: int
    requested_at: str
    not_before: str
    start_spacing_seconds: int
    stable_jitter_seconds: int
    requires_global_lease: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "priority": self.priority,
            "requested_at": self.requested_at,
            "not_before": self.not_before,
            "start_spacing_seconds": self.start_spacing_seconds,
            "stable_jitter_seconds": self.stable_jitter_seconds,
            "requires_global_lease": self.requires_global_lease,
        }


def load_agnes_dispatch_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _aware(value: str, field_name: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone")
    return result


def _stable_int(value: str, modulus: int) -> int:
    if modulus <= 0:
        return 0
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def build_agnes_dispatch_plan(
    tasks: list[dict[str, Any]],
    *,
    now: datetime,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    """Build a deterministic staggered start plan; this does not call Agnes.

    The plan is intentionally not a substitute for a distributed token bucket.
    Every start still requires a persistent global lease when more than one worker exists.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    policy = load_agnes_dispatch_policy(policy_path)
    priorities = policy["task_priorities"]
    max_tasks = int(policy["max_tasks_per_plan"])
    if len(tasks) > max_tasks:
        raise ValueError(f"task count exceeds max_tasks_per_plan={max_tasks}")

    normalized: list[tuple[int, datetime, str, dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for task in tasks:
        task_id = str(task.get("task_id") or "").strip()
        task_type = str(task.get("task_type") or "").strip()
        requested_raw = str(task.get("requested_at") or "").strip()
        if not task_id or task_id in seen_ids:
            raise ValueError("task_id must be non-empty and unique")
        if task_type not in priorities:
            raise ValueError(f"unsupported Agnes task_type: {task_type}")
        requested = _aware(requested_raw, "requested_at")
        seen_ids.add(task_id)
        normalized.append((int(priorities[task_type]), requested, task_id, task))

    normalized.sort(key=lambda item: (item[0], item[1], item[2]))
    spacing = int(policy["minimum_start_spacing_seconds"])
    max_starts = int(policy["max_request_starts_per_minute"])
    if spacing < 1 or max_starts < 1:
        raise ValueError("invalid Agnes dispatch rate policy")
    if spacing * max_starts < 60:
        raise ValueError("minimum_start_spacing_seconds is too small for max_request_starts_per_minute")

    jitter_cap = int(policy.get("stable_extra_jitter_seconds") or 0)
    # Avoid exact-second batch starts. The first slot itself gets a stable small offset.
    initial_offset = 1 + _stable_int("|".join(item[2] for item in normalized) or "empty", max(1, spacing))
    cursor = now + timedelta(seconds=initial_offset)
    output: list[AgnesDispatchItem] = []

    for priority, requested, task_id, task in normalized:
        task_type = str(task["task_type"])
        stable_jitter = _stable_int(task_id, jitter_cap + 1)
        earliest = max(now, requested.astimezone(now.tzinfo))
        candidate = max(cursor, earliest) + timedelta(seconds=stable_jitter)
        output.append(
            AgnesDispatchItem(
                task_id=task_id,
                task_type=task_type,
                priority=priority,
                requested_at=requested.isoformat(),
                not_before=candidate.isoformat(),
                start_spacing_seconds=spacing,
                stable_jitter_seconds=stable_jitter,
                requires_global_lease=True,
            )
        )
        cursor = candidate + timedelta(seconds=spacing)

    return {
        "schema_version": "0.1",
        "provider": policy["provider"],
        "model": policy["model"],
        "planned_at": now.isoformat(),
        "max_request_starts_per_minute": max_starts,
        "minimum_start_spacing_seconds": spacing,
        "max_in_flight": int(policy["max_in_flight"]),
        "requires_persistent_global_lease": True,
        "dispatch_does_not_override_model_admission": True,
        "items": [item.as_dict() for item in output],
    }


def retry_delay_seconds(
    *,
    task_id: str,
    error_class: str,
    attempt: int,
    policy_path: Path = POLICY_PATH,
) -> int:
    if attempt < 0:
        raise ValueError("attempt cannot be negative")
    policy = load_agnes_dispatch_policy(policy_path)
    retry = policy["retry_policy"].get(error_class)
    if not retry:
        raise ValueError(f"unsupported retry error_class: {error_class}")
    base = int(retry["base_seconds"])
    multiplier = int(retry["multiplier"])
    maximum = int(retry["max_seconds"])
    jitter_cap = int(retry.get("stable_jitter_seconds") or 0)
    delay = min(maximum, base * (multiplier ** attempt))
    return delay + _stable_int(f"{task_id}|{error_class}|{attempt}", jitter_cap + 1)
