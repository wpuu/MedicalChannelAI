"""Offline-only stage slicing prototype; not imported by collector entrypoints.

The caller must freeze task order and provide an ownership check and a durable
checkpoint callback. Queue delivery/checkpoint atomicity is deliberately outside
this prototype. A checksum detects corruption, not an untrusted writer.
"""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable


class CursorInvalid(ValueError):
    pass


class CycleCancelled(RuntimeError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _seal(cursor: dict[str, Any]) -> dict[str, Any]:
    cursor = deepcopy(cursor)
    cursor.pop("digest", None)
    cursor["digest"] = _digest(cursor)
    return cursor


def _number(value: Any) -> bool:
    return type(value) in (float, int) and math.isfinite(value)


@dataclass(frozen=True)
class SliceResult:
    action: str
    cursor: dict[str, Any]
    elapsed_seconds: float
    processed: int
    request_count: int


class StageSlice:
    """Serial pure logic with an absolute wall-clock expiry and monotonic budget.

    Work callbacks must honor the supplied timeout; socket inactivity timeouts
    alone do not guarantee a total request deadline. Results arriving after the
    budget are discarded, so they cannot skip unchecked work on continuation.
    """

    def __init__(
        self,
        *,
        cycle_id: str,
        stage: str,
        task_ids: list[str],
        plan_hash: str,
        expires_at: float,
        monotonic: Callable[[], float],
        wall_time: Callable[[], float],
        owns_cycle: Callable[[], bool],
        budget_seconds: float = 240,
        reserve_seconds: float = 15,
        request_timeout: float = 90,
        minimum_timeout: float = 5,
        delay_seconds: float = 4,
    ) -> None:
        values = (expires_at, budget_seconds, reserve_seconds, request_timeout,
                  minimum_timeout, delay_seconds)
        if not all(_number(v) for v in values):
            raise ValueError("BUDGET_NUMBER_INVALID")
        if not (0 < reserve_seconds < budget_seconds <= 240):
            raise ValueError("BUDGET_LIMIT_INVALID")
        if not (0 < minimum_timeout <= request_timeout and delay_seconds >= 0):
            raise ValueError("REQUEST_LIMIT_INVALID")
        if not all(isinstance(v, str) and v for v in (cycle_id, stage, plan_hash)) or not isinstance(task_ids, list):
            raise ValueError("CURSOR_BINDING_REQUIRED")
        if any(not isinstance(t, str) or not t for t in task_ids) or len(set(task_ids)) != len(task_ids):
            raise ValueError("TASK_IDS_INVALID")
        self.binding = {
            "version": 1, "cycle_id": cycle_id, "stage": stage,
            "plan_hash": plan_hash, "tasks_hash": _digest(task_ids),
            "task_count": len(task_ids), "expires_at": expires_at,
        }
        self.task_ids = list(task_ids)
        self.monotonic, self.wall_time, self.owns_cycle = monotonic, wall_time, owns_cycle
        self.budget, self.reserve = budget_seconds, reserve_seconds
        self.request_timeout, self.minimum_timeout = request_timeout, minimum_timeout
        self.delay = delay_seconds

    def _owned(self) -> None:
        if not self.owns_cycle():
            raise CycleCancelled("CYCLE_CANCELLED_OR_SUPERSEDED")
        now = self.wall_time()
        if not _number(now) or now >= self.binding["expires_at"]:
            raise CursorInvalid("CURSOR_EXPIRED")

    def cursor(self, value: dict[str, Any] | None) -> dict[str, Any]:
        self._owned()
        if value is None:
            return _seal({**self.binding, "index": 0, "revision": 0,
                          "results": [], "status": "PENDING"})
        try:
            raw = deepcopy(value)
            if not isinstance(raw, dict):
                raise ValueError()
            digest = raw.pop("digest")
            if set(raw) != set(self.binding) | {"index", "revision", "results", "status"}:
                raise ValueError()
            if digest != _digest(raw) or _json({k: raw[k] for k in self.binding}) != _json(self.binding):
                raise ValueError()
            index, revision, results = raw["index"], raw["revision"], raw["results"]
            if type(index) is not int or not 0 <= index <= len(self.task_ids):
                raise ValueError()
            if type(revision) is not int or revision != index:
                raise ValueError()
            if not isinstance(results, list) or len(results) != index:
                raise ValueError()
            if any(not isinstance(r, dict) or r.get("task_id") != self.task_ids[i]
                   or set(r) != {"task_id", "result"} for i, r in enumerate(results)):
                raise ValueError()
            if raw["status"] not in {"PENDING", "PAUSED", "COMPLETE"}:
                raise ValueError()
            if raw["status"] == "COMPLETE" and index != len(self.task_ids):
                raise ValueError()
            if index and raw["status"] == "PENDING":
                raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise CursorInvalid("CURSOR_CORRUPT_OR_BINDING_CHANGED") from exc
        return deepcopy(value)

    def run(
        self,
        value: dict[str, Any] | None,
        *,
        work: Callable[[str, float], Any],
        sleep: Callable[[float], None],
        checkpoint: Callable[[dict[str, Any]], None],
        expected_revision: int = 0,
    ) -> SliceResult:
        current = self.cursor(value)
        if type(expected_revision) is not int or expected_revision < 0:
            raise CursorInvalid("CONTINUATION_REVISION_INVALID")
        start = self.monotonic()
        def elapsed() -> float:
            delta = self.monotonic() - start
            if not _number(delta) or delta < 0:
                raise ValueError("MONOTONIC_CLOCK_INVALID")
            return delta
        def remaining() -> float:
            return min(self.budget - self.reserve - elapsed(),
                       self.binding["expires_at"] - self.wall_time())
        if expected_revision < current["revision"]:
            return SliceResult("STALE_CONTINUATION", current, elapsed(), 0, 0)
        if expected_revision != current["revision"]:
            raise CursorInvalid("CONTINUATION_REVISION_AHEAD")
        if current["status"] == "COMPLETE":
            return SliceResult("ALREADY_COMPLETE", current, elapsed(), 0, 0)
        if not self.task_ids:
            current = _seal({**current, "status": "COMPLETE"})
            checkpoint(deepcopy(current))
            self._owned()
            return SliceResult("COMPLETE", current, elapsed(), 0, 0)
        count = requests = 0
        while current["index"] < len(self.task_ids):
            self._owned()
            if remaining() <= self.delay + self.minimum_timeout:
                break
            sleep(self.delay)
            self._owned()
            available = remaining()
            if available <= self.minimum_timeout:
                break
            timeout = min(self.request_timeout, available)
            task_id = self.task_ids[current["index"]]
            requests += 1
            try:
                result = work(task_id, timeout)
            except TimeoutError:
                # A shortened timeout caused by this slice is a pause, not a
                # completed search or a permanent source failure.
                self._owned()
                if timeout < self.request_timeout:
                    break
                raise
            self._owned()
            if remaining() < 0:
                break
            updated = deepcopy(current)
            updated["index"] += 1
            updated["revision"] += 1
            updated["results"].append({"task_id": task_id, "result": result})
            updated["status"] = "PAUSED"
            if updated["index"] == len(self.task_ids):
                updated["status"] = "COMPLETE"
            updated = _seal(updated)
            self._owned()
            checkpoint(deepcopy(updated))
            # Do not acknowledge work when its checkpoint failed or the cycle
            # changed while saving. Persistence still needs a real write fence.
            self._owned()
            current = updated
            count += 1
        action = "COMPLETE" if current["status"] == "COMPLETE" else "PAUSED"
        current = _seal({**current, "status": "COMPLETE" if action == "COMPLETE" else "PAUSED"})
        return SliceResult(action, current, elapsed(), count, requests)
