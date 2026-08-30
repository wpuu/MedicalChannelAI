from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .match_pipeline import evaluate_match_pipeline
from .model_decision_contract import ModelDecisionError, build_model_decision_input


class OutreachContractError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


EARLY_STAGES = {"MARKET_RESEARCH", "PROCUREMENT_INTENT", "PREPARING"}
FORMAL_STAGES = {"TENDERING", "AMENDED", "BID_CLOSED"}
AWARD_STAGES = {"AWARDED"}

QUESTION_TEXT = {
    "CONFIRM_SCOPE": "想先确认一下，目前公开需求范围是否还有需要补充确认的技术或配置要求？",
    "CONFIRM_TIMELINE": "也想确认一下后续沟通和材料准备的时间节点，我们好按贵方节奏配合。",
    "CONFIRM_CONTACT_WINDOW": "后续由哪位老师或哪个对接窗口沟通更合适？",
    "CONFIRM_NEXT_STEP": "如果方向匹配，下一步我们优先准备哪类资料最合适？",
    "CONFIRM_FUTURE_NEEDS": "这个项目之后，如果还有同类需求，通常更适合在哪个时间点提前沟通？",
}

STRATEGY_CODES = {
    "EARLY_REQUIREMENT_DISCOVERY",
    "FORMAL_TENDER_CLARIFICATION",
    "RELATIONSHIP_RECONNECT",
    "CAPABILITY_INTRODUCTION",
    "PARTNER_ENTRY_DISCUSSION",
    "POST_AWARD_FUTURE_NEEDS",
}

POSITIONING_CODES = {
    "NO_POSITIONING",
    "DIRECT_CONFIRMED_CAPABILITY",
    "PARTNERABLE_CAPABILITY",
    "RELATIONSHIP_CONTEXT",
}


@dataclass(frozen=True)
class OutreachModelInput:
    opportunity_id: str
    lifecycle_state: str
    grounded_facts: tuple[dict[str, str], ...]
    confirmed_profile_context: dict[str, Any]
    allowed_strategy_codes: tuple[str, ...]
    allowed_question_codes: tuple[str, ...]
    allowed_positioning_codes: tuple[str, ...]
    allowed_profile_paths: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "task_type": "GROUNDED_OUTREACH_STRATEGY",
            "opportunity_id": self.opportunity_id,
            "lifecycle_state": self.lifecycle_state,
            "grounded_facts": [dict(item) for item in self.grounded_facts],
            "confirmed_profile_context": self.confirmed_profile_context,
            "allowed_strategy_codes": list(self.allowed_strategy_codes),
            "allowed_question_codes": list(self.allowed_question_codes),
            "allowed_positioning_codes": list(self.allowed_positioning_codes),
            "allowed_profile_paths": list(self.allowed_profile_paths),
            "instruction": (
                "Select only supplied codes and references. Do not write sales prose and do not create, infer, "
                "complete or guess procurement facts. Final customer-visible wording is rendered outside the model."
            ),
        }


def outreach_input_sha256(model_input: dict[str, Any]) -> str:
    raw = json.dumps(
        model_input,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _matching_capabilities(profile: dict[str, Any], opportunity: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {item for item in opportunity.get("product_labels") or [] if isinstance(item, str) and item}
    result: list[dict[str, Any]] = []
    for capability in profile.get("product_capabilities") or []:
        if not isinstance(capability, dict):
            continue
        taxonomy_ids = {
            item for item in capability.get("taxonomy_ids") or [] if isinstance(item, str) and item
        }
        if not labels.intersection(taxonomy_ids):
            continue
        result.append(
            {
                "category": capability.get("category"),
                "subcategory": capability.get("subcategory"),
                "brands": list(capability.get("brands") or []),
                "capability_type": capability.get("capability_type"),
            }
        )
    return result


def _confirmed_relationship(profile: dict[str, Any], hospital_name: str | None) -> dict[str, Any] | None:
    if not isinstance(hospital_name, str) or not hospital_name.strip():
        return None
    for row in profile.get("hospital_relationships") or []:
        if not isinstance(row, dict) or row.get("confirmed_by_customer") is not True:
            continue
        if row.get("hospital_name") != hospital_name:
            continue
        return {
            "hospital_name": hospital_name,
            "department": row.get("department"),
            "relationship_strength": row.get("relationship_strength"),
            "owner": row.get("owner"),
            "confirmed_by_customer": True,
        }
    return None


def _stage_codes(stage: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if stage in EARLY_STAGES:
        return (
            ("EARLY_REQUIREMENT_DISCOVERY", "RELATIONSHIP_RECONNECT", "CAPABILITY_INTRODUCTION", "PARTNER_ENTRY_DISCUSSION"),
            ("CONFIRM_SCOPE", "CONFIRM_TIMELINE", "CONFIRM_CONTACT_WINDOW", "CONFIRM_NEXT_STEP"),
        )
    if stage in FORMAL_STAGES:
        return (
            ("FORMAL_TENDER_CLARIFICATION", "RELATIONSHIP_RECONNECT", "CAPABILITY_INTRODUCTION", "PARTNER_ENTRY_DISCUSSION"),
            ("CONFIRM_SCOPE", "CONFIRM_TIMELINE", "CONFIRM_CONTACT_WINDOW", "CONFIRM_NEXT_STEP"),
        )
    if stage in AWARD_STAGES:
        return (
            ("POST_AWARD_FUTURE_NEEDS", "RELATIONSHIP_RECONNECT"),
            ("CONFIRM_CONTACT_WINDOW", "CONFIRM_FUTURE_NEEDS"),
        )
    raise OutreachContractError("OUTREACH_STAGE_NOT_SUPPORTED", f"unsupported outreach lifecycle stage: {stage}")


def build_outreach_model_input(
    *,
    profile: dict[str, Any],
    opportunity: dict[str, Any],
    evidence_facts: list[dict[str, Any]],
) -> OutreachModelInput:
    match = evaluate_match_pipeline(profile, opportunity)
    if not match.model_explanation_allowed or match.status not in {"MATCHED_CANDIDATE", "MATCHED_PERSONALIZED"}:
        raise OutreachContractError("OUTREACH_NOT_ELIGIBLE", f"match status does not allow outreach: {match.status}")
    try:
        bounded = build_model_decision_input(
            profile=profile,
            opportunity=opportunity,
            match_result=match,
            evidence_facts=evidence_facts,
        )
    except ModelDecisionError as exc:
        raise OutreachContractError(exc.code, str(exc)) from exc

    facts = tuple(item.as_dict() for item in bounded.grounded_facts)
    fields = {item["field_name"] for item in facts}
    if "project_name" not in fields or "buyer_name" not in fields:
        raise OutreachContractError(
            "OUTREACH_CORE_FACTS_MISSING",
            "buyer_name and project_name must both be present as grounded verified facts",
        )

    stage = str(opportunity.get("lifecycle_state") or "")
    strategies, questions = _stage_codes(stage)
    relationship = _confirmed_relationship(profile, opportunity.get("hospital_name"))
    capabilities = _matching_capabilities(profile, opportunity)
    partnering = profile.get("partnering_policy") if isinstance(profile.get("partnering_policy"), dict) else {}

    positioning = ["NO_POSITIONING"]
    allowed_paths = ["business_role"]
    if relationship is not None:
        positioning.append("RELATIONSHIP_CONTEXT")
        allowed_paths.append("hospital_relationship")
    if any(item.get("capability_type") in {"DIRECT_AUTHORIZED", "DIRECT_UNCONFIRMED", "SERVICE_ONLY", "RENTAL_CAPABLE"} for item in capabilities):
        positioning.append("DIRECT_CONFIRMED_CAPABILITY")
        allowed_paths.append("matching_product_capabilities")
    if any(item.get("capability_type") == "CAN_SOURCE_PARTNER" for item in capabilities) and partnering.get("can_seek_temporary_manufacturer") is True:
        positioning.append("PARTNERABLE_CAPABILITY")
        allowed_paths.extend(["matching_product_capabilities", "partnering_policy"])

    context = {
        "business_role": profile.get("business_role"),
        "hospital_relationship": relationship,
        "matching_product_capabilities": capabilities,
        "partnering_policy": {
            "can_seek_temporary_manufacturer": partnering.get("can_seek_temporary_manufacturer"),
            "can_cooperate_with_channel_partner": partnering.get("can_cooperate_with_channel_partner"),
            "can_do_rental_projects": partnering.get("can_do_rental_projects"),
        },
    }
    return OutreachModelInput(
        opportunity_id=str(opportunity["opportunity_id"]),
        lifecycle_state=stage,
        grounded_facts=facts,
        confirmed_profile_context=context,
        allowed_strategy_codes=strategies,
        allowed_question_codes=questions,
        allowed_positioning_codes=tuple(dict.fromkeys(positioning)),
        allowed_profile_paths=tuple(dict.fromkeys(allowed_paths)),
    )


def validate_outreach_model_output(output: dict[str, Any], model_input: OutreachModelInput) -> dict[str, Any]:
    if not isinstance(output, dict) or output.get("schema_version") != "0.1":
        raise OutreachContractError("OUTREACH_OUTPUT_SCHEMA_INVALID", "outreach model output must be schema 0.1 object")
    if output.get("opportunity_id") != model_input.opportunity_id:
        raise OutreachContractError("OUTREACH_OPPORTUNITY_MISMATCH", "model changed opportunity identity")
    strategy = output.get("strategy_code")
    questions = output.get("question_codes")
    positioning = output.get("positioning_code")
    fact_ids = output.get("supporting_fact_ids")
    profile_paths = output.get("supporting_profile_paths")

    if strategy not in model_input.allowed_strategy_codes:
        raise OutreachContractError("OUTREACH_STRATEGY_NOT_ALLOWED", str(strategy))
    if positioning not in model_input.allowed_positioning_codes:
        raise OutreachContractError("OUTREACH_POSITIONING_NOT_ALLOWED", str(positioning))
    if not isinstance(questions, list) or not 1 <= len(questions) <= 3 or len(questions) != len(set(questions)):
        raise OutreachContractError("OUTREACH_QUESTIONS_INVALID", "question_codes must contain 1..3 unique values")
    if any(code not in model_input.allowed_question_codes for code in questions):
        raise OutreachContractError("OUTREACH_QUESTION_NOT_ALLOWED", "question code outside allowlist")
    if not isinstance(fact_ids, list) or not fact_ids or len(fact_ids) != len(set(fact_ids)):
        raise OutreachContractError("OUTREACH_FACT_REFERENCES_INVALID", "supporting_fact_ids must be non-empty unique list")
    allowed_fact_ids = {item["fact_id"] for item in model_input.grounded_facts}
    if any(item not in allowed_fact_ids for item in fact_ids):
        raise OutreachContractError("OUTREACH_UNGROUNDED_FACT_REFERENCE", "unknown supporting fact reference")
    core_fact_ids = {
        item["fact_id"]
        for item in model_input.grounded_facts
        if item["field_name"] in {"buyer_name", "project_name"}
    }
    if not core_fact_ids.issubset(set(fact_ids)):
        raise OutreachContractError("OUTREACH_CORE_FACT_REFERENCES_REQUIRED", "buyer/project fact ids must be cited")

    if not isinstance(profile_paths, list) or len(profile_paths) != len(set(profile_paths)):
        raise OutreachContractError("OUTREACH_PROFILE_REFERENCES_INVALID", "supporting_profile_paths must be unique list")
    if any(path not in model_input.allowed_profile_paths for path in profile_paths):
        raise OutreachContractError("OUTREACH_PROFILE_PATH_NOT_ALLOWED", "unknown profile path")
    required_profile_path = {
        "RELATIONSHIP_CONTEXT": "hospital_relationship",
        "DIRECT_CONFIRMED_CAPABILITY": "matching_product_capabilities",
        "PARTNERABLE_CAPABILITY": "matching_product_capabilities",
    }.get(str(positioning))
    if required_profile_path and required_profile_path not in profile_paths:
        raise OutreachContractError("OUTREACH_POSITIONING_REFERENCE_REQUIRED", required_profile_path)
    if positioning == "PARTNERABLE_CAPABILITY" and "partnering_policy" not in profile_paths:
        raise OutreachContractError("OUTREACH_POSITIONING_REFERENCE_REQUIRED", "partnering_policy")

    return {
        "schema_version": "0.1",
        "opportunity_id": model_input.opportunity_id,
        "strategy_code": strategy,
        "question_codes": list(questions),
        "positioning_code": positioning,
        "supporting_fact_ids": list(fact_ids),
        "supporting_profile_paths": list(profile_paths),
        "requires_human_confirmation": True,
    }


def _fact_value(model_input: OutreachModelInput, field_name: str) -> str:
    matches = [item["field_value"] for item in model_input.grounded_facts if item["field_name"] == field_name]
    if len(matches) != 1:
        raise OutreachContractError("OUTREACH_RENDER_FACT_MISSING", field_name)
    return matches[0]


def _first_capability(context: dict[str, Any], allowed_types: set[str]) -> dict[str, Any] | None:
    for item in context.get("matching_product_capabilities") or []:
        if isinstance(item, dict) and item.get("capability_type") in allowed_types:
            return item
    return None


def render_outreach_draft(
    validated: dict[str, Any],
    model_input: OutreachModelInput,
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    buyer = _fact_value(model_input, "buyer_name")
    project = _fact_value(model_input, "project_name")
    context = model_input.confirmed_profile_context
    strategy = validated["strategy_code"]
    positioning = validated["positioning_code"]

    lines = [
        "【内部沟通话术草稿】",
        "",
        "老师您好：",
        "",
        f"关注到{buyer}公开发布了「{project}」相关信息。",
    ]

    if strategy == "RELATIONSHIP_RECONNECT" and context.get("hospital_relationship"):
        lines.append("我们团队此前与贵院有过业务沟通基础，这次想先确认当前更合适的对接窗口。")
    elif strategy == "POST_AWARD_FUTURE_NEEDS":
        lines.append("这次主要想了解后续同类需求的沟通节奏，不影响当前已公开项目结果。")
    elif strategy == "FORMAL_TENDER_CLARIFICATION":
        lines.append("我们只基于已公开信息做前期判断，想先把公开范围和后续材料要求确认清楚。")
    else:
        lines.append("我们先按已公开信息做了初步梳理，希望把需求范围和后续沟通方式确认清楚。")

    if positioning == "DIRECT_CONFIRMED_CAPABILITY":
        capability = _first_capability(
            context,
            {"DIRECT_AUTHORIZED", "DIRECT_UNCONFIRMED", "SERVICE_ONLY", "RENTAL_CAPABLE"},
        )
        if capability is None:
            raise OutreachContractError("OUTREACH_RENDER_PROFILE_MISSING", "matching_product_capabilities")
        label = capability.get("subcategory") or capability.get("category")
        if isinstance(label, str) and label.strip():
            lines.append(f"我们在{label}方向有可参与的产品或服务能力，可以先按贵方公开要求确认适配范围。")
    elif positioning == "PARTNERABLE_CAPABILITY":
        capability = _first_capability(context, {"CAN_SOURCE_PARTNER"})
        if capability is None:
            raise OutreachContractError("OUTREACH_RENDER_PROFILE_MISSING", "partnerable capability")
        label = capability.get("subcategory") or capability.get("category")
        if isinstance(label, str) and label.strip():
            lines.append(f"在{label}方向，如需求匹配，我们可以协调厂家或合作渠道资源，再按贵方要求准备材料。")

    lines.append("")
    for code in validated["question_codes"]:
        lines.append(QUESTION_TEXT[code])
    lines.extend([
        "",
        "谢谢。",
        "",
        "——",
        "说明：以上为内部沟通草稿，仅根据已验证公开事实与客户自有资源生成，不是医院官方表述，也不代表中标概率或采购承诺。",
    ])
    return {
        "schema_version": "0.1",
        "opportunity_id": model_input.opportunity_id,
        "disclaimer": "按需生成 · 仅供内部沟通参考 · 不是官方事实或医院立场",
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "draft": "\n".join(lines),
        "strategy_code": validated["strategy_code"],
        "supporting_fact_ids": validated["supporting_fact_ids"],
        "supporting_profile_paths": validated["supporting_profile_paths"],
        "requires_human_confirmation": True,
    }
