from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

from .today_actions_http import TrustedPrincipal


@dataclass(frozen=True)
class CurrentFollowedOpportunity:
    opportunity_id: str
    followup_id: str
    status: str
    remind_at: str | None
    note: str | None
    updated_at: str


class SQLiteFollowedOpportunityStore:
    """Read current tenant/profile follow-up state without changing event history."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _required(value: Any, name: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"stored {name} is missing")
        text = value.strip()
        if len(text) > max_length:
            raise RuntimeError(f"stored {name} is too long")
        return text

    def list_current(
        self,
        *,
        principal: TrustedPrincipal,
        limit: int = 100,
        include_archived: bool = false,
    ) -> list[CurrentFollowedOpportunity]:
        if not isinstance(principal.tenant_id, str) or not principal.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not isinstance(principal.profile_id, str) or not principal.profile_id.strip():
            raise ValueError("profile_id is required")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValueError("followed opportunity limit must be 1..100")

        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='medical_private_followup_events'"
            ).fetchone()
            if exists is None:
                return []
            rows = conn.execute(
                "SELECT payload FROM ("
                "SELECT payload, opportunity_id, recorded_at, rowid AS event_rowid, "
                "ROW_NUMBER() OVER (PARTITION BY opportunity_id "
                "ORDER BY recorded_at DESC, rowid DESC) AS rn "
                "FROM medical_private_followup_events WHERE tenant_id=? AND profile_id=?"
                ") WHERE rn=1 ORDER BY recorded_at DESC, event_rowid DESC LIMIT ?",
                (principal.tenant_id.strip(), principal.profile_id.strip(), limit),
            ).fetchall()

        result: list[CurrentFollowedOpportunity] = []
        for row in rows:
            event = json.loads(row[0])
            if not isinstance(event, dict):
                raise RuntimeError("stored follow-up event must be an object")
            if event.get("tenant_id") != principal.tenant_id.strip():
                raise RuntimeError("stored follow-up tenant identity mismatch")
            status = self._required(event.get("status"), "follow-up status", 40)
            if not include_archived and status == "ARCHIVED":
                continue
            remind_at = event.get("next_followup_at")
            note = event.get("note")
            result.append(
                CurrentFollowedOpportunity(
                    opportunity_id=self._required(event.get("opportunity_id"), "opportunity_id", 160),
                    followup_id=self._required(event.get("followup_id"), "followup_id", 180),
                    status=status,
                    remind_at=remind_at.strip() if isinstance(remind_at, str) and remind_at.strip() else None,
                    note=note.strip() if isinstance(note, str) and note.strip() else None,
                    updated_at=self._required(event.get("recorded_at"), "recorded_at", 80),
                )
            )
        return copy.deepcopy(result)
