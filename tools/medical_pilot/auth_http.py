from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

from .session_auth import (
    IssuedSession,
    SESSION_COOKIE_NAME,
    SessionStore,
    build_clear_cookie,
    revoke_session,
)


class InviteSessionIssuer(Protocol):
    def redeem_invite_to_session(
        self,
        *,
        code: str,
        now: datetime,
        session_ttl_seconds: int | None = None,
    ) -> IssuedSession | None: ...


@dataclass(frozen=True)
class AuthHttpResponse:
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


def _json_response(
    status_code: int,
    body: dict[str, Any],
    *,
    extra_headers: Mapping[str, str] | None = None,
) -> AuthHttpResponse:
    headers = dict(_BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return AuthHttpResponse(status_code, headers, encoded)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    matches = [value for key, value in headers.items() if key.lower() == wanted]
    if len(matches) != 1:
        return None
    return matches[0]


def _session_token(headers: Mapping[str, str]) -> str | None:
    raw_cookie = _header(headers, "Cookie")
    if not raw_cookie:
        return None
    values: list[str] = []
    for part in raw_cookie.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == SESSION_COOKIE_NAME:
            values.append(value.strip())
    if len(values) != 1:
        return None
    token = values[0]
    if len(token) < 32 or len(token) > 128:
        return None
    if any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in token):
        return None
    return token


def _parse_redeem_code(headers: Mapping[str, str], body: bytes) -> str | None:
    content_type = _header(headers, "Content-Type")
    if content_type is None or content_type.split(";", 1)[0].strip().lower() != "application/json":
        return None
    if not isinstance(body, bytes) or len(body) == 0 or len(body) > 2048:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"code"}:
        return None
    code = payload.get("code")
    if not isinstance(code, str) or len(code) < 32 or len(code) > 128:
        return None
    return code


class PilotAuthHttpTransport:
    """Framework-neutral same-origin auth boundary for the Tianjin Pilot.

    It accepts no tenant/profile identity from the browser. A one-time invite already
    carries the server-side binding, and successful redemption produces an opaque
    HttpOnly session. Deployments should additionally rate-limit /auth/redeem at the
    reverse-proxy/platform layer.
    """

    def __init__(
        self,
        *,
        invite_session_issuer: InviteSessionIssuer,
        session_store: SessionStore,
    ) -> None:
        self._issuer = invite_session_issuer
        self._session_store = session_store

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes,
        now: datetime,
    ) -> AuthHttpResponse:
        if now.tzinfo is None or now.utcoffset() is None:
            return _json_response(500, {"error": "SERVER_TIME_INVALID"})
        path = urlsplit(target).path

        if path == "/auth/redeem":
            if method.upper() != "POST":
                return _json_response(
                    405,
                    {"error": "METHOD_NOT_ALLOWED"},
                    extra_headers={"Allow": "POST"},
                )
            code = _parse_redeem_code(headers, body)
            if code is None:
                return _json_response(400, {"error": "INVALID_REQUEST"})
            try:
                session = self._issuer.redeem_invite_to_session(code=code, now=now)
            except ValueError:
                return _json_response(400, {"error": "INVALID_REQUEST"})
            except Exception:
                return _json_response(500, {"error": "INTERNAL_ERROR"})
            if session is None:
                return _json_response(401, {"error": "INVITE_INVALID_OR_EXPIRED"})
            return _json_response(
                200,
                {"authenticated": True},
                extra_headers={"Set-Cookie": session.set_cookie},
            )

        if path == "/auth/logout":
            if method.upper() != "POST":
                return _json_response(
                    405,
                    {"error": "METHOD_NOT_ALLOWED"},
                    extra_headers={"Allow": "POST"},
                )
            token = _session_token(headers)
            if token is not None:
                try:
                    revoke_session(self._session_store, token, now=now)
                except ValueError:
                    pass
            return _json_response(
                200,
                {"authenticated": False},
                extra_headers={"Set-Cookie": build_clear_cookie()},
            )

        return _json_response(404, {"error": "NOT_FOUND"})
