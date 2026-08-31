from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse
from typing import Any

from .validation import validate_record

ALLOWED_HOSTS = {"tjmugh.com.cn", "www.tjmugh.com.cn"}


class TjmughParseError(ValueError):
    pass


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data.strip())


def _visible_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return " ".join(parser.parts)


def _assert_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise TjmughParseError("TJMUGH_SOURCE_HOST_REJECTED")


def _extract_title(text: str) -> str:
    match = re.search(r"(天津医科大学总医院[^。]{0,80}?市场调研论证邀请函)", text)
    if match:
        return re.sub(r"\s+", "", match.group(1))
    match = re.search(r"([^。]{0,80}?医疗设备[^。]{0,40}?市场调研论证邀请函)", text)
    if match:
        title = re.sub(r"\s+", "", match.group(1))
        return title if title.startswith("天津医科大学总医院") else f"天津医科大学总医院{title}"
    raise TjmughParseError("TJMUGH_TITLE_NOT_FOUND")


def _extract_published_date(text: str) -> str:
    match = re.search(r"\b(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?\b", text)
    if not match:
        raise TjmughParseError("TJMUGH_PUBLISHED_DATE_NOT_FOUND")
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _extract_deadline(text: str) -> str:
    match = re.search(
        r"报名截止时间.{0,30}?(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?[^0-9]{0,12}(\d{1,2})\s*[：:]\s*:?(\d{2})",
        text,
    )
    if not match:
        raise TjmughParseError("TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND")
    year, month, day, hour, minute = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+08:00"


def _extract_items(text: str) -> list[dict[str, Any]]:
    start = re.search(r"一[、.]\s*论证项目名称\s*[：:]", text)
    end = re.search(r"二[、.]\s*供应商", text)
    if not start or not end or end.start() <= start.end():
        raise TjmughParseError("TJMUGH_PROJECT_SECTION_NOT_FOUND")
    section = text[start.end() : end.start()].strip()
    markers = list(re.finditer(r"[（(](\d{1,2})[）)]", section))
    if not markers:
        raise TjmughParseError("TJMUGH_PROJECT_ITEMS_NOT_FOUND")
    items: list[dict[str, Any]] = []
    for index, marker in enumerate(markers):
        item_start = marker.end()
        item_end = markers[index + 1].start() if index + 1 < len(markers) else len(section)
        raw_name = section[item_start:item_end].strip(" ;；,，")
        if raw_name:
            items.append({"raw_name": raw_name, "category": None, "quantity": None, "specification": None})
    if not items:
        raise TjmughParseError("TJMUGH_PROJECT_ITEMS_EMPTY")
    return items


def _extract_contact(text: str) -> dict[str, str | None] | None:
    match = re.search(r"联系电话\s*[：:]?\s*(\d{7,12})\s*([^\s，。；;]{1,8}老师)?", text)
    if not match:
        return None
    phone = match.group(1)
    name = match.group(2) or None
    return {"name": name, "title": "设备采购科", "phone": phone, "email": None}


def parse_tjmugh_market_research(
    html: str,
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_source_url(source_url)
    text = _visible_text(html)
    title = _extract_title(text)
    published_at = _extract_published_date(text)
    registration_deadline = _extract_deadline(text)
    product_items = _extract_items(text)
    public_contact = _extract_contact(text)

    facts: dict[str, Any] = {
        "project_number": None,
        "project_name": title,
        "buyer_name": "天津医科大学总医院",
        "hospital_name": "天津医科大学总医院",
        "department": None,
        "region": "天津市",
        "lifecycle_state": "MARKET_RESEARCH",
        "notice_type": "市场调研论证邀请函",
        "published_at": published_at,
        "registration_deadline": registration_deadline,
        "bid_deadline": None,
        "expected_procurement_at": None,
        "expected_procurement_precision": None,
        "budget_cny": None,
        "procurement_method": None,
        "product_categories": [],
        "product_items": product_items,
        "public_contact": public_contact,
    }
    evidence_paths = [
        ("facts.project_name", "页面标题"),
        ("facts.buyer_name", "医院官网与正文主体"),
        ("facts.hospital_name", "医院官网与正文主体"),
        ("facts.region", "医院官网主体/天津医科大学总医院"),
        ("facts.lifecycle_state", "正文=拟开展院内项目市场调研论证/确定性生命周期映射"),
        ("facts.notice_type", "页面标题/市场调研论证邀请函"),
        ("facts.published_at", "页面发布时间"),
        ("facts.registration_deadline", "本次报名截止时间"),
        ("facts.product_items", "一、论证项目名称"),
    ]
    if public_contact:
        evidence_paths.append(("facts.public_contact", "三、联系方式/联系电话"))

    record = {
        "schema_version": "0.1",
        "opportunity_id": opportunity_id,
        "source": {
            "source_id": f"tjmugh:{opportunity_id}",
            "source_type": "OFFICIAL_INSTITUTION_NOTICE",
            "url": source_url,
            "observed_at": observed_at,
        },
        "facts": facts,
        "evidence": [
            {"field_path": path, "source_url": source_url, "locator": locator}
            for path, locator in evidence_paths
        ],
    }
    return validate_record(record)
