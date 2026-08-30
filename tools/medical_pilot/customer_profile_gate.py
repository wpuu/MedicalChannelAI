from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .collector_core import SCHEMA_VERSION, normalize_space


BROAD_PRODUCT_CATEGORIES = {
    "医疗器械",
    "医疗设备",
    "ivd",
    "体外诊断",
    "检验",
    "耗材",
    "医疗耗材",
    "设备",
}

CONFIRMATION_QUESTIONS = {
    "REGION_SCOPE_NOT_CONFIRMED": "为了避免把不在经营范围内的项目推给你，请确认：你在这些城市是全市都做，还是只做指定区县？",
    "CUSTOMER_TYPES_NOT_CONFIRMED": "请确认你实际会做哪些客户类型：三甲、二级、基层、民营、疾控、血站、高校科研或第三方检验？没有列出的是否都不做？",
    "PRODUCT_CAPABILITIES_NOT_CONFIRMED": "请确认目前真正能销售、代理、租赁、服务或临时寻找厂家合作的产品范围；我不会把未确认的产品当成你能做。",
    "PARTNERING_POLICY_NOT_CONFIRMED": "如果发现你没有现成代理权的好项目，你是否愿意临时找厂家或联合其他渠道？另外，设备租赁项目是否接受？",
    "OPPORTUNITY_PREFERENCES_NOT_CONFIRMED": "请确认最低多大金额的项目值得跟，以及你希望关注市场调研、采购意向、正式招标、中标后的哪些阶段？",
    "EXCLUSION_RULES_NOT_CONFIRMED": "请确认有没有明确不做的产品、医院类型、区域或项目阶段；如果没有，也请明确回答“没有排除项”。",
}


@dataclass(frozen=True)
class MissingCondition:
    code: str
    field_path: str
    severity: str
    question: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "field_path": self.field_path,
            "severity": self.severity,
            "question": self.question,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProfileGateResult:
    computed_status: str
    profile_completeness: int
    recommendation_mode: str
    personalized_recommendation_allowed: bool
    candidate_opportunity_allowed: bool
    missing_conditions: tuple[MissingCondition, ...]
    next_question: str | None
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "computed_status": self.computed_status,
            "profile_completeness": self.profile_completeness,
            "recommendation_mode": self.recommendation_mode,
            "personalized_recommendation_allowed": self.personalized_recommendation_allowed,
            "candidate_opportunity_allowed": self.candidate_opportunity_allowed,
            "missing_required_conditions": [item.as_dict() for item in self.missing_conditions],
            "next_question": self.next_question,
            "warnings": list(self.warnings),
        }


def _text(value: Any) -> str:
    return normalize_space(value) if isinstance(value, str) else ""


def _nonempty_list(value: Any) -> list:
    return value if isinstance(value, list) and value else []


def _money(value: Any) -> Decimal | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def _add(
    missing: list[MissingCondition],
    *,
    code: str,
    path: str,
    question: str,
    reason: str,
    severity: str = "BLOCK_PERSONALIZED",
) -> None:
    if any(item.code == code and item.field_path == path for item in missing):
        return
    missing.append(
        MissingCondition(
            code=code,
            field_path=path,
            severity=severity,
            question=question,
            reason=reason,
        )
    )


def _check_regions(profile: dict[str, Any], missing: list[MissingCondition]) -> bool:
    regions = _nonempty_list(profile.get("operating_regions"))
    if not regions:
        _add(
            missing,
            code="OPERATING_REGIONS_MISSING",
            path="operating_regions",
            question="你实际经营哪些省、市？如果先做天津，请确认是否覆盖天津全市。",
            reason="没有区域边界时，系统无法判断哪些公开商机属于客户可经营范围。",
            severity="BLOCK_CANDIDATES",
        )
        return False

    valid = True
    for index, region in enumerate(regions):
        if not isinstance(region, dict) or not _text(region.get("province")) or not _text(region.get("city")):
            valid = False
            _add(
                missing,
                code="OPERATING_REGION_INVALID",
                path=f"operating_regions[{index}]",
                question="请补充这个经营区域的省和城市。",
                reason="区域记录缺少省或城市。",
                severity="BLOCK_CANDIDATES",
            )
            continue
        scope_mode = region.get("scope_mode")
        districts = region.get("districts") if isinstance(region.get("districts"), list) else []
        if scope_mode not in {"ENTIRE_CITY", "SELECTED_DISTRICTS"}:
            valid = False
            _add(
                missing,
                code="REGION_SCOPE_MODE_MISSING",
                path=f"operating_regions[{index}].scope_mode",
                question=f"{_text(region.get('city'))}是全市都做，还是只做指定区县？",
                reason="城市经营范围没有明确到全市或指定区县。",
            )
        elif scope_mode == "SELECTED_DISTRICTS" and not districts:
            valid = False
            _add(
                missing,
                code="REGION_DISTRICTS_MISSING",
                path=f"operating_regions[{index}].districts",
                question=f"请列出你在{_text(region.get('city'))}实际会做的区县。",
                reason="选择了指定区县模式但没有列出区县。",
            )
        elif scope_mode == "ENTIRE_CITY" and districts:
            valid = False
            _add(
                missing,
                code="REGION_SCOPE_CONFLICT",
                path=f"operating_regions[{index}]",
                question=f"你在{_text(region.get('city'))}到底是全市都做，还是只做这些区县？请二选一确认。",
                reason="全市模式和指定区县列表同时存在，经营范围互相冲突。",
            )
    return valid


def _check_products(profile: dict[str, Any], missing: list[MissingCondition]) -> bool:
    products = _nonempty_list(profile.get("product_capabilities"))
    if not products:
        _add(
            missing,
            code="PRODUCT_CAPABILITIES_MISSING",
            path="product_capabilities",
            question="你目前真正能做哪些产品？请至少具体到生化、发光、凝血、血球、尿液、分子、流水线、影像设备、普通设备或具体耗材类别。",
            reason="没有产品能力就无法判断公开项目是否可做。",
            severity="BLOCK_CANDIDATES",
        )
        return False

    valid = True
    for index, item in enumerate(products):
        if not isinstance(item, dict):
            valid = False
            _add(
                missing,
                code="PRODUCT_CAPABILITY_INVALID",
                path=f"product_capabilities[{index}]",
                question="请重新确认这条产品能力，至少填写产品类别和你能以什么方式参与。",
                reason="产品能力记录格式无效。",
            )
            continue
        category = _text(item.get("category"))
        subcategory = _text(item.get("subcategory"))
        capability = item.get("capability_type")
        brands = item.get("brands") if isinstance(item.get("brands"), list) else []
        if not category:
            valid = False
            _add(
                missing,
                code="PRODUCT_CATEGORY_MISSING",
                path=f"product_capabilities[{index}].category",
                question="这条产品能力具体是什么类别？",
                reason="产品类别为空。",
            )
        if category.lower() in BROAD_PRODUCT_CATEGORIES and not subcategory:
            valid = False
            _add(
                missing,
                code="PRODUCT_SCOPE_TOO_BROAD",
                path=f"product_capabilities[{index}].subcategory",
                question=f"“{category}”范围太大，请继续说明具体做哪些细分类别。",
                reason="过宽的产品类别会造成大量不相关商机和错误推荐。",
            )
        if capability in {None, "UNKNOWN"}:
            valid = False
            _add(
                missing,
                code="PRODUCT_CAPABILITY_TYPE_UNKNOWN",
                path=f"product_capabilities[{index}].capability_type",
                question=f"对于“{subcategory or category}”，你是已有授权、能直接销售、能临时找厂家、只做服务，还是能做租赁？",
                reason="产品存在但参与方式未知，无法判断项目可执行性。",
            )
        if capability == "DIRECT_AUTHORIZED" and not brands:
            valid = False
            _add(
                missing,
                code="AUTHORIZED_BRANDS_MISSING",
                path=f"product_capabilities[{index}].brands",
                question=f"“{subcategory or category}”如果是现有授权，请列出当前可用品牌；如果不限制品牌，请把能力类型改成可寻找合作厂家。",
                reason="声称直接授权但未给品牌范围，可能把无法供货的品牌项目误判为可做。",
            )
    return valid


def evaluate_customer_profile(profile: dict[str, Any]) -> ProfileGateResult:
    missing: list[MissingCondition] = []
    warnings: list[str] = []

    if not _text(profile.get("company_name")):
        _add(
            missing,
            code="COMPANY_NAME_MISSING",
            path="company_name",
            question="公司或团队名称是什么？",
            reason="需要明确当前经营画像属于哪个客户主体。",
            severity="BLOCK_CANDIDATES",
        )
    if profile.get("business_role") not in {
        "LOCAL_DISTRIBUTOR",
        "REGIONAL_DISTRIBUTOR",
        "MANUFACTURER_SALES",
        "MANUFACTURER_CHANNEL_MANAGER",
        "OTHER",
    }:
        _add(
            missing,
            code="BUSINESS_ROLE_MISSING",
            path="business_role",
            question="你当前是本地经销商、区域经销商、厂家一线销售，还是厂家渠道负责人？",
            reason="渠道商与厂家销售的商机判断、合作方式和行动建议不同。",
            severity="BLOCK_CANDIDATES",
        )

    region_valid = _check_regions(profile, missing)

    customer_types = _nonempty_list(profile.get("customer_types"))
    if not customer_types:
        _add(
            missing,
            code="CUSTOMER_TYPES_MISSING",
            path="customer_types",
            question="你实际会做哪些客户：三甲、二级、基层、民营、疾控、血站、高校科研还是第三方检验？",
            reason="没有客户类型范围会把不可能成交的机构也推给用户。",
            severity="BLOCK_CANDIDATES",
        )

    product_valid = _check_products(profile, missing)

    partnering = profile.get("partnering_policy")
    if not isinstance(partnering, dict):
        _add(
            missing,
            code="PARTNERING_POLICY_MISSING",
            path="partnering_policy",
            question=CONFIRMATION_QUESTIONS["PARTNERING_POLICY_NOT_CONFIRMED"],
            reason="没有合作策略就无法判断非现成代理项目或租赁项目是否可做。",
        )
    else:
        for key, question in (
            ("can_seek_temporary_manufacturer", "发现好项目但没有现成厂家时，你愿不愿意临时找厂家合作？"),
            ("can_cooperate_with_channel_partner", "你是否接受和其他渠道商联合参与项目？"),
            ("can_do_rental_projects", "设备租赁或租赁服务类项目你做不做？"),
        ):
            if not isinstance(partnering.get(key), bool):
                _add(
                    missing,
                    code=f"{key.upper()}_MISSING",
                    path=f"partnering_policy.{key}",
                    question=question,
                    reason="该合作条件会直接改变商机是否可执行。",
                )

    thresholds = profile.get("opportunity_thresholds")
    if not isinstance(thresholds, dict):
        _add(
            missing,
            code="OPPORTUNITY_THRESHOLDS_MISSING",
            path="opportunity_thresholds",
            question="最低多大金额的项目值得团队跟进？你希望优先看哪些阶段？",
            reason="没有金额和阶段偏好，系统无法控制商机噪声。",
        )
    else:
        if _money(thresholds.get("minimum_project_amount_cny")) is None:
            _add(
                missing,
                code="MINIMUM_PROJECT_AMOUNT_MISSING",
                path="opportunity_thresholds.minimum_project_amount_cny",
                question="最低多少金额的项目才值得你们跟？例如10万、50万或100万以上。",
                reason="项目金额门槛未知会产生大量用户根本不会跟进的项目。",
            )
        if not _nonempty_list(thresholds.get("preferred_stages")):
            _add(
                missing,
                code="PREFERRED_STAGES_MISSING",
                path="opportunity_thresholds.preferred_stages",
                question="你最想在哪些阶段得到提醒：市场调研、采购意向、正式招标、中标结果？可以多选。",
                reason="不同客户介入项目的最佳阶段不同。",
            )

    confirmation_flags = profile.get("confirmation_flags")
    for code, field in (
        ("REGION_SCOPE_NOT_CONFIRMED", "region_scope_confirmed"),
        ("CUSTOMER_TYPES_NOT_CONFIRMED", "customer_types_confirmed"),
        ("PRODUCT_CAPABILITIES_NOT_CONFIRMED", "product_capabilities_confirmed"),
        ("PARTNERING_POLICY_NOT_CONFIRMED", "partnering_policy_confirmed"),
        ("OPPORTUNITY_PREFERENCES_NOT_CONFIRMED", "opportunity_preferences_confirmed"),
        ("EXCLUSION_RULES_NOT_CONFIRMED", "exclusion_rules_confirmed"),
    ):
        confirmed = isinstance(confirmation_flags, dict) and confirmation_flags.get(field) is True
        if not confirmed:
            _add(
                missing,
                code=code,
                path=f"confirmation_flags.{field}",
                question=CONFIRMATION_QUESTIONS[code],
                reason="系统必须区分‘用户明确确认’和‘字段暂时为空/默认值’，不能把默认值当真实经营条件。",
            )

    # Candidate mode needs only a defensible area + customer type + product scope.
    candidate_blockers = [item for item in missing if item.severity == "BLOCK_CANDIDATES"]
    candidate_allowed = not candidate_blockers and region_valid and product_valid and bool(customer_types)

    personalized_allowed = candidate_allowed and not missing
    if personalized_allowed:
        status = "SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION"
        mode = "PERSONALIZED_RECOMMENDATION"
    elif candidate_allowed:
        status = "SUFFICIENT_FOR_CANDIDATES"
        mode = "CANDIDATE_ONLY"
    else:
        status = "INCOMPLETE"
        mode = "PROFILE_INTERVIEW_REQUIRED"

    # Weighted toward scope facts that directly control filtering. Confirmation
    # flags matter, but cannot make an otherwise empty profile look complete.
    checks = [
        bool(_text(profile.get("company_name"))),
        profile.get("business_role") in {
            "LOCAL_DISTRIBUTOR",
            "REGIONAL_DISTRIBUTOR",
            "MANUFACTURER_SALES",
            "MANUFACTURER_CHANNEL_MANAGER",
            "OTHER",
        },
        region_valid and bool(_nonempty_list(profile.get("operating_regions"))),
        bool(customer_types),
        product_valid and bool(_nonempty_list(profile.get("product_capabilities"))),
        isinstance(partnering, dict)
        and all(isinstance(partnering.get(key), bool) for key in (
            "can_seek_temporary_manufacturer",
            "can_cooperate_with_channel_partner",
            "can_do_rental_projects",
        )),
        isinstance(thresholds, dict) and _money(thresholds.get("minimum_project_amount_cny")) is not None,
        isinstance(thresholds, dict) and bool(_nonempty_list(thresholds.get("preferred_stages"))),
    ]
    base_points = round(70 * sum(checks) / len(checks))
    confirmation_points = 0
    if isinstance(confirmation_flags, dict):
        confirmation_points = round(
            30
            * sum(1 for value in confirmation_flags.values() if value is True)
            / 6
        )
    completeness = min(100, base_points + confirmation_points)
    if personalized_allowed:
        completeness = 100

    supplied_status = profile.get("profile_status")
    supplied_completeness = profile.get("profile_completeness")
    supplied_missing = profile.get("missing_required_conditions")
    if supplied_status and supplied_status != status:
        warnings.append("SUPPLIED_PROFILE_STATUS_IGNORED_AND_RECOMPUTED")
    if isinstance(supplied_completeness, int) and supplied_completeness != completeness:
        warnings.append("SUPPLIED_PROFILE_COMPLETENESS_IGNORED_AND_RECOMPUTED")
    if isinstance(supplied_missing, list):
        expected_codes = [item.code for item in missing]
        if sorted(str(item) for item in supplied_missing) != sorted(expected_codes):
            warnings.append("SUPPLIED_MISSING_CONDITIONS_IGNORED_AND_RECOMPUTED")

    next_question = missing[0].question if missing else None
    return ProfileGateResult(
        computed_status=status,
        profile_completeness=completeness,
        recommendation_mode=mode,
        personalized_recommendation_allowed=personalized_allowed,
        candidate_opportunity_allowed=candidate_allowed,
        missing_conditions=tuple(missing),
        next_question=next_question,
        warnings=tuple(warnings),
    )
