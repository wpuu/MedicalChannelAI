from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .tjfch_discovery import ALLOWED_HOSTS
from .validation import validate_record

RELATIVE_WINDOW_FLAG = "RELATIVE_REGISTRATION_WINDOW_7_DAYS"


class TjfchTestParseError(ValueError):
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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _assert_url(url: str, *, code: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise TjfchTestParseError(code)


def _extract_published_date(text: str, expected_title: str) -> str:
    title_pos = text.find(expected_title)
    tail = text[title_pos + len(expected_title):] if title_pos >= 0 else text
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})(?:\s+\d{1,2}:\d{2})?\b", tail[:500])
    if iso:
        year, month, day = (int(value) for value in iso.groups())
    else:
        chinese = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", tail[:500])
        if not chinese:
            raise TjfchTestParseError("TJFCH_TEST_PUBLISHED_DATE_NOT_FOUND")
        year, month, day = (int(value) for value in chinese.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise TjfchTestParseError("TJFCH_TEST_PUBLISHED_DATE_INVALID") from exc


def _extract_contact(text: str) -> dict[str, str | None] | None:
    name_match = re.search(r"联系人(?:姓名)?\s*[：:]\s*([^\s，,。；;]{1,15})", text)
    phone_match = re.search(r"(?:联系电话|咨询电话|电话)\s*[：:]\s*([0-9][0-9\-\s]{6,24})", text)
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if not (name_match or phone_match or email_match):
        return None
    phone = re.sub(r"\s+", "", phone_match.group(1)).strip() if phone_match else None
    return {
        "name": name_match.group(1).strip() if name_match else None,
        "title": None,
        "phone": phone or None,
        "email": email_match.group(0) if email_match else None,
    }


def _require_supported_relative_window(text: str) -> None:
    normalized = _normalize(text)
    if "自公告发布之日起7天" not in normalized or "逾期无效" not in normalized:
        raise TjfchTestParseError("TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED")


def parse_tjfch_test_recruitment(
    html: str,
    *,
    source_url: str,
    index_url: str,
    expected_title: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_url(source_url, code="TJFCH_TEST_SOURCE_HOST_REJECTED")
    _assert_url(index_url, code="TJFCH_TEST_INDEX_HOST_REJECTED")
    if urlparse(source_url).hostname != urlparse(index_url).hostname:
        raise TjfchTestParseError("TJFCH_TEST_INDEX_DETAIL_HOST_MISMATCH")

    text = _visible_text(html)
    normalized_title = _normalize(expected_title)
    if normalized_title not in _normalize(text):
        raise TjfchTestParseError("TJFCH_TEST_TITLE_MISMATCH")
    if "测试企业征集公告" not in normalized_title and "意向测试企业征集公告" not in normalized_title:
        raise TjfchTestParseError("TJFCH_TEST_NOTICE_TYPE_UNSUPPORTED")

    published_at = _extract_published_date(text, expected_title)
    _require_supported_relative_window(text)
    public_contact = _extract_contact(text)

    facts: dict[str, Any] = {
        "project_number": None,
        "project_name": expected_title.strip(),
        "buyer_name": "天津市第一中心医院",
        "hospital_name": "天津市第一中心医院",
        "department": None,
        "region": "天津市",
        "lifecycle_state": "PRE_MARKET_RESEARCH",
        "notice_type": "测试企业征集公告",
        "published_at": published_at,
        "registration_deadline": None,
        "registration_deadline_date": None,
        "bid_deadline": None,
        "expected_procurement_at": None,
        "expected_procurement_precision": None,
        "budget_cny": None,
        "procurement_method": None,
        "product_categories": [],
        "product_items": [],
        "public_contact": public_contact,
    }

    evidence: list[dict[str, str]] = [
        {"field_path": "facts.project_name", "source_url": source_url, "locator": "详情页标题与官方院务公开入口标题一致"},
        {"field_path": "facts.buyer_name", "source_url": source_url, "locator": "天津市第一中心医院官方页面主体"},
        {"field_path": "facts.hospital_name", "source_url": source_url, "locator": "天津市第一中心医院官方页面主体"},
        {"field_path": "facts.region", "source_url": source_url, "locator": "天津市第一中心医院官方页面主体"},
        {
            "field_path": "facts.lifecycle_state",
            "source_url": source_url,
            "locator": "正文明确本次测试调研仅为采购前期需求核实；确定性映射为PRE_MARKET_RESEARCH",
        },
        {"field_path": "facts.notice_type", "source_url": source_url, "locator": "详情页标题=测试企业征集公告"},
        {"field_path": "facts.published_at", "source_url": source_url, "locator": "详情页标题下方官方发布日期"},
    ]
    if public_contact:
        evidence.append({"field_path": "facts.public_contact", "source_url": source_url, "locator": "详情页联系电话/咨询电话/报名邮箱"})

    record = {
        "schema_version": "0.1",
        "opportunity_id": opportunity_id,
        "source": {
            "source_id": f"tjfch-test:{opportunity_id}",
            "source_type": "OFFICIAL_INSTITUTION_NOTICE",
            "url": source_url,
            "observed_at": observed_at,
        },
        "facts": facts,
        "evidence": evidence,
        "quality_flags": [RELATIVE_WINDOW_FLAG],
    }
    return validate_record(record)
