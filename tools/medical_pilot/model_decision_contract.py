from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .collector_core import SCHEMA_VERSION, normalize_space
from .opportunity_match_gate import OpportunityMatchResult
from .query_budget import DEFAULT_MODEL_FACT_CHAR_LIMIT, DEFAULT_MODEL_FACT_LIMIT


class ModelDecisionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


ACTION_LABELS = {
    "CONTACT_HOSPITAL": "联系医院核实项目",
    "VERIFY_RELATIONSHIP": "先确认院内关系资源",
    "FIND_MANUFACTURER": "寻找可合作厂家",
    "CONTACT_CHANNEL_PARTNER": "联系合作渠道",
    "PREPARE_BID": "准备投标评估",
    "MONITOR": "继续监控项目变化",
    "NO_ACTION": "暂不投入销售资源",
}

REASON_LABELS = {
    "RELATIONSHIP_EXISTS": "已存在客户确认的医院关系",
    "RELATIONSHIP_UNKNOWN": "当前尚未确认医院关系",
    "PRODUCT_CAPABILITY_DIRECT": "客户已有可直接参与的产品能力",
    "PRODUCT_CAPABILITY_PARTNERABLE": "客户允许通过寻找厂家或渠道合作参与",
    "EARLY_STAGE": "项目仍处于较早介入阶段",
    "FORMAL_TENDER": "项目已进入正式采购阶段",
    "LARGE_PROJECT": "项目达到客户重点关注金额",
    "RENTAL_CAPABILITY_MATCH": "租赁项目与客户已确认能力匹配",
    "AWARD_INTELLIGENCE_ONLY": "当前主要价值是中标与竞争情报",
}

RISK_LABELS = {
    "ATTACHMENT_DETAILS_PENDING": "关键附件详情尚未完成真实字节验证",
    "COVERAGE_PARTIAL": "当前区域公开数据覆盖仍为 PARTIAL",
    "RELATIONSHIP_UNKNOWN": "医院关系尚未确认",
    "PRODUCT_CLASSIFICATION_MODEL_DERIVED": "产品分类来自受控模型派生而非官方原文字段",
    "DEADLINE_NEAR": "项目截止时间较近",
    "CROSS_STAGE_LINK_UNCONFIRMED": "跨阶段项目关联仍是候选，尚未形成确定性桥接",
}

EARLY_STAGES = {"MARKET_RESEARCH", "PROCUREMENT_INTENT", "PREPARING"}
FORMAL_STAGES = {"TENDERING", "AMENDED", "BID_CLOSED"}
AWARD_STAGES = {"AWARDED"}

# Deterministic importance only for context selection. It never changes a fact.
FACT_FIELD_PRIORITY = {
    "project_number": 0,
    "project_name": 1,
    "buyer_name": 2,
    "hospital_name": 3,
    "lifecycle_state": 4,
    "notice_type": 5,
    "published_at": 6,
    "published_date": 6,
    "budget_cny": 7,
    "budget_amount_cny": 7,
    "award_total_cny": 7,
    "bid_deadline": 8,
    "registration_deadline": 9,
    "termination_reason": 10,
    "supplier_name": 11,
    "raw_name": 12,
    "product_name": 12,
    "brand": 13,
    "model": 14,
    "quantity": 15,
    "unit_price_cny": 16,
}


@dataclass(frozen=True)
class GroundedFact:
    fact_id: str
    field_name: str
    field_value: str
    source_url: str

    def as_dict(self) -> dict:
        return {
            "fact_id": self.fact_id,
            "field_name": self.field_name,
            "field_value": self.field_value,
            "source_url": self.source_url,
        }


@dataclass(frozen=True)
class ModelDecisionInput:
    opportunity_id: str
    match_status: str
    recommendation_mode: str
    lifecycle_state: str
    allowed_action_types: tuple[str, ...]
    allowed_reason_codes: tuple[str, ...]
    allowed_risk_codes: tuple[str, ...]
    grounded_facts: tuple[GroundedFact, ...]
    confirmed_profile_context: dict[str, Any]
    grounded_fact_source_count: int
    grounded_fact_omitted_count: int
    grounded_fact_char_count: int
    max_grounded_facts: int
    max_grounded_fact_chars: int

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": self.opportunity_id,
            "match_status": self.match_status,
            "recommendation_mode": self.recommendation_mode,
            "lifecycle_state": self.lifecycle_state,
            "allowed_action_types": list(self.allowed_action_types),
            "allowed_reason_codes": list(self.allowed_reason_codes),
            "allowed_risk_codes": list(self.allowed_risk_codes),
            "grounded_facts": [fact.as_dict() for fact in self.grounded_facts],
            "confirmed_profile_context": self.confirmed_profile_context,
            "input_budget": {
                "source_verified_fact_count": self.grounded_fact_source_count,
                "included_fact_count": len(self.grounded_facts),
                "omitted_fact_count": self.grounded_fact_omitted_count,
                "included_fact_chars": self.grounded_fact_char_count,
                "max_facts": self.max_grounded_facts,
                "max_fact_chars": self.max_grounded_fact_chars,
            },
            "instruction": "Choose only from supplied enums and reference only supplied fact_ids/profile paths. Do not generate or infer new procurement facts. The input_budget may indicate that additional verified facts exist outside this bounded model context.",
        }


def _text(value: Any) -> str:
    return normalize_space(value) if isinstance(value, str) else ""


def _action_types(stage: str) -> tuple[str, ...]:
    if stage in EARLY_STAGES:
        return ("CONTACT_HOSPITAL", "VERIFY_RELATIONSHIP", "FIND_MANUFACTURER", "CONTACT_CHANNEL_PARTNER", "MONITOR", "NO_ACTION")
    if stage in FORMAL_STAGES:
        return ("PREPARE_BID", "VERIFY_RELATIONSHIP", "FIND_MANUFACTURER", "CONTACT_CHANNEL_PARTNER", "MONITOR", "NO_ACTION")
    if stage in AWARD_STAGES:
        return ("MONITOR", "NO_ACTION")
    raise ModelDecisionError("STAGE_NOT_SUPPORTED", f"unsupported lifecycle stage for model decision: {stage}")


def _valid_grounded_facts(facts: list[dict[str, Any]]) -> tuple[GroundedFact, ...]:
    result: list[GroundedFact] = []
    seen: set[str] = set()
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if fact.get("fact_type") != "OFFICIAL_PUBLIC_FACT":
            continue
        if fact.get("verification_status") != "VERIFIED":
            continue
        if fact.get("model_generated") is not False:
            continue
        fact_id = _text(fact.get("fact_id"))
        field_name = _text(fact.get("field_name"))
        field_value = _text(fact.get("field_value"))
        source_url = _text(fact.get("source_url"))
        if not fact_id or not field_name or not field_value or not source_url or fact_id in seen:
            continue
        seen.add(fact_id)
        result.append(GroundedFact(fact_id, field_name, field_value, source_url))
    return tuple(result)


def _fact_cost(fact: GroundedFact) -> int:
    return len(fact.field_name) + len(fact.field_value) + len(fact.source_url)


def _bounded_grounded_facts(
    facts: list[dict[str, Any]],
    *,
    max_facts: int = DEFAULT_MODEL_FACT_LIMIT,
    max_chars: int = DEFAULT_MODEL_FACT_CHAR_LIMIT,
) -> tuple[tuple[GroundedFact, ...], int, int, int]:
    valid = list(_valid_grounded_facts(facts))
    valid.sort(key=lambda item: (FACT_FIELD_PRIORITY.get(item.field_name, 100), item.fact_id))

    selected: list[GroundedFact] = []
    char_count = 0
    for fact in valid:
        if len(selected) >= max_facts:
            break
        cost = _fact_cost(fact)
        if cost > max_chars:
            continue
        if char_count + cost > max_chars:
            continue
        selected.append(fact)
        char_count += cost

    return tuple(selected), len(valid), len(valid) - len(selected), char_count


def _confirmed_hospital_relationship(profile: dict[str, Any], hospital_name: str | None) -> dict[str, Any] | None:
    target = _text(hospital_name)
    if not target:
        return None
    for relationship in profile.get("hospital_relationships") or []:
        if not isinstance(relationship, dict):
            continue
        if relationship.get("confirmed_by_customer") is not True:
            continue
        if _text(relationship.get("hospital_name")) != target:
            continue
        return {
            "hospital_name": target,
            "department": relationship.get("department"),
            "relationship_strength": relationship.get("relationship_strength"),
            "owner": relationship.get("owner"),
            "confirmed_by_customer": True,
        }
    return None


def build_model_decision_input(
    *,
    profile: dict[str, Any],
    opportunity: dict[str, Any],
    match_result: OpportunityMatchResult,
    evidence_facts: list[dict[str, Any]],
    max_grounded_facts: int = DEFAULT_MODEL_FACT_LIMIT,
    max_grounded_fact_chars: int = DEFAULT_MODEL_FACT_CHAR_LIMIT,
) -> ModelDecisionInput:
    if not match_result.model_explanation_allowed:
        raise ModelDecisionError("MODEL_NOT_ALLOWED", "opportunity did not pass the deterministic match gate")
    if match_result.status not in {"MATCHED_CANDIDATE", "MATCHED_PERSONALIZED"}:
        raise ModelDecisionError("MATCH_STATUS_NOT_ALLOWED", match_result.status)
    if max_grounded_facts < 1 or max_grounded_fact_chars < 1:
        raise ModelDecisionError("MODEL_FACT_BUDGET_INVALID", "model fact budgets must be positive")

    opportunity_id = _text(opportunity.get("opportunity_id"))
    stage = _text(opportunity.get("lifecycle_state"))
    facts, valid_count, omitted_count, fact_chars = _bounded_grounded_facts(
        evidence_facts,
        max_facts=max_grounded_facts,
        max_chars=max_grounded_fact_chars,
    )
    if not opportunity_id:
        raise ModelDecisionError("OPPORTUNITY_ID_MISSING", "opportunity_id is required")
    if not facts:
        if valid_count:
            raise ModelDecisionError("MODEL_FACT_BUDGET_NO_FIT", "verified facts exist but none fit the bounded model context")
        raise ModelDecisionError("NO_GROUNDED_FACTS", "at least one VERIFIED non-model official fact is required")

    hospital_name = _text(opportunity.get("hospital_name")) or None
    relationship = _confirmed_hospital_relationship(profile, hospital_name)
    context = {
        "business_role": profile.get("business_role"),
        "partnering_policy": profile.get("partnering_policy"),
        "opportunity_thresholds": profile.get("opportunity_thresholds"),
        "product_capabilities": profile.get("product_capabilities"),
        "hospital_relationship": relationship,
        "profile_status": match_result.profile_gate.computed_status,
    }

    return ModelDecisionInput(
        opportunity_id=opportunity_id,
        match_status=match_result.status,
        recommendation_mode=match_result.recommendation_mode,
        lifecycle_state=stage,
        allowed_action_types=_action_types(stage),
        allowed_reason_codes=tuple(REASON_LABELS),
        allowed_risk_codes=tuple(RISK_LABELS),
        grounded_facts=facts,
        confirmed_profile_context=context,
        grounded_fact_source_count=valid_count,
        grounded_fact_omitted_count=omitted_count,
        grounded_fact_char_count=fact_chars,
        max_grounded_facts=max_grounded_facts,
        max_grounded_fact_chars=max_grounded_fact_chars,
    )


def validate_model_decision(output: dict[str, Any], model_input: ModelDecisionInput) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise ModelDecisionError("OUTPUT_NOT_OBJECT", "model output must be a JSON object")
    if output.get("schema_version") != SCHEMA_VERSION:
        raise ModelDecisionError("OUTPUT_SCHEMA_VERSION_INVALID", "schema_version must be 0.1")
    if output.get("opportunity_id") != model_input.opportunity_id:
        raise ModelDecisionError("OUTPUT_OPPORTUNITY_ID_MISMATCH", "model output opportunity_id changed")

    action = output.get("action_type")
    if action not in model_input.allowed_action_types:
        raise ModelDecisionError("ACTION_NOT_ALLOWED", f"action_type not allowed: {action}")

    reason_codes = output.get("reason_codes")
    risk_codes = output.get("risk_codes")
    fact_ids = output.get("supporting_fact_ids")
    profile_paths = output.get("supporting_profile_paths")
    if not isinstance(reason_codes, list) or not reason_codes:
        raise ModelDecisionError("REASON_CODES_REQUIRED", "at least one reason code is required")
    if not isinstance(risk_codes, list):
        raise ModelDecisionError("RISK_CODES_INVALID", "risk_codes must be an array")
    if not isinstance(fact_ids, list) or not fact_ids:
        raise ModelDecisionError("SUPPORTING_FACT_IDS_REQUIRED", "at least one grounded fact reference is required")
    if not isinstance(profile_paths, list):
        raise ModelDecisionError("PROFILE_PATHS_INVALID", "supporting_profile_paths must be an array")

    if any(code not in model_input.allowed_reason_codes for code in reason_codes):
        raise ModelDecisionError("REASON_CODE_NOT_ALLOWED", "model emitted a reason code outside the allowlist")
    if any(code not in model_input.allowed_risk_codes for code in risk_codes):
        raise ModelDecisionError("RISK_CODE_NOT_ALLOWED", "model emitted a risk code outside the allowlist")

    allowed_fact_ids = {fact.fact_id for fact in model_input.grounded_facts}
    if any(fact_id not in allowed_fact_ids for fact_id in fact_ids):
        raise ModelDecisionError("UNGROUNDED_FACT_REFERENCE", "model referenced a fact_id not present in grounded input")

    allowed_profile_prefixes = {
        "business_role",
        "partnering_policy",
        "opportunity_thresholds",
        "product_capabilities",
        "hospital_relationship",
        "profile_status",
    }
    for path in profile_paths:
        if not isinstance(path, str) or path.split(".", 1)[0] not in allowed_profile_prefixes:
            raise ModelDecisionError("PROFILE_PATH_NOT_ALLOWED", f"unsupported profile path: {path}")

    return {
        "schema_version": SCHEMA_VERSION,
        "opportunity_id": model_input.opportunity_id,
        "action_type": action,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "risk_codes": list(dict.fromkeys(risk_codes)),
        "supporting_fact_ids": list(dict.fromkeys(fact_ids)),
        "supporting_profile_paths": list(dict.fromkeys(profile_paths)),
        "requires_human_confirmation": bool(output.get("requires_human_confirmation", True)),
    }


def render_model_decision(validated_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": ACTION_LABELS[validated_output["action_type"]],
        "reasons": [REASON_LABELS[code] for code in validated_output["reason_codes"]],
        "risks": [RISK_LABELS[code] for code in validated_output["risk_codes"]],
        "supporting_fact_ids": validated_output["supporting_fact_ids"],
        "supporting_profile_paths": validated_output["supporting_profile_paths"],
        "requires_human_confirmation": validated_output["requires_human_confirmation"],
    }
