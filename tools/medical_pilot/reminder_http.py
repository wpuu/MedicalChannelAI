from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

from .reminder_store import SQLiteReminderInboxStore
from .today_actions_http import TrustedPrincipalResolver


_REMINDER_RE = re.compile(r"^mrem_[0-9a-f]{64}$")


class ReminderRepository(Protocol):
    def load_public_opportunity(self, opportunity_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class ReminderHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def json_body(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8"))


_BASE_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store, private",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def _json_response(status_code: int, body: dict[str, Any]) -> ReminderHttpResponse:
    return ReminderHttpResponse(
        status_code=status_code,
        headers=dict(_BASE_HEADERS),
        body=json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8"),
    )


def _require_empty_body(body: bytes) -> None:
    if not body:
        return
    if len(body) > 256:
        raise ValueError("reminder request body too large")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("reminder request body must be empty or {}") from exc
    if value != {}:
        raise ValueError("reminder request body must be empty or {}")


def _public_facts(opportunity: dict[str, Any]) -> dict[str, Any]:
    def text(name: str) -> str | None:
        value = opportunity.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else None

    return {
        "buyer_name": text("buyer_name"),
        "hospital_name": text("hospital_name"),
        "project_name": text("project_name"),
    }


class ReminderHttpTransport:
    """Authenticated in-app reminder inbox; no external push is implied."""

    def __init__(
        self,
        *,
        principal_resolver: TrustedPrincipalResolver,
        repository: ReminderRepository,
        store: SQLiteReminderInboxStore,
    ) -> None:
        self._principal_resolver = principal_resolver
        self._repository = repository
        self._store = store

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes,
        now: datetime,
    ) -> ReminderHttpResponse:
        if now.tzinfo is None or now.utcoffset() is None:
            return _json_response(500, {"error": "SERVER_TIME_INVALID"})
        parsed = urlsplit(target)
        if parsed.query or parsed.fragment:
            return _json_response(400, {"error": "INVALID_REQUEST"})

        principal = self._principal_resolver.resolve(headers)
        if principal is None or not principal.tenant_id.strip() or not principal.profile_id.strip():
            return _json_response(401, {"error": "UNAUTHORIZED"})

        if parsed.path == "/reminders":
            if method.upper() != "GET":
                return _json_response(405, {"error": "METHOD_NOT_ALLOWED"})
            if body:
                return _json_response(400, {"error": "INVALID_REQUEST"})
            try:
                due = self._store.list_due(principal=principal, now=now, limit=20)
                items: list[dict[str, Any]] = []
                for reminder in due:
                    opportunity = self._repository.load_public_opportunity(reminder.opportunity_id)
                    if opportunity is None:
                        raise RuntimeError("reminder references missing public opportunity")
                    items.append(
                        {
                            "reminder_id": reminder.reminder_id,
                            "opportunity_id": reminder.opportunity_id,
                            "followup_status": reminder.followup_status,
                            "remind_at": reminder.remind_at,
                            "note": reminder.note,
                            "facts": _public_facts(opportunity),
                        }
                    )
                return _json_response(
                    200,
                    {
                        "schema_version": "0.1",
                        "mode": "FOLLOWUP_REMINDER_INBOX",
                        "count": len(items),
                        "reminders": items,
                    },
                )
            except (ValueError, RuntimeError):
                return _json_response(500, {"error": "REMINDER_INTERNAL_ERROR"})

        prefix = "/reminders/"
        suffix = "/ack"
        if parsed.path.startswith(prefix) and parsed.path.endswith(suffix):
            reminder_id = parsed.path[len(prefix) : -len(suffix)]
            if not _REMINDER_RE.fullmatch(reminder_id):
                return _json_response(404, {"error": "REMINDER_NOT_FOUND"})
            if method.upper() != "POST":
                return _json_response(405, {"error": "METHOD_NOT_ALLOWED"})
            try:
                _require_empty_body(body)
                result = self._store.acknowledge(
                    principal=principal,
                    reminder_id=reminder_id,
                    now=now,
                )
            except ValueError:
                return _json_response(400, {"error": "INVALID_REQUEST"})
            except RuntimeError:
                return _json_response(500, {"error": "REMINDER_INTERNAL_ERROR"})
            if result is None:
                return _json_response(404, {"error": "REMINDER_NOT_FOUND"})
            return _json_response(
                200,
                {
                    "schema_version": "0.1",
                    "reminder_id": reminder_id,
                    "acknowledged": True,
                    "acknowledged_at": result["acknowledged_at"],
                    "already_acknowledged": not bool(result["inserted"]),
                },
            )

        return _json_response(404, {"error": "NOT_FOUND"})
