from __future__ import annotations

from typing import Any

from .customer_profile_gate import evaluate_customer_profile
from .opportunity_match_gate import MatchReason, OpportunityMatchResult, evaluate_opportunity_match


VALIDATED_PRODUCT_LABEL_PROVENANCE = {
    "DETERMINISTIC",
    "HUMAN_CONFIRMED",
    "CONTROLLED_MODEL_CLASSIFICATION",
}

VALIDATED_CUSTOMER_TYPE_PROVENANCE = {
    "OFFICIAL_INSTITUTION_EVIDENCE",
    "OFFICIAL_ORGANIZATION_TYPE",
    "HUMAN_CONFIRMED",
}


def _needs_fact_result(
    *,
    profile: dict[str, Any],
    code: str,
    field_path: str,
    message: str,
) -> OpportunityMatchResult:
    profile_gate = evaluate_customer_profile(profile)
    return OpportunityMatchResult(
        status="NEEDS_MORE_FACTS",
        recommendation_mode="FACT_ENRICHMENT_REQUIRED",
        personalized_recommendation_allowed=False,
        candidate_opportunity_allowed=True,
        model_explanation_allowed=False,
        reasons=(MatchReason(code, field_path, "NEEDS_MORE_FACTS", message),),
        required_next_facts=(field_path,),
        profile_gate=profile_gate,
    )


def _customer_type_gate(profile: dict[str, Any], opportunity: dict[str, Any]) -> OpportunityMatchResult | None:
    profile_gate = evaluate_customer_profile(profile)
    if not profile_gate.candidate_opportunity_allowed:
        return None

    customer_type = opportunity.get("customer_type")
    if customer_type in {None, "", "UNKNOWN"}:
        return None

    provenance = opportunity.get("customer_type_provenance")
    validation = opportunity.get("customer_type_validation_status")
    if provenance not in VALIDATED_CUSTOMER_TYPE_PROVENANCE:
        return _needs_fact_result(
            profile=profile,
            code="CUSTOMER_TYPE_PROVENANCE_MISSING",
            field_path="opportunity.customer_type_provenance",
            message="机构类型没有可接受的官方/人工确认来源，不能用于客户类型匹配。",
        )
    if validation != "VALIDATED":
        return _needs_fact_result(
            profile=profile,
            code="CUSTOMER_TYPE_NOT_VALIDATED",
            field_path="opportunity.customer_type_validation_status",
            message="机构类型尚未完成验证，不能仅凭机构名称或模型判断其为三甲、二级、疾控等类型。",
        )
    if provenance == "OFFICIAL_INSTITUTION_EVIDENCE" and not opportunity.get("institution_evidence_id"):
        return _needs_fact_result(
            profile=profile,
            code="INSTITUTION_EVIDENCE_ID_MISSING",
            field_path="opportunity.institution_evidence_id",
            message="机构类型声称来自官方 Institution Evidence，但缺少对应 evidence id。",
        )
    return None


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
        return _needs_fact_result(
            profile=profile,
            code="PRODUCT_CLASSIFICATION_PROVENANCE_MISSING",
            field_path="opportunity.product_label_provenance",
            message="产品分类没有可接受的来源标记，不能用于客户匹配。",
        )

    if validation != "VALIDATED":
        message = (
            "受控模型产品分类仍处于 benchmark pending，不能直接用于正式匹配。"
            if provenance == "CONTROLLED_MODEL_CLASSIFICATION" and validation == "BENCHMARK_PENDING"
            else "产品分类尚未完成验证，不能直接用于正式匹配。"
        )
        return _needs_fact_result(
            profile=profile,
            code="PRODUCT_CLASSIFICATION_NOT_VALIDATED",
            field_path="opportunity.product_label_validation_status",
            message=message,
        )
    return None


def evaluate_match_pipeline(profile: dict[str, Any], opportunity: dict[str, Any]) -> OpportunityMatchResult:
    """Public v0.1 matching entrypoint.

    Institution/customer type and product taxonomy are derived inputs. They may
    only influence matching after their provenance has been explicitly validated.
    The lower-level opportunity gate remains deterministic and model-free.
    """

    customer_type_block = _customer_type_gate(profile, opportunity)
    if customer_type_block is not None:
        return customer_type_block
    classification_block = _classification_gate(profile, opportunity)
    if classification_block is not None:
        return classification_block
    return evaluate_opportunity_match(profile, opportunity)
