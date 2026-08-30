from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from .agnes_dispatch import load_agnes_dispatch_policy


SCHEMA_VERSION = "0.1"
STATE_KEY = "agnes-global"
DEFAULT_LEASE_TTL_SECONDS = 120
MAX_CAS_RETRIES = 8


class AgnesLeaseStore(Protocol):
    """Atomic persistent store contract for the Agnes global lease state.

    Cross-node deployments must back this contract with a shared atomic store
    (for example Postgres/Redis/D1 with equivalent transaction/CAS semantics).
    Worker-local memory or sleep is not sufficient.
    """

    def load(self) -> dict[str, Any]: ...

    def compare_and_swap(self, expected_revision: int, new_state: dict[str, Any]) -> bool: ...


@dataclass(frozen=True)
class LeaseDecision:
    status: str
    task_id: str
    worker_id: str
    decided_at: str
    lease_id: str | None
    retry_after: str | None
    active_in_flight: int
    starts_last_60_seconds: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "decided_at": self.decided_at,
            "lease_id": self.lease_id,
            "retry_after": self.retry_after,
            "active_in_flight": self.active_in_flight,
            "starts_last_60_seconds": self.starts_last_60_seconds,
            "reason": self.reason,
        }


def _aware(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone")
    return value.astimezone(timezone.utc)


def initial_lease_state(*, now: datetime) -> dict[str, Any]:
    current = _utc(now)
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "AGNES",
        "model": "agnes-2.5-flash",
        "revision": 0,
        "recent_start_timestamps": [],
        "active_leases": [],
        "last_start_at": None,
        "updated_at": current.isoformat(),
    }


def _lease_id(task_id: str, worker_id: str, acquired_at: datetime) -> str:
    digest = hashlib.sha256(
        f"{task_id}|{worker_id}|{acquired_at.isoformat()}".encode("utf-8")
    ).hexdigest()
    return "agl_" + digest


def _normalize_state(state: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    current = _utc(now)
    if state.get("provider") != "AGNES" or state.get("model") != "agnes-2.5-flash":
        raise ValueError("invalid Agnes lease state provider/model")
    revision = state.get("revision")
    if not isinstance(revision, int) or revision < 0:
        raise ValueError("invalid Agnes lease state revision")

    recent: list[str] = []
    cutoff = current - timedelta(seconds=60)
    for raw in state.get("recent_start_timestamps") or []:
        timestamp = _aware(str(raw), "recent_start_timestamp").astimezone(timezone.utc)
        if cutoff < timestamp <= current:
            recent.append(timestamp.isoformat())
    recent.sort()

    active: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    seen_leases: set[str] = set()
    for row in state.get("active_leases") or []:
        if not isinstance(row, dict):
            raise ValueError("active lease must be object")
        task_id = str(row.get("task_id") or "")
        lease_id = str(row.get("lease_id") or "")
        worker_id = str(row.get("worker_id") or "")
        expires_at = _aware(str(row.get("expires_at") or ""), "expires_at").astimezone(timezone.utc)
        acquired_at = _aware(str(row.get("acquired_at") or ""), "acquired_at").astimezone(timezone.utc)
        if not task_id or not lease_id.startswith("agl_") or not worker_id:
            raise ValueError("invalid active lease identity")
        if task_id in seen_tasks or lease_id in seen_leases:
            raise ValueError("duplicate active lease")
        seen_tasks.add(task_id)
        seen_leases.add(lease_id)
        if expires_at > current:
            active.append(
                {
                    "lease_id": lease_id,
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "acquired_at": acquired_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                }
            )

    last_start_at = state.get("last_start_at")
    if last_start_at is not None:
        last_start_at = _aware(str(last_start_at), "last_start_at").astimezone(timezone.utc).isoformat()

    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "AGNES",
        "model": "agnes-2.5-flash",
        "revision": revision,
        "recent_start_timestamps": recent,
        "active_leases": active,
        "last_start_at": last_start_at,
        "updated_at": current.isoformat(),
    }


def evaluate_lease(
    state: dict[str, Any],
    *,
    dispatch_item: dict[str, Any],
    worker_id: str,
    now: datetime,
    lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    policy_path: Path | None = None,
) -> tuple[LeaseDecision, dict[str, Any] | None]:
    """Evaluate one start request against the persisted global state.

    A GRANTED result returns the exact next state to commit atomically. Deferred
    results never mutate state. Acquiring a lease reserves one provider start.
    """

    current = _utc(now)
    worker_id = worker_id.strip()
    if not worker_id:
        raise ValueError("worker_id is required")
    if lease_ttl_seconds < 15 or lease_ttl_seconds > 900:
        raise ValueError("lease_ttl_seconds must be 15..900")
    task_id = str(dispatch_item.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("dispatch_item.task_id is required")
    if dispatch_item.get("requires_global_lease") is not True:
        raise ValueError("dispatch item must require global lease")
    not_before = _aware(str(dispatch_item.get("not_before") or ""), "not_before").astimezone(timezone.utc)

    policy = load_agnes_dispatch_policy(policy_path) if policy_path else load_agnes_dispatch_policy()
    spacing = int(policy["minimum_start_spacing_seconds"])
    max_starts = int(policy["max_request_starts_per_minute"])
    max_in_flight = int(policy["max_in_flight"])
    normalized = _normalize_state(state, now=current)
    active = list(normalized["active_leases"])
    recent = list(normalized["recent_start_timestamps"])

    def defer(status: str, retry_after: datetime | None, reason: str) -> tuple[LeaseDecision, None]:
        return (
            LeaseDecision(
                status=status,
                task_id=task_id,
                worker_id=worker_id,
                decided_at=current.isoformat(),
                lease_id=None,
                retry_after=retry_after.isoformat() if retry_after else None,
                active_in_flight=len(active),
                starts_last_60_seconds=len(recent),
                reason=reason,
            ),
            None,
        )

    if current < not_before:
        return defer("DEFERRED_NOT_BEFORE", not_before, "dispatch not_before has not been reached")
    if any(row["task_id"] == task_id for row in active):
        duplicate = next(row for row in active if row["task_id"] == task_id)
        return defer(
            "DEFERRED_DUPLICATE_ACTIVE",
            _aware(duplicate["expires_at"], "expires_at").astimezone(timezone.utc),
            "same task already has an active global lease",
        )
    if len(active) >= max_in_flight:
        earliest = min(_aware(row["expires_at"], "expires_at").astimezone(timezone.utc) for row in active)
        return defer("DEFERRED_IN_FLIGHT", earliest, "global in-flight limit reached")
    if len(recent) >= max_starts:
        oldest = _aware(recent[0], "recent_start_timestamp").astimezone(timezone.utc)
        return defer("DEFERRED_RPM", oldest + timedelta(seconds=60), "global starts-per-minute limit reached")

    last_start_raw = normalized.get("last_start_at")
    if last_start_raw:
        last_start = _aware(str(last_start_raw), "last_start_at").astimezone(timezone.utc)
        spacing_ready = last_start + timedelta(seconds=spacing)
        if current < spacing_ready:
            return defer("DEFERRED_SPACING", spacing_ready, "global minimum start spacing not reached")

    lease_id = _lease_id(task_id, worker_id, current)
    expires = current + timedelta(seconds=lease_ttl_seconds)
    next_state = dict(normalized)
    next_state["revision"] = int(normalized["revision"]) + 1
    next_state["recent_start_timestamps"] = recent + [current.isoformat()]
    next_state["last_start_at"] = current.isoformat()
    next_state["active_leases"] = active + [
        {
            "lease_id": lease_id,
            "task_id": task_id,
            "worker_id": worker_id,
            "acquired_at": current.isoformat(),
            "expires_at": expires.isoformat(),
        }
    ]
    next_state["updated_at"] = current.isoformat()
    decision = LeaseDecision(
        status="GRANTED",
        task_id=task_id,
        worker_id=worker_id,
        decided_at=current.isoformat(),
        lease_id=lease_id,
        retry_after=None,
        active_in_flight=len(active) + 1,
        starts_last_60_seconds=len(recent) + 1,
        reason="global provider start reserved by atomic lease",
    )
    return decision, next_state


def acquire_global_lease(
    store: AgnesLeaseStore,
    *,
    dispatch_item: dict[str, Any],
    worker_id: str,
    now: datetime,
    lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> LeaseDecision:
    for _ in range(MAX_CAS_RETRIES):
        state = store.load()
        decision, next_state = evaluate_lease(
            state,
            dispatch_item=dispatch_item,
            worker_id=worker_id,
            now=now,
            lease_ttl_seconds=lease_ttl_seconds,
        )
        if next_state is None:
            return decision
        if store.compare_and_swap(int(state["revision"]), next_state):
            return decision
    return LeaseDecision(
        status="DEFERRED_CONTENTION",
        task_id=str(dispatch_item.get("task_id") or ""),
        worker_id=worker_id,
        decided_at=_utc(now).isoformat(),
        lease_id=None,
        retry_after=(_utc(now) + timedelta(seconds=1)).isoformat(),
        active_in_flight=0,
        starts_last_60_seconds=0,
        reason="atomic lease store contention exceeded retry budget",
    )


def release_global_lease(
    store: AgnesLeaseStore,
    *,
    lease_id: str,
    worker_id: str,
    now: datetime,
) -> bool:
    if not lease_id.startswith("agl_") or not worker_id.strip():
        raise ValueError("valid lease_id and worker_id required")
    current = _utc(now)
    for _ in range(MAX_CAS_RETRIES):
        state = store.load()
        normalized = _normalize_state(state, now=current)
        matching = [
            row
            for row in normalized["active_leases"]
            if row["lease_id"] == lease_id and row["worker_id"] == worker_id
        ]
        if not matching:
            return False
        next_state = dict(normalized)
        next_state["revision"] = int(normalized["revision"]) + 1
        next_state["active_leases"] = [row for row in normalized["active_leases"] if row["lease_id"] != lease_id]
        next_state["updated_at"] = current.isoformat()
        if store.compare_and_swap(int(state["revision"]), next_state):
            return True
    return False


class SQLiteAgnesLeaseStore:
    """Persistent single-host reference store using SQLite CAS transactions.

    Safe for multiple processes sharing one SQLite database file on the same host.
    It is NOT the cross-server production store; multi-node deployments require a
    genuinely shared atomic database/service implementing AgnesLeaseStore.
    """

    def __init__(self, path: Path, *, now: datetime) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        initial = initial_lease_state(now=now)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS agnes_global_state ("
                "state_key TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT OR IGNORE INTO agnes_global_state(state_key, revision, payload) VALUES (?, ?, ?)",
                (STATE_KEY, 0, json.dumps(initial, ensure_ascii=False, separators=(",", ":"))),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def load(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT revision, payload FROM agnes_global_state WHERE state_key=?",
                (STATE_KEY,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Agnes global state row missing")
        payload = json.loads(row[1])
        if int(payload.get("revision", -1)) != int(row[0]):
            raise RuntimeError("Agnes global state revision mismatch")
        return payload

    def compare_and_swap(self, expected_revision: int, new_state: dict[str, Any]) -> bool:
        expected_next = expected_revision + 1
        if int(new_state.get("revision", -1)) != expected_next:
            raise ValueError("new_state revision must equal expected_revision + 1")
        payload = json.dumps(new_state, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "UPDATE agnes_global_state SET revision=?, payload=? WHERE state_key=? AND revision=?",
                (expected_next, payload, STATE_KEY, expected_revision),
            )
            if cursor.rowcount != 1:
                conn.execute("ROLLBACK")
                return False
            conn.execute("COMMIT")
            return True
