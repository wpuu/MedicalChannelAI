from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .today_actions_dispatch import model_input_sha256


class AgnesDispatchQueue(Protocol):
    """Persistent server-only queue keyed by immutable Agnes task_id."""

    def enqueue_if_absent(self, item: dict[str, Any]) -> bool: ...

    def get(self, task_id: str) -> dict[str, Any] | None: ...

    def list_pending(self, *, limit: int) -> list[dict[str, Any]]: ...

    def delete(self, task_id: str) -> bool: ...


class MemoryAgnesDispatchQueue:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def enqueue_if_absent(self, item: dict[str, Any]) -> bool:
        validate_queue_item(item)
        task_id = item["task_id"]
        if task_id in self._rows:
            return False
        self._rows[task_id] = copy.deepcopy(item)
        return True

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self._rows.get(task_id)
        return copy.deepcopy(row) if row is not None else None

    def list_pending(self, *, limit: int) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("queue list limit must be 1..1000")
        rows = sorted(self._rows.values(), key=lambda row: (row["enqueued_at"], row["task_id"]))
        return copy.deepcopy(rows[:limit])

    def delete(self, task_id: str) -> bool:
        return self._rows.pop(task_id, None) is not None


class SQLiteAgnesDispatchQueue:
    """Same-host persistent queue using task_id as the idempotency key.

    Multiple processes sharing one SQLite file are coordinated by the PRIMARY KEY.
    Horizontal multi-server deployment requires a shared database/queue with the same
    unique task-id semantics; per-VPS SQLite files are not a global queue.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS agnes_dispatch_queue ("
                "task_id TEXT PRIMARY KEY, enqueued_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agnes_dispatch_queue_time "
                "ON agnes_dispatch_queue(enqueued_at, task_id)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def enqueue_if_absent(self, item: dict[str, Any]) -> bool:
        validate_queue_item(item)
        payload = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO agnes_dispatch_queue(task_id, enqueued_at, payload) VALUES (?, ?, ?)",
                (item["task_id"], item["enqueued_at"], payload),
            )
        return cursor.rowcount == 1

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM agnes_dispatch_queue WHERE task_id=?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        item = json.loads(row[0])
        validate_queue_item(item)
        return item

    def list_pending(self, *, limit: int) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("queue list limit must be 1..1000")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM agnes_dispatch_queue ORDER BY enqueued_at, task_id LIMIT ?",
                (limit,),
            ).fetchall()
        result = [json.loads(row[0]) for row in rows]
        for item in result:
            validate_queue_item(item)
        return result

    def delete(self, task_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM agnes_dispatch_queue WHERE task_id=?", (task_id,))
        return cursor.rowcount == 1


def validate_queue_item(item: dict[str, Any]) -> None:
    if not isinstance(item, dict) or item.get("schema_version") != "0.1":
        raise ValueError("queue item schema_version must be 0.1")
    required_strings = (
        "task_id",
        "source",
        "profile_id",
        "opportunity_id",
        "model_input_sha256",
        "enqueued_at",
    )
    for key in required_strings:
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError(f"queue item {key} is required")
    if item["source"] != "TODAY_ACTIONS":
        raise ValueError("queue item source must be TODAY_ACTIONS")
    input_hash = item["model_input_sha256"]
    if len(input_hash) != 64 or any(ch not in "0123456789abcdef" for ch in input_hash):
        raise ValueError("queue item model_input_sha256 must be lowercase sha256")
    if not item["task_id"].endswith("|" + input_hash[:24]):
        raise ValueError("queue task_id is not bound to model_input_sha256")
    if f"|{item['opportunity_id']}|" not in item["task_id"]:
        raise ValueError("queue task_id is not bound to opportunity_id")
    model_input = item.get("model_input")
    dispatch_item = item.get("dispatch_item")
    if not isinstance(model_input, dict) or not isinstance(dispatch_item, dict):
        raise ValueError("queue model_input/dispatch_item must be objects")
    if model_input.get("opportunity_id") != item["opportunity_id"]:
        raise ValueError("queue model_input opportunity mismatch")
    if model_input_sha256(model_input) != input_hash:
        raise ValueError("queue model_input hash mismatch")
    if dispatch_item.get("task_id") != item["task_id"]:
        raise ValueError("queue dispatch item task mismatch")
    if dispatch_item.get("requires_global_lease") is not True:
        raise ValueError("queue dispatch item must require global lease")
    parsed = datetime.fromisoformat(item["enqueued_at"].replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("queue enqueued_at must include timezone")


def queue_today_actions_dispatch(
    queue: AgnesDispatchQueue,
    dispatch: dict[str, Any],
    *,
    enqueued_at: datetime,
) -> dict[str, int]:
    """Idempotently persist each current Today Actions task as one queue row."""

    if enqueued_at.tzinfo is None or enqueued_at.utcoffset() is None:
        raise ValueError("enqueued_at must be timezone-aware")
    if dispatch.get("source") != "TODAY_ACTIONS":
        raise ValueError("dispatch source must be TODAY_ACTIONS")
    payloads = dispatch.get("task_payloads")
    plan = dispatch.get("agnes_dispatch_plan")
    if not isinstance(payloads, list) or not isinstance(plan, dict) or not isinstance(plan.get("items"), list):
        raise ValueError("dispatch payloads/plan are required")
    payload_by_id = {row.get("task_id"): row for row in payloads if isinstance(row, dict)}
    plan_by_id = {row.get("task_id"): row for row in plan["items"] if isinstance(row, dict)}
    if len(payload_by_id) != len(payloads) or len(plan_by_id) != len(plan["items"]) or set(payload_by_id) != set(plan_by_id):
        raise ValueError("dispatch plan/payload task identities diverged")

    inserted = 0
    duplicate = 0
    for task_id in sorted(payload_by_id):
        payload = payload_by_id[task_id]
        item = {
            "schema_version": "0.1",
            "task_id": task_id,
            "source": "TODAY_ACTIONS",
            "profile_id": dispatch.get("profile_id"),
            "opportunity_id": payload.get("opportunity_id"),
            "model_input_sha256": payload.get("model_input_sha256"),
            "model_input": payload.get("model_input"),
            "dispatch_item": plan_by_id[task_id],
            "enqueued_at": enqueued_at.astimezone(timezone.utc).isoformat(),
        }
        if queue.enqueue_if_absent(item):
            inserted += 1
        else:
            duplicate += 1
    return {"inserted": inserted, "duplicate": duplicate, "total": len(payload_by_id)}
