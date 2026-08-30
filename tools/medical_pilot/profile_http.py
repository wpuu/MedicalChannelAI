from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

from .customer_profile_gate import evaluate_customer_profile
from .customer_profile_validation import validate_customer_profile_payload
from .today_actions_http import TrustedPrincipal, TrustedPrincipalResolver


MAX_PROFILE_BODY_BYTES = 64 * 1024
BOOTSTRAP_PLACEHOLDER_NOTE = "BOOTSTRAP_PLACEHOLDER_NOT_CUSTOMER_CONFIRMED"

_EDITABLE_FIELDS = {
    "company_name",
    "business_role",
    "operating_regions",
    "customer_types",
    "product_capabilities",
    "partnering_policy",
    "opportunity_thresholds",
    "exclusion_rules",
    "hospital_relationships",
    "confirmation_flags",
}

_SERVER_FIELDS = {
    "schema_version",
    "tenant_id",
    "profile_id",
    "profile_status",
    "profile_completeness",
    "missing_required_conditions",
    "updated_at",
}


@dataclass(frozen=True)
class ProfileHttpResponse:
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


def _json_response(status_code: int, body: dict[str, Any], *, allow: str | None = None) -> ProfileHttpResponse:
    headers = dict(_BASE_HEADERS)
    if allow is not None:
        headers["Allow"] = allow
    return ProfileHttpResponse(
        status_code=status_code,
        headers=headers,
        body=json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8"),
    )


def _json_request(body: bytes) -> dict[str, Any]:
    if not body or len(body) > MAX_PROFILE_BODY_BYTES:
        raise ValueError("profile request body is required and must be <=64KiB")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("profile request body must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("profile request body must be an object")
    unexpected = sorted(set(payload) - _EDITABLE_FIELDS)
    if unexpected:
        raise ValueError("profile request contains non-editable fields")
    return payload


class ProfileRepository(Protocol):
    def load_profile(self, tenant_id: str, profile_id: str) -> dict[str, Any] | None: ...
    def upsert_profile(self, profile: dict[str, Any]) -> None: ...


def _principal(
    resolver: TrustedPrincipalResolver,
    headers: Mapping[str, str],
) -> TrustedPrincipal | None:
    principal = resolver.resolve(headers)
    if principal is None:
        return None
    if not principal.tenant_id.strip() or not principal.profile_id.strip():
        return None
    return principal


def _public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    result = {key: copy.deepcopy(profile.get(key)) for key in sorted(_EDITABLE_FIELDS)}

    # A bootstrap profile must be schema-shaped before an invitation can exist, but
    # its sentinel values are not customer-confirmed business facts. Never present
    # those placeholders back to the customer as if they had selected them.
    capabilities = result.get("product_capabilities")
    if isinstance(capabilities, list):
        result["product_capabilities"] = [
            item
            for item in capabilities
            if not (isinstance(item, dict) and item.get("notes") == BOOTSTRAP_PLACEHOLDER_NOTE)
        ]
    flags = result.get("confirmation_flags")
    if isinstance(flags, dict) and flags.get("customer_types_confirmed") is False:
        if result.get("customer_types") == ["OTHER"]:
            result["customer_types"] = []

    result.update(
        {
            "schema_version": "0.1",
            "profile_status": profile.get("profile_status"),
            "profile_completeness": profile.get("profile_completeness"),
            "missing_required_conditions": copy.deepcopy(
                profile.get("missing_required_conditions") or []
            ),
            "updated_at": profile.get("updated_at"),
        }
    )
    return result


def _with_defaults(profile: dict[str, Any]) -> dict[str, Any]:
    profile.setdefault("schema_version", "0.1")
    profile.setdefault("company_name", "")
    profile.setdefault("business_role", "OTHER")
    profile.setdefault("operating_regions", [])
    profile.setdefault("customer_types", [])
    profile.setdefault("product_capabilities", [])
    profile.setdefault(
        "partnering_policy",
        {
            "can_seek_temporary_manufacturer": False,
            "can_cooperate_with_channel_partner": False,
            "can_do_rental_projects": False,
        },
    )
    profile.setdefault(
        "opportunity_thresholds",
        {"minimum_project_amount_cny": "0", "preferred_stages": []},
    )
    profile.setdefault("exclusion_rules", [])
    profile.setdefault("hospital_relationships", [])
    profile.setdefault(
        "confirmation_flags",
        {
            "region_scope_confirmed": False,
            "customer_types_confirmed": False,
            "product_capabilities_confirmed": False,
            "partnering_policy_confirmed": False,
            "opportunity_preferences_confirmed": False,
            "exclusion_rules_confirmed": False,
        },
    )
    return profile


class ProfileHttpTransport:
    """Authenticated customer-profile editing boundary.

    Session identity fixes tenant/profile. Editable customer facts are validated,
    server readiness is recomputed, and only then is the profile persisted. When the
    profile is usable for candidates, one idempotent Today Actions refresh may be
    started immediately so grounded Agnes work enters the server-only queue.
    """

    def __init__(
        self,
        *,
        principal_resolver: TrustedPrincipalResolver,
        repository: ProfileRepository,
        after_save: Callable[[TrustedPrincipal, datetime], None] | None = None,
    ) -> None:
        self._principal_resolver = principal_resolver
        self._repository = repository
        self._after_save = after_save

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes,
        now: datetime,
    ) -> ProfileHttpResponse:
        if urlsplit(target).path != "/profile":
            return _json_response(404, {"error": "NOT_FOUND"})
        if method.upper() not in {"GET", "PUT"}:
            return _json_response(405, {"error": "METHOD_NOT_ALLOWED"}, allow="GET, PUT")
        if now.tzinfo is None or now.utcoffset() is None:
            return _json_response(500, {"error": "SERVER_TIME_INVALID"})

        principal = _principal(self._principal_resolver, headers)
        if principal is None:
            return _json_response(401, {"error": "UNAUTHORIZED"})

        try:
            stored = self._repository.load_profile(principal.tenant_id, principal.profile_id)
            if stored is None:
                return _json_response(404, {"error": "PROFILE_NOT_FOUND"})
            if stored.get("tenant_id") != principal.tenant_id or stored.get("profile_id") != principal.profile_id:
                return _json_response(404, {"error": "PROFILE_NOT_FOUND"})

            if method.upper() == "GET":
                gate = evaluate_customer_profile(stored)
                return _json_response(
                    200,
                    {"profile": _public_profile(stored), "readiness": gate.as_dict()},
                )

            editable = _json_request(body)
            candidate = _with_defaults(copy.deepcopy(stored))
            for key, value in editable.items():
                candidate[key] = copy.deepcopy(value)
            for key in _SERVER_FIELDS:
                if key not in {"schema_version", "tenant_id", "profile_id"}:
                    candidate.pop(key, None)

            candidate["schema_version"] = "0.1"
            candidate["tenant_id"] = principal.tenant_id
            candidate["profile_id"] = principal.profile_id
            gate = evaluate_customer_profile(candidate)
            candidate["profile_status"] = gate.computed_status
            candidate["profile_completeness"] = gate.profile_completeness
            candidate["missing_required_conditions"] = [
                item.code for item in gate.missing_conditions
            ]
            candidate["updated_at"] = now.astimezone(timezone.utc).isoformat()

            validate_customer_profile_payload(candidate)
            self._repository.upsert_profile(candidate)

            if gate.candidate_opportunity_allowed and self._after_save is not None:
                try:
                    self._after_save(principal, now)
                except Exception:
                    # Saving customer-confirmed facts must survive a temporary queue
                    # failure; opening /today safely retries the same immutable tasks.
                    pass

            return _json_response(
                200,
                {"profile": _public_profile(candidate), "readiness": gate.as_dict()},
            )
        except ValueError:
            return _json_response(400, {"error": "INVALID_REQUEST"})
        except RuntimeError:
            return _json_response(500, {"error": "INTERNAL_RESPONSE_REJECTED"})
        except Exception:
            return _json_response(500, {"error": "INTERNAL_ERROR"})
