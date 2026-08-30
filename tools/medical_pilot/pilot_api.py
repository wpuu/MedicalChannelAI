from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping
from urllib.parse import urlsplit

from .today_runtime import SQLiteTodayRuntime


@dataclass(frozen=True)
class PilotApiResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def json_body(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8"))


def _not_found() -> PilotApiResponse:
    body = b'{"error":"NOT_FOUND"}'
    return PilotApiResponse(
        404,
        {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
        body,
    )


def _inner_target(target: str) -> str | None:
    parsed = urlsplit(target)
    if parsed.path == "/api":
        path = "/"
    elif parsed.path.startswith("/api/"):
        path = parsed.path[len("/api") :]
    else:
        return None
    return path + (f"?{parsed.query}" if parsed.query else "")


def dispatch_pilot_api(
    runtime: SQLiteTodayRuntime,
    *,
    method: str,
    target: str,
    headers: Mapping[str, str],
    body: bytes,
    now: datetime,
) -> PilotApiResponse:
    """Translate same-origin /api/* requests into trusted core transports."""

    inner = _inner_target(target)
    if inner is None:
        return _not_found()
    path = urlsplit(inner).path
    if path.startswith("/auth/"):
        response = runtime.auth_transport.handle(
            method=method,
            target=inner,
            headers=headers,
            body=body,
            now=now,
        )
    elif path.startswith("/followup/"):
        response = runtime.followup_transport.handle(
            method=method,
            target=inner,
            headers=headers,
            body=body,
            now=now,
        )
    elif path == "/reminders" or path.startswith("/reminders/"):
        response = runtime.reminder_transport.handle(
            method=method,
            target=inner,
            headers=headers,
            body=body,
            now=now,
        )
    elif path.startswith("/outreach/"):
        response = runtime.outreach_transport.handle(
            method=method,
            target=inner,
            headers=headers,
            body=body,
            now=now,
        )
    else:
        response = runtime.transport.handle(
            method=method,
            target=inner,
            headers=headers,
            now=now,
        )
    return PilotApiResponse(
        status_code=response.status_code,
        headers=dict(response.headers),
        body=response.body,
    )
