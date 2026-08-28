from __future__ import annotations

from typing import Any

from .customer_profile_gate import evaluate_customer_profile
from .opportunity_match_gate import MatchReason, OpportunityMatchResult, evaluate_opportunity_match


VALIDATED_PRODUCT_LABEL_PROVENANCE = {
    "DETERMINISTIC",
    "HUMAN_CONFIRMED",
    "CONTROLLED_MODEL_CLASSIFICATION",
}


def _classification_gate(profile: dict[str, Any], opportunity: dict[str, Any]) -> OpportunityMatchResult | None:
    profile_gate = evaluate_customer_profile(profile)
    if not profile_gate.candidate_opportunity_allowed:
        return None

    labels = opportunity.get("product_labels")
    if not isinstance(labels, list) or not labels:
        return None

    provenance = opportunity.get("product_label_provenance")
    validation = opportunity.get("product_label_validation_status")

    if provenance not in VALIDATED_PRODUCT_LABEL_PROVENANCE:
        return OpportunityMatchResult(
            status="NEEDS_MORE_FACTS",
            recommendation_mode="FACT_ENRICHMENT_REQUIRED",
            personalized_recommendation_allowed=False,
            candidate_opportunity_allowed=True,
            model_explanation_allowed=False,
            reasons=(
                MatchReason(
                    "PRODUCT_CLASSIFICATION_PROVENANCE_MISSING",
                    "opportunity.product_label_provenance",
                    "NEEDS_MORE_FACTS",
                    "产品分类没有可接受的来源标记，不能用于客户匹配。",
                ),
            ),
            required_next_facts=("opportunity.product_label_provenance",),
            profile_gate=profile_gate,
        )

    if validation != "VALIDATED":
        message = (
            "受控模型产品分类仍处于 benchmark pending，不能直接用于正式匹配。"
            if provenance == "CONTROLLED_MODEL_CLASSIFICATION" and validation == "BENCHMARK_PENDING"
            else "产品分类尚未完成验证，不能直接用于正式匹配。"
        )
        return OpportunityMatchResult(
            status="NEEDS_MORE_FACTS",
            recommendation_mode="FACT_ENRICHMENT_REQUIRED",
            personalized_recommendation_allowed=False,
            candidate_opportunity_allowed=True,
            model_explanation_allowed=False,
            reasons=(
                MatchReason(
                    "PRODUCT_CLASSIFICATION_NOT_VALIDATED",
                    "opportunity.product_label_validation_status",
                    "NEEDS_MORE_FACTS",
                    message,
                ),
            ),
            required_next_facts=("opportunity.product_label_validation_status",),
            profile_gate=profile_gate,
        )

    return None


def evaluate_match_pipeline(profile: dict[str, Any], opportunity: dict[str, Any]) -> OpportunityMatchResult:
    """Public v0.1 matching entrypoint.

    Product taxonomy is derived information rather than an official procurement
    fact. It may come from deterministic logic, human confirmation, or a
    controlled model classifier, but it must be explicitly VALIDATED before it
    can influence a customer match. The lower-level match gate intentionally
    remains model-free.
    """

    classification_block = _classification_gate(profile, opportunity)
    if classification_block is not None:
        return classification_block
    return evaluate_opportunity_match(profile, opportunity)
