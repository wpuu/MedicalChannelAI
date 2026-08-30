from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
import uuid

from .followup_feedback import build_profile_learning_suggestions
from .today_actions_http import TrustedPrincipal


FOLLOWUP_STATUSES = {
    "NEW",
    "REVIEWING",
    "CONTACTED",
    "RELATIONSHIP_VERIFIED",
    "PREPARING",
    "BID_SUBMITTED",
    "WON",
    "LOST",
    "NOT_FIT",
    "MONITOR",
    "ARCHIVED",
}

NOT_FIT_REASONS = {
    "NO_PRODUCT_CAPABILITY",
    "NO_MANUFACTURER_ACCESS",
    "RELATIONSHIP_TOO_WEAK",
    "AMOUNT_TOO_SMALL",
    "PROJECT_TOO_LATE",
    "COMPETITOR_LOCKED_CUSTOMER_JUDGMENT",
    "DEPARTMENT_OUT_OF_SCOPE",
    "REGION_OUT_OF_SCOPE",
    "RENTAL_NOT_SUPPORTED",
    "OTHER",
}

_MUTATION_RE = re.compile(r"^[A-Za-z0-9_.:-]{16,128}$")


class FollowupConflictError(ValueError):
    code = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"


@dataclass(frozen=True)
class FollowupAppendResult:
    event: dict[str, Any]
    inserted: bool


@dataclass(frozen=True)
class FollowupState:
    opportunity_id: str
    current_status: str
    remind_at: str | None
    history: tuple[dict[str, Any], ...]
    profile_learning: dict[str, Any] | None

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "opportunity_id": self.opportunity_id,
            "current_status": self.current_status,
            "remind_at": self.remind_at,
            "history": [copy.deepcopy(item) for item in self.history],
            "profile_learning": copy.deepcopy(self.profile_learning),
        }


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _utc_iso(value: datetime) -> str:
    _require_aware(value, "datetime")
    return value.astimezone(timezone.utc).isoformat()


def _required_text(value: Any, name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{name} is too long")
    return text


def _nullable_text(value: Any, name: str, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"{name} is too long")
    return text


def _validate_principal(principal: TrustedPrincipal) -> tuple[str, str]:
    tenant_id = _required_text(principal.tenant_id, "principal.tenant_id", max_length=128)
    profile_id = _required_text(principal.profile_id, "principal.profile_id", max_length=160)
    return tenant_id, profile_id


def _validate_remind_at(value: Any) -> str | None:
    text = _nullable_text(value, "remind_at", max_length=80)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("remind_at must be ISO-8601 datetime") from exc
    _require_aware(parsed, "remind_at")
    return parsed.isoformat()


def normalize_followup_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("follow-up request must be an object")
    allowed = {"status", "note", "reason", "remind_at", "mutation_id"}
    extra = sorted(set(payload) - allowed)
    if extra:
        raise ValueError(f"follow-up request contains unsupported fields: {','.join(extra)}")

    status = _required_text(payload.get("status"), "status", max_length=40)
    if status not in FOLLOWUP_STATUSES:
        raise ValueError("follow-up status is not allowed")
    note = _nullable_text(payload.get("note"), "note", max_length=4000)
    reason = _nullable_text(payload.get("reason"), "reason", max_length=80)
    remind_at = _validate_remind_at(payload.get("remind_at"))
    mutation_id = _required_text(payload.get("mutation_id"), "mutation_id", max_length=128)
    if not _MUTATION_RE.fullmatch(mutation_id):
        raise ValueError("mutation_id format is invalid")

    if status == "NOT_FIT":
        if reason not in NOT_FIT_REASONS:
            raise ValueError("NOT_FIT requires an allowed reason")
    elif reason is not None:
        raise ValueError("reason is only allowed for NOT_FIT")

    return {
        "status": status,
        "note": note,
        "reason": reason,
        "remind_at": remind_at,
        "mutation_id": mutation_id,
    }


def _request_hash(normalized: dict[str, Any]) -> str:
    immutable = {
        key: normalized[key]
        for key in ("status", "note", "reason", "remind_at")
    }
    raw = json.dumps(
        immutable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _build_event(
    *,
    tenant_id: str,
    opportunity_id: str,
    normalized: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "followup_id": f"mfollow_{uuid.uuid4()}",
        "tenant_id": tenant_id,
        "opportunity_id": opportunity_id,
        "status": normalized["status"],
        "owner": None,
        "next_followup_at": normalized["remind_at"],
        "note": normalized["note"],
        "not_fit_reason": normalized["reason"],
        "not_fit_detail": None,
        "customer_confirmed": True,
        "recorded_at": _utc_iso(now),
    }


def _public_record(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["followup_id"],
        "status": event["status"],
        "note": event.get("note"),
        "reason": event.get("not_fit_reason"),
        "remind_at": event.get("next_followup_at"),
        "at": event["recorded_at"],
        "actor": "当前账号",
    }


class SQLiteFollowupStore:
    """Append-only tenant/profile-private follow-up event store for one-host Pilot."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS medical_private_followup_events ("
                "followup_id TEXT PRIMARY KEY, "
                "tenant_id TEXT NOT NULL, "
                "profile_id TEXT NOT NULL, "
                "opportunity_id TEXT NOT NULL, "
                "recorded_at TEXT NOT NULL, "
                "mutation_id TEXT NOT NULL, "
                "request_sha256 TEXT NOT NULL, "
                "payload TEXT NOT NULL, "
                "UNIQUE(tenant_id, profile_id, mutation_id))"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_medical_followup_history "
                "ON medical_private_followup_events("
                "tenant_id, profile_id, opportunity_id, recorded_at DESC, followup_id DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def append(
        self,
        *,
        principal: TrustedPrincipal,
        opportunity_id: str,
        request: dict[str, Any],
        now: datetime,
    ) -> FollowupAppendResult:
        _require_aware(now, "now")
        tenant_id, profile_id = _validate_principal(principal)
        opportunity_id = _required_text(opportunity_id, "opportunity_id", max_length=160)
        normalized = normalize_followup_request(request)
        mutation_id = normalized["mutation_id"]
        request_hash = _request_hash(normalized)
        event = _build_event(
            tenant_id=tenant_id,
            opportunity_id=opportunity_id,
            normalized=normalized,
            now=now,
        )
        payload_json = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT request_sha256, payload FROM medical_private_followup_events "
                "WHERE tenant_id=? AND profile_id=? AND mutation_id=?",
                (tenant_id, profile_id, mutation_id),
            ).fetchone()
            if existing is not None:
                existing_hash, existing_payload = existing
                if existing_hash != request_hash:
                    conn.execute("ROLLBACK")
                    raise FollowupConflictError(
                        "mutation_id was already used with a different follow-up payload"
                    )
                conn.execute("COMMIT")
                return FollowupAppendResult(event=json.loads(existing_payload), inserted=False)

            conn.execute(
                "INSERT INTO medical_private_followup_events("
                "followup_id, tenant_id, profile_id, opportunity_id, recorded_at, "
                "mutation_id, request_sha256, payload"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event["followup_id"],
                    tenant_id,
                    profile_id,
                    opportunity_id,
                    event["recorded_at"],
                    mutation_id,
                    request_hash,
                    payload_json,
                ),
            )
            conn.execute("COMMIT")
        return FollowupAppendResult(event=copy.deepcopy(event), inserted=True)

    def list_events(
        self,
        *,
        principal: TrustedPrincipal,
        opportunity_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        tenant_id, profile_id = _validate_principal(principal)
        opportunity_id = _required_text(opportunity_id, "opportunity_id", max_length=160)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValueError("follow-up history limit must be 1..100")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM medical_private_followup_events "
                "WHERE tenant_id=? AND profile_id=? AND opportunity_id=? "
                "ORDER BY recorded_at DESC, followup_id DESC LIMIT ?",
                (tenant_id, profile_id, opportunity_id, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            event = json.loads(row[0])
            if event.get("tenant_id") != tenant_id or event.get("opportunity_id") != opportunity_id:
                raise RuntimeError("stored follow-up identity diverges from repository key")
            result.append(event)
        return copy.deepcopy(result)

    def state(
        self,
        *,
        principal: TrustedPrincipal,
        opportunity_id: str,
        limit: int = 50,
    ) -> FollowupState:
        events = self.list_events(
            principal=principal,
            opportunity_id=opportunity_id,
            limit=limit,
        )
        if not events:
            return FollowupState(
                opportunity_id=opportunity_id,
                current_status="NEW",
                remind_at=None,
                history=(),
                profile_learning=None,
            )
        current = events[0]
        learning = build_profile_learning_suggestions(current)
        return FollowupState(
            opportunity_id=opportunity_id,
            current_status=str(current["status"]),
            remind_at=current.get("next_followup_at"),
            history=tuple(_public_record(event) for event in events),
            profile_learning=learning,
        )
