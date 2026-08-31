from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .ccgp_detail import html_to_text

CCGP_HOSTS = {"ccgp.gov.cn", "www.ccgp.gov.cn"}
EVENT_TYPES = {"CORRECTION", "TERMINATION"}
TRACKED_CORRECTION_PATHS = {
    "facts.registration_deadline",
    "facts.bid_deadline",
}
MATERIAL_CHANGE_KEYWORDS = (
    "采购需求",
    "技术参数",
    "技术要求",
    "规格",
    "型号",
    "数量",
    "预算金额",
    "最高限价",
    "资格要求",
    "评分标准",
    "评标办法",
)


class CcgpEventParseError(ValueError):
    pass


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _assert_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in CCGP_HOSTS:
        raise CcgpEventParseError("CCGP_EVENT_SOURCE_HOST_REJECTED")


def _date_from_groups(groups: tuple[str, str, str]) -> str:
    year, month, day = groups
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _datetime_from_groups(groups: tuple[str, str, str, str, str]) -> str:
    year, month, day, hour, minute = groups
    return (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        f"T{int(hour):02d}:{int(minute):02d}:00+08:00"
    )


def _extract_project_number(text: str) -> str:
    patterns = [
        r"原公告的采购项目编号\s*[：:]\s*([^\s，。；;]+)",
        r"采购项目编号\s*[：:]\s*([^\s，。；;]+)",
        r"项目编号\s*[：:]\s*([^\s，。；;]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    raise CcgpEventParseError("CCGP_EVENT_PROJECT_NUMBER_NOT_FOUND")


def _extract_project_name(text: str) -> str | None:
    patterns = [
        r"原公告的采购项目名称\s*[：:]\s*(.+?)\s+首次公告日期",
        r"采购项目名称\s*[：:]\s*(.+?)\s+二[、.]",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return _normalize_space(match.group(1))
    return None


def _extract_published_date(text: str, event_type: str) -> str:
    patterns = []
    if event_type == "CORRECTION":
        patterns.append(r"更正日期\s*[：:]\s*(20\d{2})[-年](\d{1,2})[-月](\d{1,2})日?")
    patterns.extend(
        [
            r"发布日期\s*[：:]\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
            r"公告时间\s*[|：:]?\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
        ]
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _date_from_groups(match.groups())
    raise CcgpEventParseError("CCGP_EVENT_PUBLISHED_DATE_NOT_FOUND")


def _extract_section(text: str, start_pattern: str, end_pattern: str, max_len: int = 2400) -> str | None:
    match = re.search(f"{start_pattern}(.+?){end_pattern}", text, re.S)
    if not match:
        return None
    return _normalize_space(match.group(1))[:max_len] or None


def _parse_iso_like_datetime(value: str) -> str | None:
    match = re.search(
        r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})\s*[：:]\s*(\d{2})(?::\d{2})?",
        value,
    )
    if not match:
        return None
    return _datetime_from_groups(match.groups())


def _parse_cn_datetime(value: str) -> str | None:
    match = re.search(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*"
        r"(\d{1,2})\s*(?:点|时|[:：])\s*(\d{1,2})\s*(?:分)?",
        value,
    )
    if not match:
        return None
    return _datetime_from_groups(match.groups())


def _extract_bid_deadline_override(text: str) -> tuple[bool, str | None]:
    standard = re.search(
        r"原公告的投标文件提交截止时间\s*[：:]\s*.+?更正为\s*[：:]?\s*"
        r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}[：:]\d{2}(?::\d{2})?)",
        text,
        re.S,
    )
    if standard:
        return True, _parse_iso_like_datetime(standard.group(1))

    cn = re.search(
        r"现更正(?:投标文件提交截止时间|投标截止时间、开标时间|投标截止时间).*?[：:]\s*"
        r"((?:20\d{2}).{0,40}?(?:点|时|[:：]).{0,8}?(?:分)?)",
        text,
        re.S,
    )
    if cn:
        return True, _parse_cn_datetime(cn.group(1))

    changed = bool(re.search(r"(?:投标文件提交截止时间|投标截止时间).{0,80}?(?:更正|调整|变更)", text))
    return changed, None


def _extract_registration_override(text: str) -> tuple[bool, str | None]:
    block = re.search(
        r"原公告的获取(?:招标|采购)文件结束(?:日期|时间)\s*[：:]\s*.+?更正为\s*[：:]?\s*"
        r"([^。；;]+)",
        text,
        re.S,
    )
    if block:
        replacement = block.group(1)
        exact = _parse_iso_like_datetime(replacement) or _parse_cn_datetime(replacement)
        return True, exact

    changed = bool(
        re.search(
            r"获取(?:招标|采购)文件(?:结束日期|结束时间|截止时间).{0,80}?(?:更正|调整|变更)",
            text,
        )
    )
    return changed, None


def _has_material_unparsed_change(summary: str | None) -> bool:
    if not summary:
        return False
    return any(keyword in summary for keyword in MATERIAL_CHANGE_KEYWORDS)


def _extract_correction_changes(text: str, summary: str | None) -> tuple[list[str], dict[str, str], list[str]]:
    changed_paths: list[str] = []
    fact_overrides: dict[str, str] = {}
    unresolved_paths: list[str] = []

    registration_changed, registration_value = _extract_registration_override(text)
    if registration_changed:
        path = "facts.registration_deadline"
        changed_paths.append(path)
        if registration_value:
            fact_overrides[path] = registration_value
        else:
            unresolved_paths.append(path)

    bid_changed, bid_value = _extract_bid_deadline_override(text)
    if bid_changed:
        path = "facts.bid_deadline"
        changed_paths.append(path)
        if bid_value:
            fact_overrides[path] = bid_value
        else:
            unresolved_paths.append(path)

    if _has_material_unparsed_change(summary):
        unresolved_paths.append("__material_correction__")

    if not changed_paths and not unresolved_paths:
        unresolved_paths.append("__unparsed_correction__")

    return sorted(set(changed_paths)), fact_overrides, sorted(set(unresolved_paths))


def parse_ccgp_event_text(
    text: str,
    *,
    source_url: str,
    observed_at: str,
    event_id: str,
) -> dict[str, Any]:
    _assert_source_url(source_url)
    normalized = _normalize_space(text.replace("\xa0", " "))

    if "终止公告" in normalized:
        event_type = "TERMINATION"
    elif "更正公告" in normalized or "更正信息" in normalized:
        event_type = "CORRECTION"
    else:
        raise CcgpEventParseError("CCGP_EVENT_TYPE_NOT_SUPPORTED")

    project_number = _extract_project_number(normalized)
    project_name = _extract_project_name(normalized)
    published_at = _extract_published_date(normalized, event_type)

    if event_type == "TERMINATION":
        summary = _extract_section(
            normalized,
            r"二[、.]\s*项目终止的原因\s*[：:]?",
            r"三[、.]\s*其他补充事宜",
        )
        changed_fact_paths: list[str] = []
        fact_overrides: dict[str, str] = {}
        unresolved_fact_paths: list[str] = []
    else:
        summary = _extract_section(
            normalized,
            r"二[、.]\s*更正信息\s*[：:]?",
            r"三[、.]\s*其他补充(?:事宜|事项)",
        )
        changed_fact_paths, fact_overrides, unresolved_fact_paths = _extract_correction_changes(
            normalized,
            summary,
        )

    return {
        "schema_version": "0.1",
        "event_id": event_id,
        "event_type": event_type,
        "project_number": project_number,
        "project_name": project_name,
        "published_at": published_at,
        "source_url": source_url,
        "observed_at": observed_at,
        "summary": summary,
        "changed_fact_paths": changed_fact_paths,
        "fact_overrides": fact_overrides,
        "unresolved_fact_paths": unresolved_fact_paths,
        "requires_reconciliation": event_type == "CORRECTION" and bool(unresolved_fact_paths),
        "terminal": event_type == "TERMINATION",
    }


def parse_ccgp_event_html(
    html: str,
    *,
    source_url: str,
    observed_at: str,
    event_id: str,
) -> dict[str, Any]:
    return parse_ccgp_event_text(
        html_to_text(html),
        source_url=source_url,
        observed_at=observed_at,
        event_id=event_id,
    )


def validate_notice_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for event in events:
        if event.get("schema_version") != "0.1":
            raise ValueError("EVENT_SCHEMA_VERSION_UNSUPPORTED")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("EVENT_ID_REQUIRED")
        if event_id in seen_ids:
            raise ValueError(f"DUPLICATE_EVENT_ID:{event_id}")
        seen_ids.add(event_id)
        if event.get("event_type") not in EVENT_TYPES:
            raise ValueError("EVENT_TYPE_INVALID")
        project_number = event.get("project_number")
        if not isinstance(project_number, str) or not project_number.strip():
            raise ValueError("EVENT_PROJECT_NUMBER_REQUIRED")
        published_at = event.get("published_at")
        if not isinstance(published_at, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", published_at):
            raise ValueError("EVENT_PUBLISHED_DATE_INVALID")
        _assert_source_url(str(event.get("source_url") or ""))

        changed_paths = event.get("changed_fact_paths", [])
        fact_overrides = event.get("fact_overrides", {})
        unresolved_paths = event.get("unresolved_fact_paths", [])
        if not isinstance(changed_paths, list) or not all(isinstance(path, str) for path in changed_paths):
            raise ValueError("EVENT_CHANGED_PATHS_INVALID")
        if not isinstance(fact_overrides, dict):
            raise ValueError("EVENT_FACT_OVERRIDES_INVALID")
        if not isinstance(unresolved_paths, list) or not all(isinstance(path, str) for path in unresolved_paths):
            raise ValueError("EVENT_UNRESOLVED_PATHS_INVALID")
        if any(path not in TRACKED_CORRECTION_PATHS for path in fact_overrides):
            raise ValueError("EVENT_FACT_OVERRIDE_PATH_INVALID")
        if any(path not in changed_paths for path in fact_overrides):
            raise ValueError("EVENT_FACT_OVERRIDE_WITHOUT_CHANGE")
        for value in fact_overrides.values():
            if not isinstance(value, str) or not value.endswith("+08:00"):
                raise ValueError("EVENT_FACT_OVERRIDE_VALUE_INVALID")

        validated.append(event)
    return validated
