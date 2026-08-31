from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .ccgp_detail import html_to_text

CCGP_HOSTS = {"ccgp.gov.cn", "www.ccgp.gov.cn"}
EVENT_TYPES = {"CORRECTION", "TERMINATION"}


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


def _extract_section(text: str, start_pattern: str, end_pattern: str, max_len: int = 1600) -> str | None:
    match = re.search(f"{start_pattern}(.+?){end_pattern}", text, re.S)
    if not match:
        return None
    return _normalize_space(match.group(1))[:max_len] or None


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
    else:
        summary = _extract_section(
            normalized,
            r"二[、.]\s*更正信息\s*[：:]?",
            r"三[、.]\s*其他补充事宜",
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
        "requires_reconciliation": event_type == "CORRECTION",
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
        validated.append(event)
    return validated
