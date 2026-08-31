from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .collector_core import SCHEMA_VERSION, normalize_space
from .customer_profile_gate import ProfileGateResult, evaluate_customer_profile


ALLOWED_VERIFICATION = {"VERIFIED"}
MATCHABLE_STAGES = {
    "MARKET_RESEARCH",
    "PROCUREMENT_INTENT",
    "PREPARING",
    "TENDERING",
    "AMENDED",
    "BID_CLOSED",
    "AWARDED",
}


@dataclass(frozen=True)
class MatchReason:
    code: str
    field_path: str
    outcome: str
    message: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "outcome": self.outcome,
            "message": self.message,
        }


@dataclass(frozen=True)
class OpportunityMatchResult:
    status: str
    recommendation_mode: str
    personalized_recommendation_allowed: bool
    candidate_opportunity_allowed: bool
    model_explanation_allowed: bool
    reasons: tuple[MatchReason, ...]
    required_next_facts: tuple[str, ...]
    profile_gate: ProfileGateResult

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "recommendation_mode": self.recommendation_mode,
            "personalized_recommendation_allowed": self.personalized_recommendation_allowed,
            "candidate_opportunity_allowed": self.candidate_opportunity_allowed,
            "model_explanation_allowed": self.model_explanation_allowed,
            "reasons": [reason.as_dict() for reason in self.reasons],
            "required_next_facts": list(self.required_next_facts),
            "profile_gate": self.profile_gate.as_dict(),
        }


def _text(value: Any) -> str:
    return normalize_space(value) if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    return _text(value).lower().replace(" ", "")


def _money(value: Any) -> Decimal | None:
    if isinstance(value, dict):
        value = value.get("amount")
    if not isinstance(value, str) or not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _profile_region_match(profile: dict[str, Any], opportunity: dict[str, Any]) -> tuple[str, MatchReason | None, str | None]:
    region = opportunity.get("region")
    if not isinstance(region, dict):
        return (
            "NEEDS_MORE_FACTS",
            MatchReason("OPPORTUNITY_REGION_MISSING", "opportunity.region", "NEEDS_MORE_FACTS", "商机缺少可核验的区域信息，不能判断是否在客户经营范围。"),
            "opportunity.region",
        )

    province = _norm(region.get("province"))
    city = _norm(region.get("city"))
    district = _norm(region.get("district"))
    if not province or not city:
        return (
            "NEEDS_MORE_FACTS",
            MatchReason("OPPORTUNITY_REGION_INCOMPLETE", "opportunity.region", "NEEDS_MORE_FACTS", "商机区域缺少省或城市。"),
            "opportunity.region",
        )

    same_city_regions: list[dict[str, Any]] = []
    for configured in profile.get("operating_regions") or []:
        if not isinstance(configured, dict):
            continue
        if _norm(configured.get("province")) == province and _norm(configured.get("city")) == city:
            same_city_regions.append(configured)

    if not same_city_regions:
        return (
            "REJECTED",
            MatchReason("OUTSIDE_OPERATING_REGION", "opportunity.region", "REJECT", "该项目不在客户已确认的经营城市范围内。"),
            None,
        )

    for configured in same_city_regions:
        if configured.get("scope_mode") == "ENTIRE_CITY":
            return "PASS", None, None
        if configured.get("scope_mode") == "SELECTED_DISTRICTS":
            allowed = {_norm(item) for item in (configured.get("districts") or []) if _text(item)}
            if not district:
                return (
                    "NEEDS_MORE_FACTS",
                    MatchReason("OPPORTUNITY_DISTRICT_MISSING", "opportunity.region.district", "NEEDS_MORE_FACTS", "客户只做指定区县，但该商机尚未核验所属区县。"),
                    "opportunity.region.district",
                )
            if district in allowed:
                return "PASS", None, None

    return (
        "REJECTED",
        MatchReason("OUTSIDE_SELECTED_DISTRICTS", "opportunity.region.district", "REJECT", "该项目不在客户已确认会做的区县内。"),
        None,
    )


def _customer_type_match(profile: dict[str, Any], opportunity: dict[str, Any]) -> tuple[str, MatchReason | None, str | None]:
    customer_type = _text(opportunity.get("customer_type"))
    if not customer_type or customer_type == "UNKNOWN":
        return (
            "NEEDS_MORE_FACTS",
            MatchReason("OPPORTUNITY_CUSTOMER_TYPE_UNKNOWN", "opportunity.customer_type", "NEEDS_MORE_FACTS", "不能仅凭机构名称猜三甲、二级、疾控或其他客户类型。"),
            "opportunity.customer_type",
        )
    allowed = set(profile.get("customer_types") or [])
    if customer_type not in allowed:
        return (
            "REJECTED",
            MatchReason("CUSTOMER_TYPE_EXCLUDED_BY_SCOPE", "opportunity.customer_type", "REJECT", "该机构类型不在客户已确认会做的客户范围内。"),
            None,
        )
    return "PASS", None, None


def _stage_match(profile: dict[str, Any], opportunity: dict[str, Any]) -> tuple[str, MatchReason | None]:
    stage = _text(opportunity.get("lifecycle_state"))
    if not stage:
        return "NEEDS_MORE_FACTS", MatchReason("OPPORTUNITY_STAGE_MISSING", "opportunity.lifecycle_state", "NEEDS_MORE_FACTS", "缺少当前项目生命周期状态。")
    if stage not in MATCHABLE_STAGES:
        return "REJECTED", MatchReason("STAGE_NOT_ACTIONABLE", "opportunity.lifecycle_state", "REJECT", "当前项目状态不属于可经营推荐阶段。")
    preferred = set((profile.get("opportunity_thresholds") or {}).get("preferred_stages") or [])
    if stage not in preferred:
        return "REJECTED", MatchReason("STAGE_NOT_PREFERRED", "opportunity.lifecycle_state", "REJECT", "该阶段不在客户已确认希望跟进的项目阶段内。")
    return "PASS", None


def _amount_match(profile: dict[str, Any], opportunity: dict[str, Any]) -> tuple[str, MatchReason | None, str | None]:
    minimum = _money((profile.get("opportunity_thresholds") or {}).get("minimum_project_amount_cny"))
    amount = _money(opportunity.get("budget"))
    if minimum is None:
        return "PROFILE_ERROR", MatchReason("PROFILE_MINIMUM_AMOUNT_INVALID", "profile.opportunity_thresholds.minimum_project_amount_cny", "BLOCK", "客户最低项目金额无效。"), None
    if amount is None:
        return (
            "NEEDS_MORE_FACTS",
            MatchReason("OPPORTUNITY_AMOUNT_UNKNOWN", "opportunity.budget", "NEEDS_MORE_FACTS", "当前公开信息没有可核验金额，无法应用客户最低金额门槛。"),
            "opportunity.budget",
        )
    if amount < minimum:
        return "REJECTED", MatchReason("BELOW_MINIMUM_PROJECT_AMOUNT", "opportunity.budget", "REJECT", "项目金额低于客户已确认的最低跟进金额。"), None
    return "PASS", None, None


def _is_excluded(profile: dict[str, Any], opportunity: dict[str, Any]) -> MatchReason | None:
    labels = {_norm(item) for item in opportunity.get("product_labels") or [] if _text(item)}
    stage = _norm(opportunity.get("lifecycle_state"))
    customer_type = _norm(opportunity.get("customer_type"))
    region = opportunity.get("region") if isinstance(opportunity.get("region"), dict) else {}
    region_values = {_norm(region.get("province")), _norm(region.get("city")), _norm(region.get("district"))}

    for rule in profile.get("exclusion_rules") or []:
        if not isinstance(rule, dict):
            continue
        kind = rule.get("kind")
        value = _norm(rule.get("value"))
        if not value:
            continue
        matched = (
            (kind == "PRODUCT_CATEGORY" and value in labels)
            or (kind == "HOSPITAL_TYPE" and value == customer_type)
            or (kind == "REGION" and value in region_values)
            or (kind == "PROJECT_STAGE" and value == stage)
        )
        if matched:
            return MatchReason("EXPLICIT_EXCLUSION_MATCH", "profile.exclusion_rules", "REJECT", f"命中客户明确排除规则：{_text(rule.get('value'))}。")
    return None


def _product_match(profile: dict[str, Any], opportunity: dict[str, Any]) -> tuple[str, MatchReason | None, str | None]:
    labels = {_norm(item) for item in opportunity.get("product_labels") or [] if _text(item)}
    if not labels:
        return (
            "NEEDS_MORE_FACTS",
            MatchReason("PRODUCT_CLASSIFICATION_MISSING", "opportunity.product_labels", "NEEDS_MORE_FACTS", "项目尚未形成受控产品分类，不能仅凭标题猜客户是否能做。"),
            "opportunity.product_labels",
        )

    partnering = profile.get("partnering_policy") if isinstance(profile.get("partnering_policy"), dict) else {}
    matched_any = False
    for capability in profile.get("product_capabilities") or []:
        if not isinstance(capability, dict):
            continue
        # Stable matching keys are controlled taxonomy IDs. category/subcategory are
        # retained only as a backwards-compatible fallback for older stored profiles.
        keys = {
            _norm(item)
            for item in (capability.get("taxonomy_ids") or [])
            if _text(item)
        }
        keys.update({_norm(capability.get("category")), _norm(capability.get("subcategory"))})
        keys.discard("")
        if not keys.intersection(labels):
            continue
        capability_type = capability.get("capability_type")
        if capability_type in {"DIRECT_AUTHORIZED", "DIRECT_UNCONFIRMED", "SERVICE_ONLY", "RENTAL_CAPABLE"}:
            matched_any = True
            break
        if capability_type == "CAN_SOURCE_PARTNER" and partnering.get("can_seek_temporary_manufacturer") is True:
            matched_any = True
            break

    if not matched_any:
        return (
            "REJECTED",
            MatchReason("NO_CONFIRMED_PRODUCT_CAPABILITY", "opportunity.product_labels", "REJECT", "项目产品分类与客户已确认的可执行产品能力不匹配。"),
            None,
        )
    return "PASS", None, None


def _rental_match(profile: dict[str, Any], opportunity: dict[str, Any]) -> tuple[str, MatchReason | None, str | None]:
    is_rental = opportunity.get("is_rental_project")
    if is_rental is None:
        return (
            "NEEDS_MORE_FACTS",
            MatchReason("RENTAL_CLASSIFICATION_UNKNOWN", "opportunity.is_rental_project", "NEEDS_MORE_FACTS", "尚未确认该项目是否属于租赁/租赁服务，不能应用客户租赁能力规则。"),
            "opportunity.is_rental_project",
        )
    if is_rental is False:
        return "PASS", None, None
    partnering = profile.get("partnering_policy") if isinstance(profile.get("partnering_policy"), dict) else {}
    if partnering.get("can_do_rental_projects") is not True:
        return (
            "REJECTED",
            MatchReason("RENTAL_PROJECT_NOT_SUPPORTED", "opportunity.is_rental_project", "REJECT", "该项目属于租赁类，但客户已确认不做租赁项目。"),
            None,
        )
    return "PASS", None, None


def evaluate_opportunity_match(profile: dict[str, Any], opportunity: dict[str, Any]) -> OpportunityMatchResult:
    profile_gate = evaluate_customer_profile(profile)
    if not profile_gate.candidate_opportunity_allowed:
        return OpportunityMatchResult(
            status="PROFILE_BLOCKED",
            recommendation_mode="PROFILE_INTERVIEW_REQUIRED",
            personalized_recommendation_allowed=False,
            candidate_opportunity_allowed=False,
            model_explanation_allowed=False,
            reasons=(MatchReason("PROFILE_NOT_READY_FOR_CANDIDATES", "profile", "BLOCK", "客户画像核心条件不足，必须继续访谈后才能匹配商机。"),),
            required_next_facts=(),
            profile_gate=profile_gate,
        )

    verification = _text(opportunity.get("verification_status"))
    coverage = _text(opportunity.get("coverage_status"))
    if verification not in ALLOWED_VERIFICATION:
        return OpportunityMatchResult(
            status="FACT_BLOCKED",
            recommendation_mode="NO_RECOMMENDATION",
            personalized_recommendation_allowed=False,
            candidate_opportunity_allowed=False,
            model_explanation_allowed=False,
            reasons=(MatchReason("OPPORTUNITY_NOT_VERIFIED", "opportunity.verification_status", "BLOCK", "商机事实尚未 VERIFIED，不能进入客户匹配。"),),
            required_next_facts=("opportunity.verification_status",),
            profile_gate=profile_gate,
        )
    if coverage in {"DEGRADED", "UNKNOWN"}:
        return OpportunityMatchResult(
            status="FACT_BLOCKED",
            recommendation_mode="NO_RECOMMENDATION",
            personalized_recommendation_allowed=False,
            candidate_opportunity_allowed=False,
            model_explanation_allowed=False,
            reasons=(MatchReason("SOURCE_COVERAGE_NOT_RELIABLE", "opportunity.coverage_status", "BLOCK", "当前来源覆盖状态不足以支持正式商机匹配。"),),
            required_next_facts=("opportunity.coverage_status",),
            profile_gate=profile_gate,
        )

    reasons: list[MatchReason] = []
    required_next_facts: list[str] = []

    exclusion = _is_excluded(profile, opportunity)
    if exclusion is not None:
        return OpportunityMatchResult(
            status="REJECTED",
            recommendation_mode="NO_RECOMMENDATION",
            personalized_recommendation_allowed=False,
            candidate_opportunity_allowed=False,
            model_explanation_allowed=False,
            reasons=(exclusion,),
            required_next_facts=(),
            profile_gate=profile_gate,
        )

    checks = [
        _profile_region_match(profile, opportunity),
        _customer_type_match(profile, opportunity),
        (*_stage_match(profile, opportunity), None),
        _amount_match(profile, opportunity),
        _product_match(profile, opportunity),
        _rental_match(profile, opportunity),
    ]

    for status, reason, required_fact in checks:
        if reason is not None:
            reasons.append(reason)
        if required_fact and required_fact not in required_next_facts:
            required_next_facts.append(required_fact)
        if status in {"REJECTED", "PROFILE_ERROR"}:
            return OpportunityMatchResult(
                status="REJECTED" if status == "REJECTED" else "PROFILE_BLOCKED",
                recommendation_mode="NO_RECOMMENDATION",
                personalized_recommendation_allowed=False,
                candidate_opportunity_allowed=False,
                model_explanation_allowed=False,
                reasons=tuple(reasons),
                required_next_facts=tuple(required_next_facts),
                profile_gate=profile_gate,
            )

    if required_next_facts:
        return OpportunityMatchResult(
            status="NEEDS_MORE_FACTS",
            recommendation_mode="FACT_ENRICHMENT_REQUIRED",
            personalized_recommendation_allowed=False,
            candidate_opportunity_allowed=True,
            model_explanation_allowed=False,
            reasons=tuple(reasons),
            required_next_facts=tuple(required_next_facts),
            profile_gate=profile_gate,
        )

    personalized = profile_gate.personalized_recommendation_allowed
    return OpportunityMatchResult(
        status="MATCHED_PERSONALIZED" if personalized else "MATCHED_CANDIDATE",
        recommendation_mode="PERSONALIZED_RECOMMENDATION" if personalized else "CANDIDATE_ONLY",
        personalized_recommendation_allowed=personalized,
        candidate_opportunity_allowed=True,
        model_explanation_allowed=True,
        reasons=tuple(reasons),
        required_next_facts=(),
        profile_gate=profile_gate,
    )
