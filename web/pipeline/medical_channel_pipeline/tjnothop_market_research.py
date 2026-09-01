from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .validation import validate_record

ALLOWED_HOSTS = {"tjnothop.cn", "www.tjnothop.cn"}


class TjnothopParseError(ValueError):
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
        raise TjnothopParseError(code)


def _extract_title(text: str) -> str:
    match = re.search(r"(天津市天津医院\s*[^。]{1,100}?采购项目调研公告)", text)
    if not match:
        raise TjnothopParseError("TJNOTHOP_TITLE_NOT_FOUND")
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _extract_product(text: str) -> tuple[str, str | None]:
    name_match = re.search(r"产品名称\s*[：:]\s*(.+?)(?=\s+2[、.．])", text)
    if not name_match:
        raise TjnothopParseError("TJNOTHOP_PRODUCT_NAME_NOT_FOUND")
    product_name = name_match.group(1).strip(" ：:;,，；")
    if not product_name:
        raise TjnothopParseError("TJNOTHOP_PRODUCT_NAME_EMPTY")

    quantity_match = re.search(r"采购数量\s*[：:]\s*(.+?)(?=\s+3[、.．])", text)
    quantity = quantity_match.group(1).strip(" ：:;,，；") if quantity_match else None
    return product_name, quantity or None


def _extract_budget(text: str) -> int | None:
    match = re.search(r"预算金额\s*[：:]\s*([0-9]+(?:\.[0-9]+)?)\s*(万元|元)", text)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise TjnothopParseError("TJNOTHOP_BUDGET_INVALID") from exc
    if amount < 0:
        raise TjnothopParseError("TJNOTHOP_BUDGET_INVALID")
    multiplier = Decimal(10_000 if match.group(2) == "万元" else 1)
    yuan = amount * multiplier
    integral = yuan.to_integral_value()
    if yuan != integral:
        raise TjnothopParseError("TJNOTHOP_BUDGET_NOT_WHOLE_CNY")
    return int(integral)


def _extract_registration_deadline_date(text: str) -> str:
    section = re.search(
        r"报名及资质提交时间\s*[：:]?\s*(.+?)(?=\s*(?:五|六)[、.．]\s*论证时间)",
        text,
    )
    if not section:
        raise TjnothopParseError("TJNOTHOP_REGISTRATION_SECTION_NOT_FOUND")
    matches = re.findall(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?",
        section.group(1),
    )
    if not matches:
        raise TjnothopParseError("TJNOTHOP_REGISTRATION_DATE_NOT_FOUND")
    year, month, day = (int(value) for value in matches[-1])
    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise TjnothopParseError("TJNOTHOP_REGISTRATION_DATE_INVALID") from exc
    return parsed.isoformat()


def _extract_contact(text: str) -> dict[str, str | None] | None:
    phone_match = re.search(r"联系电话\s*[：:]?\s*([0-9-]{7,20})", text)
    if not phone_match:
        return None
    name_match = re.search(r"联系人\s*[：:]?\s*([^\s，。；;]{1,10})", text)
    title = "设备物资科" if "设备物资科" in text else None
    return {
        "name": name_match.group(1) if name_match else None,
        "title": title,
        "phone": phone_match.group(1),
        "email": None,
    }


def parse_tjnothop_market_research(
    html: str,
    *,
    source_url: str,
    index_url: str,
    index_published_at: str,
    expected_title: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_url(source_url, code="TJNOTHOP_SOURCE_HOST_REJECTED")
    _assert_url(index_url, code="TJNOTHOP_INDEX_HOST_REJECTED")
    if urlparse(source_url).hostname != urlparse(index_url).hostname:
        raise TjnothopParseError("TJNOTHOP_INDEX_DETAIL_HOST_MISMATCH")
    try:
        date.fromisoformat(index_published_at)
    except ValueError as exc:
        raise TjnothopParseError("TJNOTHOP_INDEX_PUBLISHED_DATE_INVALID") from exc

    text = _visible_text(html)
    title = _extract_title(text)
    if _normalize(title) != _normalize(expected_title):
        raise TjnothopParseError("TJNOTHOP_TITLE_MISMATCH")
    product_name, quantity = _extract_product(text)
    budget_cny = _extract_budget(text)
    registration_deadline_date = _extract_registration_deadline_date(text)
    public_contact = _extract_contact(text)

    facts: dict[str, Any] = {
        "project_number": None,
        "project_name": title,
        "buyer_name": "天津市天津医院",
        "hospital_name": "天津市天津医院",
        "department": None,
        "region": "天津市",
        "lifecycle_state": "MARKET_RESEARCH",
        "notice_type": "采购项目调研公告",
        "published_at": index_published_at,
        "registration_deadline": None,
        "registration_deadline_date": registration_deadline_date,
        "bid_deadline": None,
        "expected_procurement_at": None,
        "expected_procurement_precision": None,
        "budget_cny": budget_cny,
        "procurement_method": None,
        "product_categories": [],
        "product_items": [
            {
                "raw_name": product_name,
                "category": None,
                "quantity": quantity,
                "specification": None,
            }
        ],
        "public_contact": public_contact,
    }

    evidence: list[dict[str, str]] = [
        {"field_path": "facts.project_name", "source_url": source_url, "locator": "详情页标题"},
        {"field_path": "facts.buyer_name", "source_url": source_url, "locator": "详情页标题/医院官网主体"},
        {"field_path": "facts.hospital_name", "source_url": source_url, "locator": "详情页标题/医院官网主体"},
        {"field_path": "facts.region", "source_url": source_url, "locator": "天津市天津医院官方页面主体"},
        {
            "field_path": "facts.lifecycle_state",
            "source_url": source_url,
            "locator": "正文=开展采购需求调查/供应商参与调研；确定性生命周期映射",
        },
        {"field_path": "facts.notice_type", "source_url": source_url, "locator": "详情页标题=采购项目调研公告"},
        {"field_path": "facts.published_at", "source_url": index_url, "locator": "官方新闻中心/通知公告列表发布日期"},
        {
            "field_path": "facts.registration_deadline_date",
            "source_url": source_url,
            "locator": "报名及资质提交时间的结束日期；原文未公布具体时分",
        },
        {"field_path": "facts.product_items", "source_url": source_url, "locator": "一、产品要求/产品名称与采购数量"},
    ]
    if budget_cny is not None:
        evidence.append({"field_path": "facts.budget_cny", "source_url": source_url, "locator": "一、产品要求/预算金额"})
    if public_contact:
        evidence.append({"field_path": "facts.public_contact", "source_url": source_url, "locator": "联系电话/设备物资科"})

    record = {
        "schema_version": "0.1",
        "opportunity_id": opportunity_id,
        "source": {
            "source_id": f"tjnothop:{opportunity_id}",
            "source_type": "OFFICIAL_INSTITUTION_NOTICE",
            "url": source_url,
            "observed_at": observed_at,
        },
        "facts": facts,
        "evidence": evidence,
        "quality_flags": ["DEADLINE_TIME_NOT_PUBLISHED"],
    }
    return validate_record(record)
