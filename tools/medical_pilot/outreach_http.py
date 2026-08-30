from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from .outreach_service import GroundedOutreachService, OutreachServiceError
from .today_actions_http import TrustedPrincipalResolver


@dataclass(frozen=True)
class OutreachHttpResponse:
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
) -> OutreachHttpResponse:
    headers = dict(_BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return OutreachHttpResponse(
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
    prefix = "/outreach/"
    if not path.startswith(prefix):
        return None
    raw = path[len(prefix):]
    if not raw or "/" in raw:
        return None
    value = unquote(raw).strip()
    if not value or "/" in value or len(value) > 160:
        return None
    return value


def _validate_empty_request(body: bytes) -> None:
    if not body:
        return
    if len(body) > 256:
        raise ValueError("outreach request body must be empty or {}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("outreach request body must be empty or valid JSON object") from exc
    if payload != {}:
        raise ValueError("outreach v0.1 does not accept prompt, tone, tenant, profile or other input")


def _retry_after_seconds(retry_after: str | None, now: datetime) -> str | None:
    if not retry_after:
        return None
    try:
        target = datetime.fromisoformat(retry_after.replace("Z", "+00:00"))
    except ValueError:
        return None
    if target.tzinfo is None or target.utcoffset() is None:
        return None
    seconds = max(1, math.ceil((target - now.astimezone(target.tzinfo)).total_seconds()))
    return str(seconds)


_CONTRACT_OR_ELIGIBILITY_CODES = {
    "OUTREACH_NOT_ELIGIBLE",
    "OUTREACH_STAGE_NOT_SUPPORTED",
    "OUTREACH_CORE_FACTS_MISSING",
    "MODEL_NOT_ALLOWED",
    "MATCH_STATUS_NOT_ALLOWED",
    "NO_GROUNDED_FACTS",
    "MODEL_FACT_BUDGET_NO_FIT",
}

_MODEL_OUTPUT_CODES = {
    "OUTREACH_OUTPUT_SCHEMA_INVALID",
    "OUTREACH_OPPORTUNITY_MISMATCH",
    "OUTREACH_STRATEGY_NOT_ALLOWED",
    "OUTREACH_POSITIONING_NOT_ALLOWED",
    "OUTREACH_QUESTIONS_INVALID",
    "OUTREACH_QUESTION_NOT_ALLOWED",
    "OUTREACH_FACT_REFERENCES_INVALID",
    "OUTREACH_UNGROUNDED_FACT_REFERENCE",
    "OUTREACH_CORE_FACT_REFERENCES_REQUIRED",
    "OUTREACH_PROFILE_REFERENCES_INVALID",
    "OUTREACH_PROFILE_PATH_NOT_ALLOWED",
    "OUTREACH_POSITIONING_REFERENCE_REQUIRED",
    "OUTREACH_RENDER_FACT_MISSING",
    "OUTREACH_RENDER_PROFILE_MISSING",
    "MODEL_JSON_INVALID",
    "RESPONSE_INVALID",
}


class OutreachHttpTransport:
    """Same-origin authenticated on-demand outreach endpoint.

    The browser supplies only the opportunity id in the path. It cannot add free-form
    prompts or choose tenant/profile. All model input is rebuilt server-side from the
    authenticated customer profile plus VERIFIED public facts.
    """

    def __init__(
        self,
        *,
        principal_resolver: TrustedPrincipalResolver,
        service: GroundedOutreachService,
    ) -> None:
        self._principal_resolver = principal_resolver
        self._service = service

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes,
        now: datetime,
    ) -> OutreachHttpResponse:
        if now.tzinfo is None or now.utcoffset() is None:
            return _json_response(500, {"error": "SERVER_TIME_INVALID"})
        opportunity_id = _opportunity_id(target)
        if opportunity_id is None:
            return _json_response(404, {"error": "NOT_FOUND"})
        if method.upper() != "POST":
            return _json_response(405, {"error": "METHOD_NOT_ALLOWED"}, extra_headers={"Allow": "POST"})

        principal = self._principal_resolver.resolve(headers)
        if principal is None or not principal.tenant_id.strip() or not principal.profile_id.strip():
            return _json_response(401, {"error": "UNAUTHORIZED"})

        try:
            _validate_empty_request(body)
            result = self._service.generate(
                principal=principal,
                opportunity_id=opportunity_id,
                now=now,
            )
            return _json_response(200, result.public_result)
        except ValueError:
            return _json_response(400, {"error": "INVALID_REQUEST"})
        except OutreachServiceError as exc:
            if exc.code in {"PROFILE_NOT_FOUND", "OPPORTUNITY_NOT_FOUND"}:
                return _json_response(404, {"error": exc.code})
            if exc.code == "OUTREACH_PROVIDER_NOT_CONFIGURED":
                return _json_response(503, {"error": exc.code})
            if exc.code == "OUTREACH_PROVIDER_DEFERRED":
                retry_seconds = _retry_after_seconds(exc.retry_after, now)
                extra = {"Retry-After": retry_seconds} if retry_seconds else None
                return _json_response(429, {"error": exc.code}, extra_headers=extra)
            if exc.code == "HTTP_429":
                return _json_response(429, {"error": "OUTREACH_PROVIDER_RATE_LIMITED"})
            if exc.code in _CONTRACT_OR_ELIGIBILITY_CODES:
                return _json_response(409, {"error": exc.code})
            if exc.code in _MODEL_OUTPUT_CODES:
                return _json_response(502, {"error": "OUTREACH_MODEL_OUTPUT_REJECTED"})
            if exc.code in {"HTTP_5XX", "HTTP_408", "NETWORK_ERROR", "OUTREACH_MODEL_CALL_FAILED"}:
                return _json_response(502, {"error": "OUTREACH_PROVIDER_ERROR"})
            if exc.code == "OUTREACH_LEASE_RELEASE_FAILED":
                return _json_response(503, {"error": exc.code})
            return _json_response(500, {"error": "OUTREACH_INTERNAL_ERROR"})
        except RuntimeError:
            return _json_response(500, {"error": "OUTREACH_INTERNAL_ERROR"})
        except Exception:
            return _json_response(500, {"error": "INTERNAL_ERROR"})
