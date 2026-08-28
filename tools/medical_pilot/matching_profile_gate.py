from __future__ import annotations

from typing import Any

from .customer_profile_gate import (
    MissingCondition,
    ProfileGateResult,
    evaluate_customer_profile,
)
from .profile_product_taxonomy import validate_profile_product_taxonomy


def evaluate_matching_profile(profile: dict[str, Any]) -> ProfileGateResult:
    """Profile readiness used by the opportunity matching pipeline.

    The base interview gate validates business answers and explicit confirmations.
    This wrapper additionally requires every executable product capability to map
    to the controlled product taxonomy. A UI must not show a profile as 100%
    match-ready while taxonomy mapping is still missing.
    """

    base = evaluate_customer_profile(profile)
    taxonomy_issues = validate_profile_product_taxonomy(profile)
    if not taxonomy_issues:
        return base

    extra: list[MissingCondition] = []
    for issue in taxonomy_issues:
        question = (
            "你已经说明了产品范围，但还需要映射到标准产品分类。请确认具体产品，例如设备、试剂还是两者，并尽量给出具体名称；"
            "例如‘全自动化学发光免疫分析仪’和‘化学发光检测试剂’会被分成不同类别。"
        )
        extra.append(
            MissingCondition(
                code=issue.code,
                field_path=issue.field_path,
                severity="BLOCK_CANDIDATES",
                question=question,
                reason=issue.message,
            )
        )

    combined = tuple(base.missing_conditions) + tuple(extra)
    warnings = tuple(base.warnings) + (
        "PROFILE_PRODUCT_TAXONOMY_NOT_READY",
    )
    return ProfileGateResult(
        computed_status="INCOMPLETE",
        profile_completeness=min(base.profile_completeness, 60),
        recommendation_mode="PROFILE_INTERVIEW_REQUIRED",
        personalized_recommendation_allowed=False,
        candidate_opportunity_allowed=False,
        missing_conditions=combined,
        next_question=combined[0].question if combined else base.next_question,
        warnings=warnings,
    )
