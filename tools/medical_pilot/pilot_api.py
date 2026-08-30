from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping
from urllib.parse import urlsplit

from .health_http import handle_health_request
from .today_runtime import SQLiteTodayRuntime


UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class PilotApiResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def json_body(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8"))


@dataclass(frozen=True)
class CanonicalOriginPolicy:
    """Single-origin boundary for the authenticated real Pilot.

    The static synthetic Demo does not run this API server. Real Pilot requests
    must arrive through one HTTPS origin; browser writes additionally require an
    Origin header matching that origin. Loopback is permitted only for healthz.
    """

    origin: str
    authority: str

    @classmethod
    def parse(cls, value: str) -> "CanonicalOriginPolicy":
        raw = value.strip()
        if not raw:
            raise ValueError("canonical origin is required")
        parsed = urlsplit(raw)
        if parsed.scheme.lower() != "https":
            raise ValueError("canonical origin must use https")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("canonical origin must not contain userinfo")
        if not parsed.hostname:
            raise ValueError("canonical origin must contain a hostname")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("canonical origin must not contain path, query or fragment")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("canonical origin contains an invalid port") from exc
        hostname = parsed.hostname.lower()
        authority_host = f"[{hostname}]" if ":" in hostname else hostname
        authority = authority_host if port in (None, 443) else f"{authority_host}:{port}"
        return cls(origin=f"https://{authority}", authority=authority)


def _json_error(status_code: int, code: str) -> PilotApiResponse:
    body = json.dumps({"error": code}, separators=(",", ":")).encode("utf-8")
    return PilotApiResponse(
        status_code,
        {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
        body,
    )


def _not_found() -> PilotApiResponse:
    return _json_error(404, "NOT_FOUND")


def _forbidden() -> PilotApiResponse:
    return _json_error(403, "FORBIDDEN")


def _inner_target(target: str) -> str | None:
    parsed = urlsplit(target)
    if parsed.path == "/api":
        path = "/"
    elif parsed.path.startswith("/api/"):
        path = parsed.path[len("/api") :]
    else:
        return None
    return path + (f"?{parsed.query}" if parsed.query else "")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value.strip()
    return None


def _normalize_authority(host_header: str, *, scheme: str = "https") -> str | None:
    raw = host_header.strip()
    if not raw or any(ch in raw for ch in "/?#") or "@" in raw:
        return None
    try:
        parsed = urlsplit(f"{scheme}://{raw}")
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return None
        port = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname.lower()
    authority_host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    return authority_host if port in (None, default_port) else f"{authority_host}:{port}"


def _normalize_origin(origin_header: str) -> str | None:
    raw = origin_header.strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname.lower()
    authority_host = f"[{hostname}]" if ":" in hostname else hostname
    authority = authority_host if port in (None, 443) else f"{authority_host}:{port}"
    return f"https://{authority}"


def _is_loopback_health_host(host_header: str | None) -> bool:
    if host_header is None:
        return False
    raw = host_header.strip()
    if not raw or any(ch in raw for ch in "/?#") or "@" in raw:
        return False
    try:
        parsed = urlsplit(f"http://{raw}")
        return parsed.hostname is not None and parsed.hostname.lower() in LOOPBACK_HOSTS
    except ValueError:
        return False


def enforce_origin_policy(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    policy: CanonicalOriginPolicy,
) -> PilotApiResponse | None:
    """Return a generic 403 when Host/Origin violates the canonical boundary."""

    normalized_method = method.upper()
    host = _header(headers, "Host")

    if path == "/healthz" and normalized_method in {"GET", "HEAD"} and _is_loopback_health_host(host):
        return None

    if host is None or _normalize_authority(host) != policy.authority:
        return _forbidden()

    if normalized_method in UNSAFE_METHODS:
        origin = _header(headers, "Origin")
        if origin is None or _normalize_origin(origin) != policy.origin:
            return _forbidden()

    return None


def dispatch_pilot_api(
    runtime: SQLiteTodayRuntime,
    *,
    method: str,
    target: str,
    headers: Mapping[str, str],
    body: bytes,
    now: datetime,
    origin_policy: CanonicalOriginPolicy | None = None,
) -> PilotApiResponse:
    """Translate same-origin /api/* requests into trusted core transports."""

    inner = _inner_target(target)
    if inner is None:
        return _not_found()
    path = urlsplit(inner).path

    if origin_policy is not None:
        rejected = enforce_origin_policy(
            method=method,
            path=path,
            headers=headers,
            policy=origin_policy,
        )
        if rejected is not None:
            return rejected

    if path == "/healthz":
        health = handle_health_request(method=method, target=inner, body=body)
        return PilotApiResponse(health.status_code, dict(health.headers), health.body)
    if path.startswith("/auth/"):
        response = runtime.auth_transport.handle(
            method=method,
            target=inner,
            headers=headers,
            body=body,
            now=now,
        )
    elif path == "/profile":
        response = runtime.profile_transport.handle(
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
    elif path == "/followed":
        response = runtime.followed_transport.handle(
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
