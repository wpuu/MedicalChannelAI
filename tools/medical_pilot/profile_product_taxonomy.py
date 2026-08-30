from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .product_classifier import taxonomy_ids


@dataclass(frozen=True)
class ProfileTaxonomyIssue:
    code: str
    field_path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "message": self.message,
        }


def validate_profile_product_taxonomy(profile: dict[str, Any]) -> tuple[ProfileTaxonomyIssue, ...]:
    allowed = taxonomy_ids()
    issues: list[ProfileTaxonomyIssue] = []
    capabilities = profile.get("product_capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        return (
            ProfileTaxonomyIssue(
                "PRODUCT_CAPABILITIES_MISSING",
                "product_capabilities",
                "客户尚未提供可执行产品能力。",
            ),
        )

    for index, capability in enumerate(capabilities):
        path = f"product_capabilities[{index}].taxonomy_ids"
        if not isinstance(capability, dict):
            issues.append(ProfileTaxonomyIssue("PRODUCT_CAPABILITY_INVALID", f"product_capabilities[{index}]", "产品能力记录格式无效。"))
            continue
        labels = capability.get("taxonomy_ids")
        if not isinstance(labels, list) or not labels:
            issues.append(
                ProfileTaxonomyIssue(
                    "PRODUCT_TAXONOMY_IDS_MISSING",
                    path,
                    "该产品能力尚未映射到受控 taxonomy，不能用于正式商机匹配。",
                )
            )
            continue
        seen: set[str] = set()
        for label in labels:
            if not isinstance(label, str) or not label or label in seen:
                issues.append(ProfileTaxonomyIssue("PRODUCT_TAXONOMY_ID_INVALID", path, "产品 taxonomy ID 为空、重复或格式无效。"))
                continue
            seen.add(label)
            if label not in allowed:
                issues.append(
                    ProfileTaxonomyIssue(
                        "PRODUCT_TAXONOMY_ID_UNKNOWN",
                        path,
                        f"未知 taxonomy ID：{label}。必须先加入受控字典或重新确认客户产品范围。",
                    )
                )
    return tuple(issues)


def normalized_profile_for_taxonomy_match(profile: dict[str, Any]) -> dict[str, Any]:
    """Expand each customer capability into one internal capability per taxonomy id.

    The lower deterministic matcher historically compares category/subcategory
    strings. This adapter prevents a risky all-at-once rewrite while changing
    the effective matching key to stable taxonomy IDs. Human-readable category
    and subcategory stay in the original profile and are not used here.
    """

    issues = validate_profile_product_taxonomy(profile)
    if issues:
        raise ValueError("profile taxonomy is not valid")

    result = copy.deepcopy(profile)
    expanded: list[dict[str, Any]] = []
    for capability in profile.get("product_capabilities") or []:
        for label in capability.get("taxonomy_ids") or []:
            normalized = copy.deepcopy(capability)
            normalized["category"] = label
            normalized["subcategory"] = None
            normalized["taxonomy_ids"] = [label]
            expanded.append(normalized)
    result["product_capabilities"] = expanded
    return result
