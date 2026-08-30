from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .collector_core import SCHEMA_VERSION


PROFILE_SUGGESTION_MAP = {
    "NO_PRODUCT_CAPABILITY": "REVIEW_PRODUCT_CAPABILITY_SCOPE",
    "NO_MANUFACTURER_ACCESS": "REVIEW_PARTNERING_POLICY",
    "RELATIONSHIP_TOO_WEAK": "REVIEW_RELATIONSHIP_ASSET",
    "AMOUNT_TOO_SMALL": "REVIEW_MINIMUM_PROJECT_AMOUNT",
    "DEPARTMENT_OUT_OF_SCOPE": "REVIEW_PRODUCT_OR_DEPARTMENT_SCOPE",
    "REGION_OUT_OF_SCOPE": "REVIEW_OPERATING_REGION",
    "RENTAL_NOT_SUPPORTED": "REVIEW_RENTAL_POLICY",
}


@dataclass(frozen=True)
class ProfileLearningSuggestion:
    code: str
    reason: str
    auto_apply_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason": self.reason,
            "auto_apply_allowed": self.auto_apply_allowed,
        }


def build_profile_learning_suggestions(followup: dict[str, Any]) -> dict[str, Any]:
    """Translate customer-confirmed follow-up feedback into review suggestions.

    Follow-up feedback is CUSTOMER_PRIVATE_FACT. It never changes OFFICIAL facts and
    never auto-mutates the customer profile. Suggestions require a separate explicit
    customer confirmation before profile rules are changed.
    """

    status = followup.get("status")
    reason = followup.get("not_fit_reason")
    customer_confirmed = followup.get("customer_confirmed") is True

    suggestions: list[ProfileLearningSuggestion] = []
    warnings: list[str] = []

    if status != "NOT_FIT":
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": followup.get("opportunity_id"),
            "learning_status": "NO_PROFILE_LEARNING_TRIGGER",
            "suggestions": [],
            "warnings": [],
        }

    if not customer_confirmed:
        warnings.append("FOLLOWUP_NOT_CUSTOMER_CONFIRMED")
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": followup.get("opportunity_id"),
            "learning_status": "REQUIRES_CUSTOMER_CONFIRMATION",
            "suggestions": [],
            "warnings": warnings,
        }

    code = PROFILE_SUGGESTION_MAP.get(reason)
    if code:
        suggestions.append(
            ProfileLearningSuggestion(
                code=code,
                reason=f"客户已确认该项目不适合，原因：{reason}。仅建议复核画像，不自动修改。",
            )
        )
    elif reason in {"PROJECT_TOO_LATE", "COMPETITOR_LOCKED_CUSTOMER_JUDGMENT", "OTHER"}:
        warnings.append("PROJECT_SPECIFIC_FEEDBACK_DO_NOT_GENERALIZE_TO_PROFILE")
    else:
        warnings.append("UNKNOWN_NOT_FIT_REASON")

    return {
        "schema_version": SCHEMA_VERSION,
        "opportunity_id": followup.get("opportunity_id"),
        "learning_status": "PROFILE_REVIEW_SUGGESTED" if suggestions else "PROJECT_SPECIFIC_ONLY",
        "suggestions": [item.as_dict() for item in suggestions],
        "warnings": warnings,
    }
