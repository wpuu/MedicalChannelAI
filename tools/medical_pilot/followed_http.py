from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import math
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

from .followed_store import SQLiteFollowedOpportunityStore
from .today_actions_http import TrustedPrincipalResolver


class FollowedRepository(Protocol):
    def load_public_opportunity(self, opportunity_id: str) -> dict[str, Any] | None: ...
    def load_evidence(
        self, tenant_id: str, opportunity_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]: ...


@dataclass(frozen=True)
class FollowedHttpResponse:
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


def _json_response(status_code: int, body: dict[str, Any]) -> FollowedHttpResponse:
    return FollowedHttpResponse(
        status_code=status_code,
        headers=dict(_BASE_HEADERS),
        body=json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8"),
    )


def _text(opportunity: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = opportunity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _coerce_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation:
            return None
        if not parsed.is_finite():
            return None
        return float(parsed)
    return None


def _number(opportunity: dict[str, Any], *keys: str) -> float | int | None:
    for key in keys:
        value = opportunity.get(key)
        direct = _coerce_number(value)
        if direct is not None:
            return direct
        if isinstance(value, dict):
            for nested_key in ("amount_cny", "amount", "value"):
                nested = _coerce_number(value.get(nested_key))
                if nested is not None:
                    return nested
    return None


def _verified_urls(evidence: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for fact in evidence:
        if not isinstance(fact, dict) or fact.get("verification_status") != "VERIFIED":
            continue
        value = fact.get("source_url")
        if not isinstance(value, str) or not value.strip():
            continue
        url = value.strip()
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result[:20]


class FollowedHttpTransport:
    """Authenticated current follow-up list, independent from Today Top5 ranking."""

    def __init__(
        self,
        *,
        principal_resolver: TrustedPrincipalResolver,
        repository: FollowedRepository,
        store: SQLiteFollowedOpportunityStore,
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
    ) -> FollowedHttpResponse:
        if now.tzinfo is None or now.utcoffset() is None:
            return _json_response(500, {"error": "SERVER_TIME_INVALID"})
        parsed = urlsplit(target)
        if parsed.path != "/followed":
            return _json_response(404, {"error": "NOT_FOUND"})
        if parsed.query or parsed.fragment or body:
            return _json_response(400, {"error": "INVALID_REQUEST"})
        if method.upper() != "GET":
            return _json_response(405, {"error": "METHOD_NOT_ALLOWED"})

        principal = self._principal_resolver.resolve(headers)
        if principal is None or not principal.tenant_id.strip() or not principal.profile_id.strip():
            return _json_response(401, {"error": "UNAUTHORIZED"})

        try:
            current = self._store.list_current(principal=principal, limit=100)
            ids = [item.opportunity_id for item in current]
            evidence_by_id = self._repository.load_evidence(principal.tenant_id, ids)
            rows: list[dict[str, Any]] = []
            for item in current:
                opportunity = self._repository.load_public_opportunity(item.opportunity_id)
                if opportunity is None:
                    raise RuntimeError("follow-up references missing public opportunity")
                rows.append(
                    {
                        "opportunity_id": item.opportunity_id,
                        "followup_status": item.status,
                        "remind_at": item.remind_at,
                        "latest_note": item.note,
                        "followup_updated_at": item.updated_at,
                        "facts": {
                            "project_number": _text(opportunity, "project_number", "project_code"),
                            "project_name": _text(opportunity, "project_name"),
                            "buyer_name": _text(opportunity, "buyer_name"),
                            "hospital_name": _text(opportunity, "hospital_name"),
                            "department": _text(opportunity, "department"),
                            "lifecycle_state": _text(opportunity, "lifecycle_state"),
                            "published_at": _text(opportunity, "published_at", "publish_date"),
                            "bid_deadline": _text(opportunity, "bid_deadline"),
                            "expected_procurement_at": _text(
                                opportunity,
                                "expected_procurement_at",
                                "expected_purchase_date",
                            ),
                            "budget_cny": _number(
                                opportunity,
                                "budget_cny",
                                "budget_amount_cny",
                                "budget",
                            ),
                        },
                        "evidence_source_urls": _verified_urls(
                            evidence_by_id.get(item.opportunity_id, [])
                        ),
                    }
                )
            return _json_response(
                200,
                {
                    "schema_version": "0.1",
                    "mode": "FOLLOWED_OPPORTUNITIES",
                    "count": len(rows),
                    "items": rows,
                },
            )
        except (ValueError, RuntimeError):
            return _json_response(500, {"error": "FOLLOWED_INTERNAL_ERROR"})
