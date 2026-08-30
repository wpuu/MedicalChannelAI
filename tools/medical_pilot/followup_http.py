from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping, Protocol
from urllib.parse import unquote, urlsplit

from .followup_store import FollowupConflictError, SQLiteFollowupStore
from .today_actions_http import TrustedPrincipal, TrustedPrincipalResolver
from .today_repo import SQLiteTodayActionsRepository


@dataclass(frozen=True)
class FollowupHttpResponse:
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


def _json_response(status_code: int, body: dict[str, Any], *, allow: str | None = None) -> FollowupHttpResponse:
    headers = dict(_BASE_HEADERS)
    if allow is not None:
        headers["Allow"] = allow
    return FollowupHttpResponse(
        status_code=status_code,
        headers=headers,
        body=json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8"),
    )


def _opportunity_id(target: str) -> str | None:
    path = urlsplit(target).path
    prefix = "/followup/"
    if not path.startswith(prefix):
        return None
    raw = path[len(prefix):]
    if not raw or "/" in raw:
        return None
    value = unquote(raw).strip()
    if not value or "/" in value or len(value) > 160:
        return None
    return value


def _json_request(body: bytes) -> dict[str, Any]:
    if not body or len(body) > 4096:
        raise ValueError("follow-up request body is required and must be <=4096 bytes")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("follow-up request body must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("follow-up request body must be an object")
    return payload


class FollowupRepository(Protocol):
    def load_profile(self, tenant_id: str, profile_id: str) -> dict[str, Any] | None: ...
    def load_public_opportunity(self, opportunity_id: str) -> dict[str, Any] | None: ...


class FollowupHttpTransport:
    """Authenticated HTTP boundary for customer-private follow-up state.

    Tenant/profile identity always comes from TrustedPrincipalResolver. Browser JSON
    cannot select another tenant/profile, and follow-up state never mutates public
    procurement opportunities or evidence.
    """

    def __init__(
        self,
        *,
        principal_resolver: TrustedPrincipalResolver,
        repository: FollowupRepository,
        store: SQLiteFollowupStore,
    ) -> None:
        self._principal_resolver = principal_resolver
        self._repository = repository
        self._store = store

    def _principal(self, headers: Mapping[str, str]) -> TrustedPrincipal | None:
        principal = self._principal_resolver.resolve(headers)
        if principal is None:
            return None
        if not principal.tenant_id.strip() or not principal.profile_id.strip():
            return None
        return principal

    def _resource_exists(self, principal: TrustedPrincipal, opportunity_id: str) -> str | None:
        profile = self._repository.load_profile(principal.tenant_id, principal.profile_id)
        if profile is None:
            return "PROFILE_NOT_FOUND"
        if profile.get("tenant_id") != principal.tenant_id or profile.get("profile_id") != principal.profile_id:
            return "PROFILE_NOT_FOUND"
        opportunity = self._repository.load_public_opportunity(opportunity_id)
        if opportunity is None:
            return "OPPORTUNITY_NOT_FOUND"
        return None

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes,
        now: datetime,
    ) -> FollowupHttpResponse:
        if now.tzinfo is None or now.utcoffset() is None:
            return _json_response(500, {"error": "SERVER_TIME_INVALID"})
        opportunity_id = _opportunity_id(target)
        if opportunity_id is None:
            return _json_response(404, {"error": "NOT_FOUND"})
        if method.upper() not in {"GET", "POST"}:
            return _json_response(405, {"error": "METHOD_NOT_ALLOWED"}, allow="GET, POST")

        principal = self._principal(headers)
        if principal is None:
            return _json_response(401, {"error": "UNAUTHORIZED"})

        try:
            missing = self._resource_exists(principal, opportunity_id)
            if missing is not None:
                return _json_response(404, {"error": missing})

            if method.upper() == "GET":
                state = self._store.state(
                    principal=principal,
                    opportunity_id=opportunity_id,
                )
                return _json_response(200, state.as_public_dict())

            request = _json_request(body)
            append_result = self._store.append(
                principal=principal,
                opportunity_id=opportunity_id,
                request=request,
                now=now,
            )
            state = self._store.state(
                principal=principal,
                opportunity_id=opportunity_id,
            )
            response = state.as_public_dict()
            response["mutation_inserted"] = append_result.inserted
            return _json_response(200, response)
        except FollowupConflictError as exc:
            return _json_response(409, {"error": exc.code})
        except ValueError:
            return _json_response(400, {"error": "INVALID_REQUEST"})
        except RuntimeError:
            return _json_response(500, {"error": "INTERNAL_RESPONSE_REJECTED"})
        except Exception:
            return _json_response(500, {"error": "INTERNAL_ERROR"})
