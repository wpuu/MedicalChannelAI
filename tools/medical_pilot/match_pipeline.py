from __future__ import annotations

from typing import Any

from .classifier_admission import classifier_can_drive_matching
from .institution_enrichment import enrich_opportunity_customer_type
from .matching_profile_gate import evaluate_matching_profile
from .opportunity_match_gate import MatchReason, OpportunityMatchResult, evaluate_opportunity_match
from .product_classifier import taxonomy_ids
from .profile_product_taxonomy import normalized_profile_for_taxonomy_match


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


def _profile_block_result(profile: dict[str, Any]) -> OpportunityMatchResult | None:
    profile_gate = evaluate_matching_profile(profile)
    if profile_gate.candidate_opportunity_allowed:
        return None

    first_missing = profile_gate.missing_conditions[0] if profile_gate.missing_conditions else None
    reason = MatchReason(
        first_missing.code if first_missing is not None else "PROFILE_NOT_READY_FOR_MATCHING",
        f"profile.{first_missing.field_path}" if first_missing is not None else "profile",
        "BLOCK",
        first_missing.reason if first_missing is not None else "客户画像尚未达到商机匹配要求。",
    )
    return OpportunityMatchResult(
        status="PROFILE_BLOCKED",
        recommendation_mode="PROFILE_INTERVIEW_REQUIRED",
        personalized_recommendation_allowed=False,
        candidate_opportunity_allowed=False,
        model_explanation_allowed=False,
        reasons=(reason,),
        required_next_facts=(),
        profile_gate=profile_gate,
    )


def _needs_fact_result(
    *,
    profile: dict[str, Any],
    code: str,
    field_path: str,
    message: str,
) -> OpportunityMatchResult:
    profile_gate = evaluate_matching_profile(profile)
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
    labels = opportunity.get("product_labels")
    if not isinstance(labels, list) or not labels:
        return None

    allowed_taxonomy = taxonomy_ids()
    unknown_labels = [label for label in labels if not isinstance(label, str) or label not in allowed_taxonomy]
    if unknown_labels:
        return _needs_fact_result(
            profile=profile,
            code="PRODUCT_TAXONOMY_ID_UNKNOWN",
            field_path="opportunity.product_labels",
            message=f"项目产品分类包含未登记 taxonomy ID：{', '.join(map(str, unknown_labels))}。不能用于正式匹配。",
        )

    provenance = opportunity.get("product_label_provenance")
    validation = opportunity.get("product_label_validation_status")
    classifier_id = opportunity.get("product_classifier_id")

    if provenance not in VALIDATED_PRODUCT_LABEL_PROVENANCE:
        return _needs_fact_result(
            profile=profile,
            code="PRODUCT_CLASSIFICATION_PROVENANCE_MISSING",
            field_path="opportunity.product_label_provenance",
            message="产品分类没有可接受的来源标记，不能用于客户匹配。",
        )
    if not isinstance(classifier_id, str) or not classifier_id:
        return _needs_fact_result(
            profile=profile,
            code="PRODUCT_CLASSIFIER_ID_MISSING",
            field_path="opportunity.product_classifier_id",
            message="产品分类缺少分类器身份，无法验证该分类是否有资格驱动正式匹配。",
        )

    admitted, admission_reason = classifier_can_drive_matching(classifier_id, provenance)
    if not admitted:
        message = (
            "Agnes 产品 taxonomy 分类器仍处于 benchmark pending；即使单条结果自报 VALIDATED，也不能进入正式匹配。"
            if provenance == "CONTROLLED_MODEL_CLASSIFICATION"
            else f"产品分类器未通过全局准入：{admission_reason}。"
        )
        return _needs_fact_result(
            profile=profile,
            code="PRODUCT_CLASSIFIER_NOT_ADMITTED",
            field_path="opportunity.product_classifier_id",
            message=message,
        )

    if validation != "VALIDATED":
        return _needs_fact_result(
            profile=profile,
            code="PRODUCT_CLASSIFICATION_NOT_VALIDATED",
            field_path="opportunity.product_label_validation_status",
            message="产品分类本条结果尚未完成验证，不能直接用于正式匹配。",
        )
    return None


def evaluate_match_pipeline(profile: dict[str, Any], opportunity: dict[str, Any]) -> OpportunityMatchResult:
    """Public v0.1 matching entrypoint.

    Customer interview readiness and product-taxonomy readiness are evaluated by
    one public matching-profile gate. Institution/customer type is automatically
    enriched from the exact VERIFIED institution registry before type validation;
    fuzzy matching is not used and existing validated human values are preserved.
    Opportunity product taxonomy can influence matching only after provenance
    validation and classifier admission. The lower opportunity gate remains
    deterministic and model-free.
    """

    profile_block = _profile_block_result(profile)
    if profile_block is not None:
        return profile_block

    enriched_opportunity = enrich_opportunity_customer_type(opportunity)

    customer_type_block = _customer_type_gate(profile, enriched_opportunity)
    if customer_type_block is not None:
        return customer_type_block

    classification_block = _classification_gate(profile, enriched_opportunity)
    if classification_block is not None:
        return classification_block

    normalized_profile = normalized_profile_for_taxonomy_match(profile)
    return evaluate_opportunity_match(normalized_profile, enriched_opportunity)
