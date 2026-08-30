from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping, Protocol
from urllib.parse import unquote, urlsplit

from .agnes_dispatch_queue import AgnesDispatchQueue
from .agnes_task_result import AgnesTaskResultStore
from .today_actions_api import (
    TodayActionsApiResponse,
    TodayActionsRepository,
    build_today_actions_api_response,
    get_today_opportunity_api_response,
)


@dataclass(frozen=True)
class TrustedPrincipal:
    """Tenant/profile identity already verified by a server-side auth boundary."""

    tenant_id: str
    profile_id: str


class TrustedPrincipalResolver(Protocol):
    """Resolve auth/session data to a trusted principal.

    Implementations must verify a session, signature, or upstream trusted identity.
    They must not simply copy tenant/profile IDs from arbitrary browser headers or
    query parameters.
    """

    def resolve(self, headers: Mapping[str, str]) -> TrustedPrincipal | None: ...


class TodayActionsApplication(Protocol):
    def get_today(self, principal: TrustedPrincipal, now: datetime) -> TodayActionsApiResponse: ...

    def get_opportunity(
        self,
        principal: TrustedPrincipal,
        opportunity_id: str,
        now: datetime,
    ) -> TodayActionsApiResponse: ...


class RepositoryTodayActionsApplication:
    """Bind the HTTP transport to the existing tenant-safe application boundary."""

    def __init__(
        self,
        *,
        repository: TodayActionsRepository,
        result_store: AgnesTaskResultStore,
        dispatch_queue: AgnesDispatchQueue | None = None,
    ) -> None:
        self._repository = repository
        self._result_store = result_store
        self._dispatch_queue = dispatch_queue

    def get_today(self, principal: TrustedPrincipal, now: datetime) -> TodayActionsApiResponse:
        return build_today_actions_api_response(
            tenant_id=principal.tenant_id,
            profile_id=principal.profile_id,
            repository=self._repository,
            result_store=self._result_store,
            dispatch_queue=self._dispatch_queue,
            now=now,
        )

    def get_opportunity(
        self,
        principal: TrustedPrincipal,
        opportunity_id: str,
        now: datetime,
    ) -> TodayActionsApiResponse:
        return get_today_opportunity_api_response(
            tenant_id=principal.tenant_id,
            profile_id=principal.profile_id,
            opportunity_id=opportunity_id,
            repository=self._repository,
            result_store=self._result_store,
            dispatch_queue=self._dispatch_queue,
            now=now,
        )


@dataclass(frozen=True)
class TodayActionsHttpResponse:
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
) -> TodayActionsHttpResponse:
    headers = dict(_BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return TodayActionsHttpResponse(status_code, headers, encoded)


def _opportunity_id(path: str) -> str | None:
    prefix = "/opportunity/"
    if not path.startswith(prefix):
        return None
    raw = path[len(prefix) :]
    if not raw or "/" in raw:
        return None
    value = unquote(raw).strip()
    if not value or "/" in value or len(value) > 128:
        return None
    return value


class TodayActionsHttpTransport:
    """Framework-neutral, same-origin HTTP boundary for the H5 Pilot.

    This transport intentionally has no built-in tenant/profile query parameters and
    no permissive CORS behavior. Identity must arrive from a trusted server-side
    resolver. A Vercel/Flask/FastAPI adapter can translate its request/response
    objects without changing the business application boundary.
    """

    def __init__(
        self,
        *,
        principal_resolver: TrustedPrincipalResolver,
        application: TodayActionsApplication,
    ) -> None:
        self._principal_resolver = principal_resolver
        self._application = application

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        now: datetime,
    ) -> TodayActionsHttpResponse:
        if method.upper() != "GET":
            return _json_response(405, {"error": "METHOD_NOT_ALLOWED"}, extra_headers={"Allow": "GET"})
        if now.tzinfo is None or now.utcoffset() is None:
            return _json_response(500, {"error": "SERVER_TIME_INVALID"})

        principal = self._principal_resolver.resolve(headers)
        if principal is None:
            return _json_response(401, {"error": "UNAUTHORIZED"})
        if not principal.tenant_id.strip() or not principal.profile_id.strip():
            return _json_response(401, {"error": "UNAUTHORIZED"})

        path = urlsplit(target).path
        try:
            if path == "/today":
                response = self._application.get_today(principal, now)
                return _json_response(response.status_code, response.body)

            opportunity_id = _opportunity_id(path)
            if opportunity_id is not None:
                response = self._application.get_opportunity(principal, opportunity_id, now)
                return _json_response(response.status_code, response.body)
        except ValueError:
            return _json_response(400, {"error": "INVALID_REQUEST"})
        except RuntimeError:
            return _json_response(500, {"error": "INTERNAL_RESPONSE_REJECTED"})
        except Exception:
            return _json_response(500, {"error": "INTERNAL_ERROR"})

        return _json_response(404, {"error": "NOT_FOUND"})
