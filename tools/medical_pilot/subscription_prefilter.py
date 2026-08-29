from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .collector_core import SCHEMA_VERSION
from .matching_profile_gate import evaluate_matching_profile


@dataclass(frozen=True)
class ProfileSubscriptionIndex:
    input_profile_count: int
    indexed_profile_ids: tuple[str, ...]
    profiles_by_city: dict[tuple[str, str], frozenset[str]]
    profiles_by_district: dict[tuple[str, str, str], frozenset[str]]
    entire_city_profiles: dict[tuple[str, str], frozenset[str]]
    profiles_by_taxonomy: dict[str, frozenset[str]]
    profiles_by_customer_type: dict[str, frozenset[str]]


def _add(mapping: dict[Any, set[str]], key: Any, profile_id: str) -> None:
    mapping.setdefault(key, set()).add(profile_id)


def build_profile_subscription_index(profiles: list[dict[str, Any]]) -> ProfileSubscriptionIndex:
    by_city: dict[tuple[str, str], set[str]] = {}
    by_district: dict[tuple[str, str, str], set[str]] = {}
    entire_city: dict[tuple[str, str], set[str]] = {}
    by_taxonomy: dict[str, set[str]] = {}
    by_customer_type: dict[str, set[str]] = {}
    indexed_ids: list[str] = []

    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        profile_id = profile.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id:
            continue
        readiness = evaluate_matching_profile(profile)
        if not readiness.candidate_opportunity_allowed:
            continue

        indexed_ids.append(profile_id)
        for region in profile.get("operating_regions") or []:
            if not isinstance(region, dict):
                continue
            province = region.get("province")
            city = region.get("city")
            if not isinstance(province, str) or not isinstance(city, str) or not province or not city:
                continue
            city_key = (province, city)
            _add(by_city, city_key, profile_id)
            if region.get("scope_mode") == "ENTIRE_CITY":
                _add(entire_city, city_key, profile_id)
            else:
                for district in region.get("districts") or []:
                    if isinstance(district, str) and district:
                        _add(by_district, (province, city, district), profile_id)

        for capability in profile.get("product_capabilities") or []:
            if not isinstance(capability, dict):
                continue
            for taxonomy_id in capability.get("taxonomy_ids") or []:
                if isinstance(taxonomy_id, str) and taxonomy_id:
                    _add(by_taxonomy, taxonomy_id, profile_id)

        for customer_type in profile.get("customer_types") or []:
            if isinstance(customer_type, str) and customer_type:
                _add(by_customer_type, customer_type, profile_id)

    return ProfileSubscriptionIndex(
        input_profile_count=len(profiles),
        indexed_profile_ids=tuple(sorted(set(indexed_ids))),
        profiles_by_city={key: frozenset(value) for key, value in by_city.items()},
        profiles_by_district={key: frozenset(value) for key, value in by_district.items()},
        entire_city_profiles={key: frozenset(value) for key, value in entire_city.items()},
        profiles_by_taxonomy={key: frozenset(value) for key, value in by_taxonomy.items()},
        profiles_by_customer_type={key: frozenset(value) for key, value in by_customer_type.items()},
    )


def prefilter_profiles_for_opportunity(
    index: ProfileSubscriptionIndex,
    opportunity: dict[str, Any],
) -> dict[str, Any]:
    """Narrow possible subscribers without replacing the full deterministic Match Gate.

    This layer must have validated taxonomy and customer type. Region filtering is
    conservative: if district is unknown, selected-district profiles in the same city
    remain candidates and the full match gate decides later. This avoids false negatives.
    """

    required: list[str] = []
    region = opportunity.get("region") if isinstance(opportunity.get("region"), dict) else {}
    province = region.get("province")
    city = region.get("city")
    district = region.get("district")
    if not isinstance(province, str) or not province or not isinstance(city, str) or not city:
        required.append("opportunity.region.province_city")

    labels = opportunity.get("product_labels")
    if not isinstance(labels, list) or not labels:
        required.append("opportunity.product_labels")
    elif opportunity.get("product_label_validation_status") != "VALIDATED":
        required.append("opportunity.product_label_validation_status")

    customer_type = opportunity.get("customer_type")
    if not isinstance(customer_type, str) or not customer_type or customer_type == "UNKNOWN":
        required.append("opportunity.customer_type")
    elif opportunity.get("customer_type_validation_status") != "VALIDATED":
        required.append("opportunity.customer_type_validation_status")

    if required:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "NEEDS_MORE_FACTS",
            "input_profile_count": index.input_profile_count,
            "indexed_profile_count": len(index.indexed_profile_ids),
            "candidate_profile_ids": [],
            "required_next_facts": list(dict.fromkeys(required)),
            "interpretation": "PERFORMANCE_PREFILTER_ONLY_FINAL_MATCH_STILL_REQUIRED",
        }

    assert isinstance(province, str) and isinstance(city, str)
    city_key = (province, city)
    region_candidates = set(index.profiles_by_city.get(city_key, frozenset()))
    if isinstance(district, str) and district:
        exact_district = set(index.profiles_by_district.get((province, city, district), frozenset()))
        whole_city = set(index.entire_city_profiles.get(city_key, frozenset()))
        region_candidates = exact_district.union(whole_city)

    taxonomy_candidates: set[str] = set()
    for label in labels:
        if isinstance(label, str):
            taxonomy_candidates.update(index.profiles_by_taxonomy.get(label, frozenset()))

    type_candidates = set(index.profiles_by_customer_type.get(customer_type, frozenset()))
    candidates = sorted(region_candidates.intersection(taxonomy_candidates).intersection(type_candidates))

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "READY",
        "input_profile_count": index.input_profile_count,
        "indexed_profile_count": len(index.indexed_profile_ids),
        "candidate_profile_ids": candidates,
        "required_next_facts": [],
        "interpretation": "PERFORMANCE_PREFILTER_ONLY_FINAL_MATCH_STILL_REQUIRED",
    }
