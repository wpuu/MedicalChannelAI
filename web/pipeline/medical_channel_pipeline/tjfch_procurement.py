from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .tjfch_discovery import ALLOWED_HOSTS
from .validation import validate_record

TIANJIN = ZoneInfo("Asia/Shanghai")


class TjfchParseError(ValueError):
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
        raise TjfchParseError(code)


def _extract_project_number(text: str) -> str | None:
    match = re.search(r"项目编号\s*[：:]\s*([A-Za-z0-9_\-－–—]+)", text)
    if not match:
        return None
    value = match.group(1).replace("－", "-").replace("–", "-").replace("—", "-").strip()
    return value or None


def _to_cny(amount_text: str, unit: str) -> int:
    try:
        amount = Decimal(amount_text.replace(",", ""))
    except InvalidOperation as exc:
        raise TjfchParseError("TJFCH_BUDGET_INVALID") from exc
    if amount < 0:
        raise TjfchParseError("TJFCH_BUDGET_INVALID")
    multiplier = Decimal(10_000 if unit == "万元" else 1)
    yuan = amount * multiplier
    integral = yuan.to_integral_value()
    if yuan != integral:
        raise TjfchParseError("TJFCH_BUDGET_NOT_WHOLE_CNY")
    return int(integral)


def _extract_budget(text: str) -> int | None:
    for pattern in (
        r"项目预算\s*[：:]\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万元|元)",
        r"最高限价\s*[：:]\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万元|元)",
        r"预算金额\s*[：:]\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万元|元)",
    ):
        match = re.search(pattern, text)
        if match:
            return _to_cny(match.group(1), match.group(2))
    return None


def _extract_bid_deadline(text: str) -> str:
    prefix = r"(?:院内比选响应文件|响应文件|投标文件|比选文件)[^。；;]{0,35}?(?:递交|提交)[^。；;]{0,20}?截止时间"
    patterns = (
        prefix + r"\s*[：:]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*(上午|下午)?\s*(\d{1,2})\s*[：:]\s*(\d{2})",
        r"(?:递交|提交)[^。；;]{0,35}?截止时间\s*[：:]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*(上午|下午)?\s*(\d{1,2})\s*[：:]\s*(\d{2})",
    )
    match = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            break
    if not match:
        iso = re.search(
            r"(?:递交|提交)[^。；;]{0,35}?截止时间\s*[：:]?\s*(20\d{2})-(\d{1,2})-(\d{1,2})\s+(\d{1,2})\s*[：:]\s*(\d{2})",
            text,
        )
        if not iso:
            raise TjfchParseError("TJFCH_BID_DEADLINE_NOT_EXACT")
        year, month, day, hour, minute = (int(value) for value in iso.groups())
    else:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        meridiem = match.group(4)
        hour = int(match.group(5))
        minute = int(match.group(6))
        if meridiem == "下午" and hour < 12:
            hour += 12
        if meridiem == "上午" and hour == 12:
            hour = 0
    try:
        return datetime(year, month, day, hour, minute, tzinfo=TIANJIN).isoformat()
    except ValueError as exc:
        raise TjfchParseError("TJFCH_BID_DEADLINE_INVALID") from exc


def _extract_contact(text: str) -> dict[str, str | None] | None:
    name_match = re.search(r"联系人\s*[：:]\s*([^\s，,。；;]{1,15})", text)
    phone_match = re.search(r"(?:联系电话|电话)\s*[：:]\s*([0-9][0-9\-\s]{6,24})", text)
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


def parse_tjfch_procurement_notice(
    html: str,
    *,
    source_url: str,
    index_url: str,
    index_published_at: str,
    expected_title: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_url(source_url, code="TJFCH_SOURCE_HOST_REJECTED")
    _assert_url(index_url, code="TJFCH_INDEX_HOST_REJECTED")
    if urlparse(source_url).hostname != urlparse(index_url).hostname:
        raise TjfchParseError("TJFCH_INDEX_DETAIL_HOST_MISMATCH")
    try:
        date.fromisoformat(index_published_at)
    except ValueError as exc:
        raise TjfchParseError("TJFCH_INDEX_PUBLISHED_DATE_INVALID") from exc

    text = _visible_text(html)
    if _normalize(expected_title) not in _normalize(text):
        raise TjfchParseError("TJFCH_TITLE_MISMATCH")
    if "院内比选" not in _normalize(expected_title) or "公告" not in _normalize(expected_title):
        raise TjfchParseError("TJFCH_NOTICE_TYPE_UNSUPPORTED")
    if index_published_at not in text and index_published_at.replace("-", "年", 1).replace("-", "月", 1) not in text:
        chinese_date = date.fromisoformat(index_published_at)
        date_markers = {
            f"{chinese_date.year}年{chinese_date.month}月{chinese_date.day}日",
            f"{chinese_date.year} 年 {chinese_date.month} 月 {chinese_date.day} 日",
        }
        if not any(marker in text for marker in date_markers):
            raise TjfchParseError("TJFCH_DETAIL_PUBLISHED_DATE_NOT_CONFIRMED")

    project_number = _extract_project_number(text)
    budget_cny = _extract_budget(text)
    bid_deadline = _extract_bid_deadline(text)
    public_contact = _extract_contact(text)

    facts: dict[str, Any] = {
        "project_number": project_number,
        "project_name": expected_title.strip(),
        "buyer_name": "天津市第一中心医院",
        "hospital_name": "天津市第一中心医院",
        "department": None,
        "region": "天津市",
        "lifecycle_state": "BIDDING",
        "notice_type": "院内比选采购公告",
        "published_at": index_published_at,
        "registration_deadline": None,
        "registration_deadline_date": None,
        "bid_deadline": bid_deadline,
        "expected_procurement_at": None,
        "expected_procurement_precision": None,
        "budget_cny": budget_cny,
        "procurement_method": "院内比选",
        "product_categories": [],
        "product_items": [],
        "public_contact": public_contact,
    }

    evidence: list[dict[str, str]] = [
        {"field_path": "facts.project_name", "source_url": source_url, "locator": "详情页标题与官方列表标题一致"},
        {"field_path": "facts.buyer_name", "source_url": source_url, "locator": "天津市第一中心医院官方院内比选页面主体"},
        {"field_path": "facts.hospital_name", "source_url": source_url, "locator": "天津市第一中心医院官方院内比选页面主体"},
        {"field_path": "facts.region", "source_url": source_url, "locator": "天津市第一中心医院官方页面主体"},
        {"field_path": "facts.lifecycle_state", "source_url": source_url, "locator": "标题/正文=院内比选采购公告；确定性映射为BIDDING"},
        {"field_path": "facts.notice_type", "source_url": source_url, "locator": "官方栏目=院内比选采购信息；标题含院内比选公告"},
        {"field_path": "facts.published_at", "source_url": source_url, "locator": "详情页发布日期与/system/YYYY/MM/DD/路径日期一致"},
        {"field_path": "facts.bid_deadline", "source_url": source_url, "locator": "响应/投标文件递交截止时间，原文含明确日期和时分"},
        {"field_path": "facts.procurement_method", "source_url": source_url, "locator": "标题/正文明确采用院内比选"},
    ]
    if project_number:
        evidence.append({"field_path": "facts.project_number", "source_url": source_url, "locator": "项目编号"})
    if budget_cny is not None:
        evidence.append({"field_path": "facts.budget_cny", "source_url": source_url, "locator": "项目预算/最高限价/预算金额"})
    if public_contact:
        evidence.append({"field_path": "facts.public_contact", "source_url": source_url, "locator": "项目联系方式/联系人/电话/政务邮箱"})

    record = {
        "schema_version": "0.1",
        "opportunity_id": opportunity_id,
        "source": {
            "source_id": f"tjfch:{opportunity_id}",
            "source_type": "OFFICIAL_INSTITUTION_NOTICE",
            "url": source_url,
            "observed_at": observed_at,
        },
        "facts": facts,
        "evidence": evidence,
        "quality_flags": [],
    }
    return validate_record(record)
