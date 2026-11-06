"""Local-stub-only physical-key and deadline guard around the frozen kernel.

Markers/scope are assertions about trusted test objects, never authentication or
a sandbox for arbitrary Python. No SDK, client construction, threads or retries.
Timeouts are passed to the transport and checked on return; a blocking transport
cannot be preempted here. Real runtime integration remains NO-GO.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable, Protocol

import collector_readonly_export as core
from collector_epoch import epoch_key


class SyntheticTransport(Protocol):
    input_kind: str
    target_scope: dict

    def get(self, key: str, *, timeout_seconds: float) -> Any: ...


class SyntheticGetOnlyGuard:
    """One fixed two-pass run; the first rejection permanently closes the guard."""

    def __init__(self, transport: SyntheticTransport, *, scope: dict,
                 expected_scope: dict, monotonic: Callable[[], float] = time.monotonic):
        self._failed = False
        self._closed = False
        self._calls = 0
        self._clock = monotonic
        self._last_time = None
        self._started = self._now()
        self._read_deadline = self._started + 110.0
        self._total_deadline = self._started + 120.0
        if not (self._started < self._read_deadline < self._total_deadline):
            self._reject("GUARD_CLOCK_INVALID")
        if type(scope) is not dict or type(expected_scope) is not dict or (
            scope != core._D_SCOPE or expected_scope != core._D_SCOPE
        ):
            self._reject("EXPORT_SCOPE_REJECTED")
        self._transport = transport
        self._check_transport()
        keys = tuple(epoch_key(key, core._D_SCOPE["preview_epoch"]) for key in core._plan())
        if len(keys) != 58 or len(set(keys)) != 58:
            self._reject("GUARD_PLAN_CHANGED")
        self._allowed = frozenset(keys)
        self._sequence = keys * 2

    def _check_transport(self) -> None:
        try:
            marker = getattr(self._transport, "input_kind", None)
            declared = getattr(self._transport, "target_scope", None)
            has_get = callable(getattr(self._transport, "get", None))
            writable = any(hasattr(self._transport, method) for method in (
                "set", "delete", "expire", "expire_tag", "expireTag", "clear"))
        except Exception:
            self._reject("GUARD_TRANSPORT_INVALID")
        if marker != "SYNTHETIC_LOCAL_STUB":
            self._reject("GUARD_LOCAL_STUB_REQUIRED")
        if type(declared) is not dict or declared != core._D_SCOPE:
            self._reject("GUARD_TRANSPORT_SCOPE_REJECTED")
        if not has_get or writable:
            self._reject("EXPORT_GET_ONLY_REQUIRED")

    @property
    def call_count(self) -> int:
        return self._calls

    def _reject(self, code: str) -> None:
        self._failed = True
        self._closed = True
        raise core.ExportRejected(code)

    def _now(self) -> float:
        try:
            value = self._clock()
            if type(value) not in (int, float):
                raise ValueError()
            value = float(value)
            if not math.isfinite(value) or (self._last_time is not None and value < self._last_time):
                raise ValueError()
        except Exception:
            self._reject("GUARD_CLOCK_INVALID")
        self._last_time = value
        return value

    def _check_open(self) -> None:
        if self._failed:
            self._reject("GUARD_FAILED")
        if self._closed:
            self._reject("GUARD_CLOSED")

    def _read_time(self) -> float:
        value = self._now()
        if value >= self._total_deadline:
            self._reject("GUARD_TOTAL_DEADLINE_EXCEEDED")
        if value >= self._read_deadline:
            self._reject("GUARD_READ_DEADLINE_EXCEEDED")
        return value

    def get(self, key: str) -> Any:
        self._check_open()
        if type(key) is not str or key not in self._allowed:
            self._reject("GUARD_KEY_REJECTED")
        if self._calls >= 116:
            self._reject("GUARD_CALL_LIMIT")
        if key != self._sequence[self._calls]:
            self._reject("GUARD_KEY_ORDER_REJECTED")
        self._check_transport()
        started = self._read_time()
        timeout = min(2.0, self._read_deadline - started)
        self._calls += 1  # Failed calls also consume budget; never retry.
        try:
            value = self._transport.get(key, timeout_seconds=timeout)
        except Exception:
            self._reject("GUARD_TRANSPORT_FAILED")
        self._check_transport()
        returned = self._read_time()
        if returned - started >= timeout:
            self._reject("GUARD_GET_DEADLINE_EXCEEDED")
        return value

    def finish(self) -> None:
        """Check the entire run before delivery, including kernel processing time."""
        self._check_open()
        self._check_transport()
        if self._now() >= self._total_deadline:
            self._reject("GUARD_TOTAL_DEADLINE_EXCEEDED")
        if self._calls != 116:
            self._reject("GUARD_INCOMPLETE_READ_PLAN")
        self._closed = True


def observe_synthetic_d_canonical(transport: SyntheticTransport, *, scope: dict,
                                  expected_scope: dict,
                                  monotonic: Callable[[], float] = time.monotonic,
                                  limits: core.ExportLimits | None = None) -> dict[str, Any]:
    """Return the existing kernel envelope unchanged, or reject the whole run."""
    guard = SyntheticGetOnlyGuard(transport, scope=scope, expected_scope=expected_scope,
                                 monotonic=monotonic)
    try:
        result = core.observe_d_canonical(guard, scope=scope, expected_scope=expected_scope,
                                          limits=limits if limits is not None else core.ExportLimits())
        guard.finish()
        return result
    finally:
        guard._closed = True
