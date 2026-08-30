from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


TERMINAL_STATUSES = {"READY", "MODEL_OUTPUT_REJECTED"}


class AgnesTaskResultStore(Protocol):
    def get(self, task_id: str) -> dict[str, Any] | None: ...
    def put_if_absent(self, task_id: str, result: dict[str, Any]) -> bool: ...


class MemoryAgnesTaskResultStore:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self._rows.get(task_id)
        if row is None:
            return None
        validate_terminal_result(task_id, row)
        return copy.deepcopy(row)

    def put_if_absent(self, task_id: str, result: dict[str, Any]) -> bool:
        validate_terminal_result(task_id, result)
        if task_id in self._rows:
            return False
        self._rows[task_id] = copy.deepcopy(result)
        return True


class SQLiteAgnesTaskResultStore:
    """Single-host persistent terminal-result store with unique task identity."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS agnes_task_results ("
                "task_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM agnes_task_results WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            return None
        result = json.loads(row[0])
        validate_terminal_result(task_id, result)
        return result

    def put_if_absent(self, task_id: str, result: dict[str, Any]) -> bool:
        validate_terminal_result(task_id, result)
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO agnes_task_results(task_id, payload) VALUES (?, ?)",
                (task_id, payload),
            )
        return cursor.rowcount == 1


def validate_terminal_result(task_id: str, result: dict[str, Any]) -> None:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id is required")
    if not isinstance(result, dict) or result.get("schema_version") != "0.1":
        raise ValueError("terminal result schema_version must be 0.1")
    if result.get("task_id") != task_id:
        raise ValueError("terminal result task_id mismatch")
    if result.get("status") not in TERMINAL_STATUSES:
        raise ValueError("only READY or MODEL_OUTPUT_REJECTED may be persisted as terminal")
    if not isinstance(result.get("opportunity_id"), str) or not result["opportunity_id"]:
        raise ValueError("terminal result opportunity_id is required")
    model_input_sha256 = result.get("model_input_sha256")
    if not isinstance(model_input_sha256, str) or len(model_input_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in model_input_sha256):
        raise ValueError("terminal result model_input_sha256 must be lowercase sha256")
    if not task_id.endswith("|" + model_input_sha256[:24]):
        raise ValueError("terminal result task_id is not bound to model_input_sha256")
    if f"|{result['opportunity_id']}|" not in task_id:
        raise ValueError("terminal result task_id is not bound to opportunity_id")
    completed_at = result.get("completed_at")
    if not isinstance(completed_at, str):
        raise ValueError("terminal result completed_at is required")
    parsed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("terminal result completed_at must include timezone")
    if result["status"] == "READY":
        if not isinstance(result.get("validated_output"), dict) or not isinstance(result.get("rendered_decision"), dict):
            raise ValueError("READY terminal result requires validated output and rendered decision")
        if result.get("error_code") is not None:
            raise ValueError("READY terminal result cannot carry error_code")
    else:
        if result.get("validated_output") is not None or result.get("rendered_decision") is not None:
            raise ValueError("rejected terminal result cannot carry a rendered decision")
        if not isinstance(result.get("error_code"), str) or not result["error_code"]:
            raise ValueError("rejected terminal result requires error_code")


def build_terminal_result(
    *,
    task_id: str,
    opportunity_id: str,
    model_input_sha256: str,
    status: str,
    completed_at: datetime,
    validated_output: dict[str, Any] | None,
    rendered_decision: dict[str, Any] | None,
    error_code: str | None,
) -> dict[str, Any]:
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("completed_at must be timezone-aware")
    result = {
        "schema_version": "0.1",
        "task_id": task_id,
        "opportunity_id": opportunity_id,
        "model_input_sha256": model_input_sha256,
        "status": status,
        "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
        "validated_output": validated_output,
        "rendered_decision": rendered_decision,
        "error_code": error_code,
    }
    validate_terminal_result(task_id, result)
    return result
