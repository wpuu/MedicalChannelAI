from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Protocol

from .agnes_client import AgnesClientError
from .agnes_global_lease import AgnesLeaseStore, acquire_global_lease, release_global_lease
from .outreach_contract import (
    OutreachContractError,
    build_outreach_model_input,
    outreach_input_sha256,
    render_outreach_draft,
    validate_outreach_model_output,
)
from .today_actions_http import TrustedPrincipal


ModelCall = Callable[[dict[str, Any]], dict[str, Any]]
Clock = Callable[[], datetime]


class OutreachRepository(Protocol):
    def load_profile(self, tenant_id: str, profile_id: str) -> dict[str, Any] | None: ...
    def load_public_opportunity(self, opportunity_id: str) -> dict[str, Any] | None: ...
    def load_evidence(self, tenant_id: str, opportunity_ids: list[str]) -> dict[str, list[dict[str, Any]]]: ...


class OutreachServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class OutreachServiceResult:
    public_result: dict[str, Any]
    cached: bool


class SQLiteOutreachResultStore:
    """Single-host immutable outreach cache keyed by locked input fingerprint."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_private_outreach_results ("
                "task_id TEXT PRIMARY KEY, "
                "tenant_id TEXT NOT NULL, "
                "profile_id TEXT NOT NULL, "
                "opportunity_id TEXT NOT NULL, "
                "input_sha256 TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "payload TEXT NOT NULL, "
                "UNIQUE(tenant_id, profile_id, opportunity_id, input_sha256))"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(
        self,
        *,
        principal: TrustedPrincipal,
        opportunity_id: str,
        input_sha256: str,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM medical_private_outreach_results "
                "WHERE tenant_id=? AND profile_id=? AND opportunity_id=? AND input_sha256=?",
                (principal.tenant_id, principal.profile_id, opportunity_id, input_sha256),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, dict) or payload.get("opportunity_id") != opportunity_id:
            raise RuntimeError("stored outreach result identity mismatch")
        return copy.deepcopy(payload)

    def put_if_absent(
        self,
        *,
        task_id: str,
        principal: TrustedPrincipal,
        opportunity_id: str,
        input_sha256: str,
        created_at: datetime,
        payload: dict[str, Any],
    ) -> bool:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO medical_private_outreach_results("
                "task_id, tenant_id, profile_id, opportunity_id, input_sha256, created_at, payload"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    principal.tenant_id,
                    principal.profile_id,
                    opportunity_id,
                    input_sha256,
                    created_at.astimezone(timezone.utc).isoformat(),
                    encoded,
                ),
            )
        return cursor.rowcount == 1


def _task_id(principal: TrustedPrincipal, opportunity_id: str, input_sha256: str) -> str:
    return (
        f"outreach|{principal.tenant_id}|{principal.profile_id}|"
        f"{opportunity_id}|{input_sha256[:24]}"
    )


class GroundedOutreachService:
    def __init__(
        self,
        *,
        repository: OutreachRepository,
        result_store: SQLiteOutreachResultStore,
        lease_store: AgnesLeaseStore,
        model_call: ModelCall | None,
        worker_id: str = "pilot-outreach-http",
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._result_store = result_store
        self._lease_store = lease_store
        self._model_call = model_call
        self._worker_id = worker_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def generate(
        self,
        *,
        principal: TrustedPrincipal,
        opportunity_id: str,
        now: datetime,
    ) -> OutreachServiceResult:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        profile = self._repository.load_profile(principal.tenant_id, principal.profile_id)
        if profile is None:
            raise OutreachServiceError("PROFILE_NOT_FOUND", "authenticated profile does not exist")
        opportunity = self._repository.load_public_opportunity(opportunity_id)
        if opportunity is None:
            raise OutreachServiceError("OPPORTUNITY_NOT_FOUND", "public opportunity does not exist")
        facts = self._repository.load_evidence(principal.tenant_id, [opportunity_id]).get(opportunity_id, [])
        try:
            locked = build_outreach_model_input(
                profile=profile,
                opportunity=opportunity,
                evidence_facts=facts,
            )
        except OutreachContractError as exc:
            raise OutreachServiceError(exc.code, str(exc)) from exc

        model_input = locked.as_dict()
        input_hash = outreach_input_sha256(model_input)
        task_id = _task_id(principal, opportunity_id, input_hash)
        cached = self._result_store.get(
            principal=principal,
            opportunity_id=opportunity_id,
            input_sha256=input_hash,
        )
        if cached is not None:
            public = copy.deepcopy(cached)
            public["cached"] = True
            return OutreachServiceResult(public, True)

        if self._model_call is None:
            raise OutreachServiceError(
                "OUTREACH_PROVIDER_NOT_CONFIGURED",
                "server has no outreach model provider configured",
            )

        lease = acquire_global_lease(
            self._lease_store,
            dispatch_item={
                "task_id": task_id,
                "task_type": "INTERACTIVE_DEEP_DIVE",
                "not_before": now.isoformat(),
                "requires_global_lease": True,
            },
            worker_id=self._worker_id,
            now=now,
        )
        if lease.status != "GRANTED" or not lease.lease_id:
            raise OutreachServiceError(
                "OUTREACH_PROVIDER_DEFERRED",
                lease.reason,
                retry_after=lease.retry_after,
            )

        raw_output: dict[str, Any] | None = None
        error: Exception | None = None
        finished_at: datetime | None = None
        try:
            raw_output = self._model_call(model_input)
        except Exception as exc:
            error = exc
        finally:
            finished_at = self._clock()
            if finished_at.tzinfo is None or finished_at.utcoffset() is None:
                raise ValueError("outreach clock must return timezone-aware datetime")
            released = release_global_lease(
                self._lease_store,
                lease_id=lease.lease_id,
                worker_id=self._worker_id,
                now=finished_at,
            )
            if not released:
                raise OutreachServiceError(
                    "OUTREACH_LEASE_RELEASE_FAILED",
                    "outreach provider lease could not be released",
                )

        if error is not None:
            if isinstance(error, AgnesClientError):
                raise OutreachServiceError(error.error_class, error.message) from error
            raise OutreachServiceError(
                "OUTREACH_MODEL_CALL_FAILED",
                f"outreach model call failed: {type(error).__name__}",
            ) from error
        if raw_output is None:
            raise OutreachServiceError("OUTREACH_MODEL_OUTPUT_EMPTY", "outreach model returned no object")
        try:
            validated = validate_outreach_model_output(raw_output, locked)
            rendered = render_outreach_draft(validated, locked, generated_at=finished_at)
        except OutreachContractError as exc:
            raise OutreachServiceError(exc.code, str(exc)) from exc

        persisted = copy.deepcopy(rendered)
        persisted["cached"] = False
        self._result_store.put_if_absent(
            task_id=task_id,
            principal=principal,
            opportunity_id=opportunity_id,
            input_sha256=input_hash,
            created_at=finished_at,
            payload=persisted,
        )
        winner = self._result_store.get(
            principal=principal,
            opportunity_id=opportunity_id,
            input_sha256=input_hash,
        )
        if winner is None:
            raise RuntimeError("outreach result disappeared after persistence")
        winner["cached"] = not bool(persisted == winner)
        return OutreachServiceResult(winner, bool(winner.get("cached")))
