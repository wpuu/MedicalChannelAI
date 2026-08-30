from __future__ import annotations

from datetime import datetime
import re
from typing import Any


_PROFILE_ID_RE = re.compile(r"^mprof_[0-9a-fA-F-]{36}$")
_TAXONOMY_ID_RE = re.compile(r"^[A-Z0-9_]{3,100}$")
_MONEY_RE = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")

_BUSINESS_ROLES = {
    "LOCAL_DISTRIBUTOR",
    "REGIONAL_DISTRIBUTOR",
    "MANUFACTURER_SALES",
    "MANUFACTURER_CHANNEL_MANAGER",
    "OTHER",
}
_CUSTOMER_TYPES = {
    "TERTIARY_HOSPITAL",
    "SECONDARY_HOSPITAL",
    "PRIMARY_CARE",
    "PRIVATE_HOSPITAL",
    "CDC",
    "BLOOD_CENTER",
    "UNIVERSITY",
    "RESEARCH_INSTITUTE",
    "THIRD_PARTY_LAB",
    "OTHER",
}
_CAPABILITY_TYPES = {
    "DIRECT_AUTHORIZED",
    "DIRECT_UNCONFIRMED",
    "CAN_SOURCE_PARTNER",
    "SERVICE_ONLY",
    "RENTAL_CAPABLE",
    "UNKNOWN",
}
_STAGES = {
    "MARKET_RESEARCH",
    "PROCUREMENT_INTENT",
    "PREPARING",
    "TENDERING",
    "AMENDED",
    "BID_CLOSED",
    "AWARDED",
}
_EXCLUSION_KINDS = {
    "PRODUCT_CATEGORY",
    "HOSPITAL_TYPE",
    "REGION",
    "PROJECT_STAGE",
    "OTHER",
}
_RELATIONSHIP_STRENGTHS = {"STRONG", "MEDIUM", "WEAK", "HISTORICAL", "UNKNOWN"}
_PROFILE_STATUSES = {
    "INCOMPLETE",
    "SUFFICIENT_FOR_CANDIDATES",
    "SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION",
}
_CONFIRMATION_KEYS = {
    "region_scope_confirmed",
    "customer_types_confirmed",
    "product_capabilities_confirmed",
    "partnering_policy_confirmed",
    "opportunity_preferences_confirmed",
    "exclusion_rules_confirmed",
}
_TOP_LEVEL_KEYS = {
    "schema_version",
    "profile_id",
    "tenant_id",
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
    "profile_status",
    "profile_completeness",
    "missing_required_conditions",
    "updated_at",
}


def _object(value: Any, name: str, *, allowed: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if allowed is not None:
        unexpected = set(value) - allowed
        if unexpected:
            raise ValueError(f"{name} contains unsupported fields")
    return value


def _text(value: Any, name: str, *, minimum: int = 1, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if len(value) < minimum or len(value) > maximum:
        raise ValueError(f"{name} length is invalid")
    return value


def _nullable_text(value: Any, name: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    return _text(value, name, maximum=maximum)


def _string_list(
    value: Any,
    name: str,
    *,
    minimum: int = 0,
    maximum: int,
    item_maximum: int,
    allowed: set[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded list")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, f"{name}[{index}]", maximum=item_maximum)
        if allowed is not None and text not in allowed:
            raise ValueError(f"{name}[{index}] is not allowed")
        result.append(text)
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must contain unique values")
    return result


def _iso_datetime(value: Any, name: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    text = _text(value, name, maximum=80)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone")


def _money(value: Any, name: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    text = _text(value, name, maximum=40)
    if not _MONEY_RE.fullmatch(text):
        raise ValueError(f"{name} must be a non-negative decimal string")


def validate_customer_profile_payload(profile: dict[str, Any]) -> None:
    """Validate the persisted customer profile contract without external dependencies.

    This intentionally mirrors the frozen JSON schema closely enough for the trusted
    Pilot write boundary. Business readiness is evaluated separately by
    ``evaluate_customer_profile``; this function checks structural safety only.
    """

    profile = _object(profile, "profile", allowed=_TOP_LEVEL_KEYS)
    if set(profile) != _TOP_LEVEL_KEYS:
        raise ValueError("profile is missing required fields")
    if profile.get("schema_version") != "0.1":
        raise ValueError("profile.schema_version must be 0.1")

    profile_id = _text(profile.get("profile_id"), "profile.profile_id", maximum=160)
    if not _PROFILE_ID_RE.fullmatch(profile_id):
        raise ValueError("profile.profile_id has invalid format")
    _text(profile.get("tenant_id"), "profile.tenant_id", maximum=160)
    _text(profile.get("company_name"), "profile.company_name", maximum=300)

    if profile.get("business_role") not in _BUSINESS_ROLES:
        raise ValueError("profile.business_role is invalid")

    regions = profile.get("operating_regions")
    if not isinstance(regions, list) or not regions or len(regions) > 64:
        raise ValueError("profile.operating_regions must contain 1..64 regions")
    for index, raw in enumerate(regions):
        item = _object(
            raw,
            f"profile.operating_regions[{index}]",
            allowed={"province", "city", "scope_mode", "districts"},
        )
        if set(item) != {"province", "city", "scope_mode", "districts"}:
            raise ValueError("operating region is missing required fields")
        _text(item.get("province"), f"operating_regions[{index}].province", maximum=100)
        _text(item.get("city"), f"operating_regions[{index}].city", maximum=100)
        scope_mode = item.get("scope_mode")
        if scope_mode not in {"ENTIRE_CITY", "SELECTED_DISTRICTS"}:
            raise ValueError("operating region scope_mode is invalid")
        districts = _string_list(
            item.get("districts"),
            f"operating_regions[{index}].districts",
            maximum=100,
            item_maximum=100,
        )
        if scope_mode == "ENTIRE_CITY" and districts:
            raise ValueError("ENTIRE_CITY region cannot contain districts")
        if scope_mode == "SELECTED_DISTRICTS" and not districts:
            raise ValueError("SELECTED_DISTRICTS region requires districts")

    _string_list(
        profile.get("customer_types"),
        "profile.customer_types",
        minimum=1,
        maximum=len(_CUSTOMER_TYPES),
        item_maximum=80,
        allowed=_CUSTOMER_TYPES,
    )

    products = profile.get("product_capabilities")
    if not isinstance(products, list) or not products or len(products) > 100:
        raise ValueError("profile.product_capabilities must contain 1..100 items")
    product_keys = {"category", "subcategory", "taxonomy_ids", "brands", "capability_type", "notes"}
    for index, raw in enumerate(products):
        item = _object(raw, f"product_capabilities[{index}]", allowed=product_keys)
        required = {"category", "taxonomy_ids", "capability_type"}
        if not required.issubset(item):
            raise ValueError("product capability is missing required fields")
        _text(item.get("category"), f"product_capabilities[{index}].category", maximum=200)
        _nullable_text(item.get("subcategory"), f"product_capabilities[{index}].subcategory", maximum=200)
        taxonomy_ids = _string_list(
            item.get("taxonomy_ids"),
            f"product_capabilities[{index}].taxonomy_ids",
            minimum=1,
            maximum=100,
            item_maximum=100,
        )
        if any(not _TAXONOMY_ID_RE.fullmatch(value) for value in taxonomy_ids):
            raise ValueError("product capability taxonomy id is invalid")
        _string_list(
            item.get("brands", []),
            f"product_capabilities[{index}].brands",
            maximum=100,
            item_maximum=200,
        )
        if item.get("capability_type") not in _CAPABILITY_TYPES:
            raise ValueError("product capability type is invalid")
        _nullable_text(item.get("notes"), f"product_capabilities[{index}].notes", maximum=1000)

    partnering = _object(
        profile.get("partnering_policy"),
        "profile.partnering_policy",
        allowed={
            "can_seek_temporary_manufacturer",
            "can_cooperate_with_channel_partner",
            "can_do_rental_projects",
        },
    )
    if set(partnering) != {
        "can_seek_temporary_manufacturer",
        "can_cooperate_with_channel_partner",
        "can_do_rental_projects",
    }:
        raise ValueError("partnering policy is missing required fields")
    if any(not isinstance(partnering[key], bool) for key in partnering):
        raise ValueError("partnering policy values must be booleans")

    thresholds = _object(
        profile.get("opportunity_thresholds"),
        "profile.opportunity_thresholds",
        allowed={"minimum_project_amount_cny", "owner_attention_amount_cny", "preferred_stages"},
    )
    if not {"minimum_project_amount_cny", "preferred_stages"}.issubset(thresholds):
        raise ValueError("opportunity thresholds are missing required fields")
    _money(thresholds.get("minimum_project_amount_cny"), "minimum_project_amount_cny")
    _money(thresholds.get("owner_attention_amount_cny"), "owner_attention_amount_cny", nullable=True)
    _string_list(
        thresholds.get("preferred_stages"),
        "preferred_stages",
        minimum=1,
        maximum=len(_STAGES),
        item_maximum=80,
        allowed=_STAGES,
    )

    exclusions = profile.get("exclusion_rules")
    if not isinstance(exclusions, list) or len(exclusions) > 100:
        raise ValueError("exclusion_rules must be a bounded list")
    for index, raw in enumerate(exclusions):
        item = _object(raw, f"exclusion_rules[{index}]", allowed={"kind", "value", "reason"})
        if not {"kind", "value"}.issubset(item):
            raise ValueError("exclusion rule is missing required fields")
        if item.get("kind") not in _EXCLUSION_KINDS:
            raise ValueError("exclusion rule kind is invalid")
        _text(item.get("value"), f"exclusion_rules[{index}].value", maximum=300)
        _nullable_text(item.get("reason"), f"exclusion_rules[{index}].reason", maximum=1000)

    relationships = profile.get("hospital_relationships")
    if not isinstance(relationships, list) or len(relationships) > 500:
        raise ValueError("hospital_relationships must be a bounded list")
    relationship_keys = {
        "hospital_name",
        "department",
        "relationship_strength",
        "owner",
        "confirmed_by_customer",
        "last_confirmed_at",
    }
    for index, raw in enumerate(relationships):
        item = _object(raw, f"hospital_relationships[{index}]", allowed=relationship_keys)
        if not {"hospital_name", "relationship_strength", "confirmed_by_customer"}.issubset(item):
            raise ValueError("hospital relationship is missing required fields")
        _text(item.get("hospital_name"), f"hospital_relationships[{index}].hospital_name", maximum=300)
        _nullable_text(item.get("department"), f"hospital_relationships[{index}].department", maximum=200)
        if item.get("relationship_strength") not in _RELATIONSHIP_STRENGTHS:
            raise ValueError("hospital relationship strength is invalid")
        _nullable_text(item.get("owner"), f"hospital_relationships[{index}].owner", maximum=200)
        if not isinstance(item.get("confirmed_by_customer"), bool):
            raise ValueError("hospital relationship confirmed_by_customer must be boolean")
        _iso_datetime(
            item.get("last_confirmed_at"),
            f"hospital_relationships[{index}].last_confirmed_at",
            nullable=True,
        )

    flags = _object(profile.get("confirmation_flags"), "profile.confirmation_flags", allowed=_CONFIRMATION_KEYS)
    if set(flags) != _CONFIRMATION_KEYS or any(not isinstance(flags[key], bool) for key in flags):
        raise ValueError("confirmation flags are invalid")

    if profile.get("profile_status") not in _PROFILE_STATUSES:
        raise ValueError("profile.profile_status is invalid")
    completeness = profile.get("profile_completeness")
    if not isinstance(completeness, int) or isinstance(completeness, bool) or not 0 <= completeness <= 100:
        raise ValueError("profile.profile_completeness is invalid")
    _string_list(
        profile.get("missing_required_conditions"),
        "profile.missing_required_conditions",
        maximum=100,
        item_maximum=200,
    )
    _iso_datetime(profile.get("updated_at"), "profile.updated_at")

    if profile.get("profile_status") == "SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION":
        if completeness < 80 or profile.get("missing_required_conditions"):
            raise ValueError("personalized profile readiness fields are inconsistent")
        if not all(flags.values()):
            raise ValueError("personalized profile requires all confirmation flags")
