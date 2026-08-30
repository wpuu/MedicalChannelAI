from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from .today_actions_http import TrustedPrincipal


@dataclass(frozen=True)
class DueReminder:
    reminder_id: str
    followup_id: str
    opportunity_id: str
    followup_status: str
    remind_at: str
    note: str | None

    def as_private_dict(self) -> dict[str, Any]:
        return {
            "reminder_id": self.reminder_id,
            "followup_id": self.followup_id,
            "opportunity_id": self.opportunity_id,
            "followup_status": self.followup_status,
            "remind_at": self.remind_at,
            "note": self.note,
        }


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _required_text(value: Any, name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    result = value.strip()
    if len(result) > max_length:
        raise ValueError(f"{name} is too long")
    return result


def _principal(principal: TrustedPrincipal) -> tuple[str, str]:
    return (
        _required_text(principal.tenant_id, "tenant_id", max_length=128),
        _required_text(principal.profile_id, "profile_id", max_length=160),
    )


def _parse_aware(value: Any, name: str) -> datetime:
    text = _required_text(value, name, max_length=80)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"stored {name} is invalid") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise RuntimeError(f"stored {name} must be timezone-aware")
    return result


def _reminder_id(tenant_id: str, profile_id: str, followup_id: str) -> str:
    digest = hashlib.sha256(
        f"{tenant_id}|{profile_id}|{followup_id}".encode("utf-8")
    ).hexdigest()
    return "mrem_" + digest


class SQLiteReminderInboxStore:
    """Single-host in-app reminder inbox derived from current follow-up events.

    A reminder exists only while the latest follow-up event for an opportunity has a
    due `next_followup_at`. Newer follow-up events supersede older reminders without
    mutating history. Acknowledgement is tenant/profile-private and idempotent.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_private_reminder_ack ("
                "reminder_id TEXT NOT NULL, "
                "tenant_id TEXT NOT NULL, "
                "profile_id TEXT NOT NULL, "
                "followup_id TEXT NOT NULL, "
                "acknowledged_at TEXT NOT NULL, "
                "PRIMARY KEY(tenant_id, profile_id, reminder_id))"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _current_events(self, *, principal: TrustedPrincipal) -> list[dict[str, Any]]:
        tenant_id, profile_id = _principal(principal)
        with self._connect() as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='medical_private_followup_events'"
            ).fetchone()
            if table is None:
                return []
            rows = conn.execute(
                "SELECT payload FROM ("
                "SELECT payload, opportunity_id, rowid AS event_rowid, "
                "ROW_NUMBER() OVER (PARTITION BY opportunity_id "
                "ORDER BY recorded_at DESC, rowid DESC) AS rn "
                "FROM medical_private_followup_events WHERE tenant_id=? AND profile_id=?"
                ") WHERE rn=1",
                (tenant_id, profile_id),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            event = json.loads(row[0])
            if not isinstance(event, dict):
                raise RuntimeError("stored follow-up event is not an object")
            if event.get("tenant_id") != tenant_id:
                raise RuntimeError("stored follow-up tenant identity mismatch")
            result.append(event)
        return result

    def list_due(
        self,
        *,
        principal: TrustedPrincipal,
        now: datetime,
        limit: int = 20,
    ) -> list[DueReminder]:
        _require_aware(now, "now")
        tenant_id, profile_id = _principal(principal)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValueError("reminder limit must be 1..100")
        with self._connect() as conn:
            acknowledged = {
                str(row[0])
                for row in conn.execute(
                    "SELECT reminder_id FROM medical_private_reminder_ack "
                    "WHERE tenant_id=? AND profile_id=?",
                    (tenant_id, profile_id),
                ).fetchall()
            }

        due: list[tuple[datetime, DueReminder]] = []
        for event in self._current_events(principal=principal):
            remind_raw = event.get("next_followup_at")
            if not isinstance(remind_raw, str) or not remind_raw.strip():
                continue
            remind_at = _parse_aware(remind_raw, "next_followup_at")
            if remind_at > now.astimezone(remind_at.tzinfo):
                continue
            followup_id = _required_text(event.get("followup_id"), "followup_id", max_length=180)
            reminder_id = _reminder_id(tenant_id, profile_id, followup_id)
            if reminder_id in acknowledged:
                continue
            opportunity_id = _required_text(
                event.get("opportunity_id"), "opportunity_id", max_length=160
            )
            status = _required_text(event.get("status"), "status", max_length=40)
            note = event.get("note") if isinstance(event.get("note"), str) else None
            due.append(
                (
                    remind_at,
                    DueReminder(
                        reminder_id=reminder_id,
                        followup_id=followup_id,
                        opportunity_id=opportunity_id,
                        followup_status=status,
                        remind_at=remind_at.isoformat(),
                        note=note,
                    ),
                )
            )
        due.sort(key=lambda item: (item[0], item[1].reminder_id))
        return [copy.deepcopy(item[1]) for item in due[:limit]]

    def acknowledge(
        self,
        *,
        principal: TrustedPrincipal,
        reminder_id: str,
        now: datetime,
    ) -> dict[str, Any] | None:
        _require_aware(now, "now")
        tenant_id, profile_id = _principal(principal)
        reminder_id = _required_text(reminder_id, "reminder_id", max_length=80)
        current = {
            item.reminder_id: item
            for item in self.list_due(principal=principal, now=now, limit=100)
        }.get(reminder_id)
        if current is None:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT followup_id, acknowledged_at FROM medical_private_reminder_ack "
                    "WHERE tenant_id=? AND profile_id=? AND reminder_id=?",
                    (tenant_id, profile_id, reminder_id),
                ).fetchone()
            if existing is None:
                return None
            return {
                "reminder_id": reminder_id,
                "followup_id": str(existing[0]),
                "acknowledged_at": str(existing[1]),
                "inserted": False,
            }

        acknowledged_at = now.astimezone(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO medical_private_reminder_ack("
                "reminder_id, tenant_id, profile_id, followup_id, acknowledged_at"
                ") VALUES (?, ?, ?, ?, ?)",
                (
                    reminder_id,
                    tenant_id,
                    profile_id,
                    current.followup_id,
                    acknowledged_at,
                ),
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    "SELECT followup_id, acknowledged_at FROM medical_private_reminder_ack "
                    "WHERE tenant_id=? AND profile_id=? AND reminder_id=?",
                    (tenant_id, profile_id, reminder_id),
                ).fetchone()
                if row is None:
                    raise RuntimeError("reminder acknowledgement disappeared")
                return {
                    "reminder_id": reminder_id,
                    "followup_id": str(row[0]),
                    "acknowledged_at": str(row[1]),
                    "inserted": False,
                }
        return {
            "reminder_id": reminder_id,
            "followup_id": current.followup_id,
            "acknowledged_at": acknowledged_at,
            "inserted": True,
        }
