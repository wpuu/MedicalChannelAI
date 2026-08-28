from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .collector_core import SCHEMA_VERSION, normalize_space
from .opportunity_match_gate import OpportunityMatchResult


class PriorityScoreError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


RELATIONSHIP_POINTS = {
    "STRONG": 25,
    "MEDIUM": 18,
    "HISTORICAL": 12,
    "WEAK": 8,
    "UNKNOWN": 0,
}

STAGE_POINTS = {
    "MARKET_RESEARCH": 25,
    "PROCUREMENT_INTENT": 23,
    "PREPARING": 20,
    "TENDERING": 15,
    "AMENDED": 10,
    "BID_CLOSED": 3,
    "AWARDED": 5,
}

CAPABILITY_POINTS = {
    "DIRECT_AUTHORIZED": 30,
    "DIRECT_UNCONFIRMED": 25,
    "RENTAL_CAPABLE": 25,
    "CAN_SOURCE_PARTNER": 18,
    "SERVICE_ONLY": 12,
}


@dataclass(frozen=True)
class ScoreComponent:
    code: str
    points: int
    max_points: int
    basis: str
    profile_paths: tuple[str, ...] = ()
    opportunity_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "points": self.points,
            "max_points": self.max_points,
            "basis": self.basis,
            "profile_paths": list(self.profile_paths),
            "opportunity_paths": list(self.opportunity_paths),
        }


@dataclass(frozen=True)
class PriorityScore:
    score: int
    score_type: str
    components: tuple[ScoreComponent, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "score": self.score,
            "score_type": self.score_type,
            "components": [component.as_dict() for component in self.components],
            "warnings": list(self.warnings),
            "interpretation": "BUSINESS_PRIORITY_NOT_WIN_PROBABILITY",
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


def _relationship_component(profile: dict[str, Any], opportunity: dict[str, Any]) -> tuple[ScoreComponent, str | None]:
    hospital = _text(opportunity.get("hospital_name"))
    if not hospital:
        return ScoreComponent("RELATIONSHIP", 0, 25, "医院身份或关系记录不足，未加关系分。"), "RELATIONSHIP_UNKNOWN"

    best_strength = "UNKNOWN"
    for relationship in profile.get("hospital_relationships") or []:
        if not isinstance(relationship, dict) or relationship.get("confirmed_by_customer") is not True:
            continue
        if _text(relationship.get("hospital_name")) != hospital:
            continue
        strength = relationship.get("relationship_strength")
        if RELATIONSHIP_POINTS.get(strength, 0) > RELATIONSHIP_POINTS.get(best_strength, 0):
            best_strength = strength

    points = RELATIONSHIP_POINTS.get(best_strength, 0)
    warning = None if points else "RELATIONSHIP_UNKNOWN"
    return (
        ScoreComponent(
            "RELATIONSHIP",
            points,
            25,
            f"客户确认的医院关系强度：{best_strength}。" if points else "没有客户确认的该院关系，关系维度记0分。",
            profile_paths=("hospital_relationships",),
            opportunity_paths=("hospital_name",),
        ),
        warning,
    )


def _capability_component(profile: dict[str, Any], opportunity: dict[str, Any]) -> ScoreComponent:
    labels = {_norm(item) for item in opportunity.get("product_labels") or [] if _text(item)}
    best_type = None
    best_points = -1
    best_index = None
    partnering = profile.get("partnering_policy") if isinstance(profile.get("partnering_policy"), dict) else {}

    for index, capability in enumerate(profile.get("product_capabilities") or []):
        if not isinstance(capability, dict):
            continue
        keys = {_norm(capability.get("category")), _norm(capability.get("subcategory"))}
        keys.discard("")
        if not keys.intersection(labels):
            continue
        capability_type = capability.get("capability_type")
        if capability_type == "CAN_SOURCE_PARTNER" and partnering.get("can_seek_temporary_manufacturer") is not True:
            continue
        points = CAPABILITY_POINTS.get(capability_type, 0)
        if points > best_points:
            best_type = capability_type
            best_points = points
            best_index = index

    if best_type is None:
        raise PriorityScoreError("MATCHED_WITHOUT_PRODUCT_CAPABILITY", "matched opportunity has no scoreable product capability")
    return ScoreComponent(
        "PRODUCT_EXECUTION_CAPABILITY",
        best_points,
        30,
        f"已确认产品参与能力：{best_type}。",
        profile_paths=(f"product_capabilities[{best_index}]",),
        opportunity_paths=("product_labels",),
    )


def _stage_component(opportunity: dict[str, Any]) -> ScoreComponent:
    stage = _text(opportunity.get("lifecycle_state"))
    if stage not in STAGE_POINTS:
        raise PriorityScoreError("STAGE_NOT_SCOREABLE", stage)
    return ScoreComponent(
        "INTERVENTION_STAGE",
        STAGE_POINTS[stage],
        25,
        f"当前项目阶段：{stage}；越早期通常越有渠道介入空间，但该分数不是成功概率。",
        opportunity_paths=("lifecycle_state",),
    )


def _amount_component(profile: dict[str, Any], opportunity: dict[str, Any]) -> ScoreComponent:
    amount = _money(opportunity.get("budget"))
    thresholds = profile.get("opportunity_thresholds") if isinstance(profile.get("opportunity_thresholds"), dict) else {}
    minimum = _money(thresholds.get("minimum_project_amount_cny"))
    owner_attention = _money(thresholds.get("owner_attention_amount_cny"))
    if amount is None or minimum is None:
        raise PriorityScoreError("AMOUNT_NOT_SCOREABLE", "budget or minimum threshold missing")

    if owner_attention is not None and amount >= owner_attention:
        points = 20
        basis = "项目金额已达到客户设置的老板/重点关注金额。"
    elif minimum > 0 and amount >= minimum * Decimal("3"):
        points = 16
        basis = "项目金额至少为最低跟进门槛的3倍。"
    else:
        points = 10
        basis = "项目金额达到最低跟进门槛。"

    return ScoreComponent(
        "PROJECT_AMOUNT",
        points,
        20,
        basis,
        profile_paths=("opportunity_thresholds.minimum_project_amount_cny", "opportunity_thresholds.owner_attention_amount_cny"),
        opportunity_paths=("budget",),
    )


def calculate_priority_score(
    profile: dict[str, Any],
    opportunity: dict[str, Any],
    match_result: OpportunityMatchResult,
) -> PriorityScore:
    if match_result.status not in {"MATCHED_CANDIDATE", "MATCHED_PERSONALIZED"}:
        raise PriorityScoreError("MATCH_REQUIRED", "priority score requires a matched opportunity")

    relationship, relationship_warning = _relationship_component(profile, opportunity)
    components = (
        _capability_component(profile, opportunity),
        relationship,
        _stage_component(opportunity),
        _amount_component(profile, opportunity),
    )
    score = sum(component.points for component in components)
    warnings = tuple(item for item in (relationship_warning,) if item)
    return PriorityScore(
        score=score,
        score_type="PERSONALIZED_PRIORITY" if match_result.status == "MATCHED_PERSONALIZED" else "CANDIDATE_PRIORITY",
        components=components,
        warnings=warnings,
    )
