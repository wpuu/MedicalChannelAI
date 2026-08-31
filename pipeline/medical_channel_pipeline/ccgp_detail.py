from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .validation import validate_record

CCGP_HOSTS = {"ccgp.gov.cn", "www.ccgp.gov.cn"}


class CcgpDetailParseError(ValueError):
    pass


class _VisibleTextParser(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "li",
        "p",
        "section",
        "table",
        "tbody",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _assert_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in CCGP_HOSTS:
        raise CcgpDetailParseError("CCGP_DETAIL_SOURCE_HOST_REJECTED")


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _date_from_cn(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _datetime_from_cn(
    year: str,
    month: str,
    day: str,
    hour: str,
    minute: str,
) -> str:
    return (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        f"T{int(hour):02d}:{int(minute):02d}:00+08:00"
    )


def _required_match(pattern: str, text: str, code: str, flags: int = 0) -> re.Match[str]:
    match = re.search(pattern, text, flags)
    if not match:
        raise CcgpDetailParseError(code)
    return match


def _extract_project_number(text: str) -> str:
    match = _required_match(
        r"项目编号\s*[：:]\s*([^\s，。；;]+)",
        text,
        "CCGP_PROJECT_NUMBER_NOT_FOUND",
    )
    return match.group(1).strip()


def _extract_project_name(text: str) -> str:
    match = _required_match(
        r"项目名称\s*[：:]\s*(.+?)\s+预算金额\s*[：:]",
        text,
        "CCGP_PROJECT_NAME_NOT_FOUND",
        re.S,
    )
    return _normalize_space(match.group(1))


def _extract_buyer(text: str) -> str:
    patterns = [
        r"采购人信息\s+名称\s*[：:]\s*(.+?)\s+地址\s*[：:]",
        r"采购单位\s*[|：:]?\s*(.+?)\s+(?:采购单位地址|行政区域|公告时间)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return _normalize_space(match.group(1))
    raise CcgpDetailParseError("CCGP_BUYER_NOT_FOUND")


def _extract_region(text: str) -> str | None:
    match = re.search(r"行政区域\s*[|：:]?\s*(.+?)\s+(?:\||公告时间)", text, re.S)
    return _normalize_space(match.group(1)) if match else None


def _extract_publish_date(text: str) -> str:
    patterns = [
        r"发布日期\s*[：:]\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
        r"公告时间\s*[|：:]?\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
        r"\b(20\d{2})年(\d{1,2})月(\d{1,2})日\s+\d{1,2}:\d{2}\s+来源",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _date_from_cn(*match.groups())
    raise CcgpDetailParseError("CCGP_PUBLISHED_DATE_NOT_FOUND")


def _extract_registration_deadline(text: str) -> str:
    section = re.search(
        r"三[、.]\s*获取招标文件\s+时间\s*[：:]\s*"
        r"20\d{2}年\d{1,2}月\d{1,2}日\s*到\s*"
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日"
        r"(.+?)(?:地点\s*[：:]|四[、.])",
        text,
        re.S,
    )
    if not section:
        raise CcgpDetailParseError("CCGP_REGISTRATION_SECTION_NOT_FOUND")
    year, month, day, schedule = section.groups()
    times = re.findall(r"至\s*(\d{1,2})\s*[：:]\s*(\d{2})", schedule)
    if not times:
        raise CcgpDetailParseError("CCGP_REGISTRATION_END_TIME_NOT_FOUND")
    hour, minute = times[-1]
    return _datetime_from_cn(year, month, day, hour, minute)


def _extract_bid_deadline(text: str) -> str:
    match = _required_match(
        r"四[、.]\s*提交投标文件截止时间、开标时间和地点\s*"
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*"
        r"(\d{1,2})\s*点\s*(\d{1,2})\s*分",
        text,
        "CCGP_BID_DEADLINE_NOT_FOUND",
        re.S,
    )
    return _datetime_from_cn(*match.groups())


def _extract_budget_cny(text: str) -> int | None:
    match = re.search(r"预算金额\s*[：:]\s*([0-9]+(?:\.[0-9]+)?)\s*万元", text)
    if not match:
        match = re.search(r"预算金额\s*[|：:]?\s*[￥¥]?\s*([0-9]+(?:\.[0-9]+)?)\s*万元", text)
    if not match:
        return None
    return int(round(float(match.group(1)) * 10_000))


def _extract_contact(text: str) -> dict[str, str | None] | None:
    match = re.search(
        r"3[.、]\s*项目联系方式\s+项目联系人\s*[：:]\s*(.+?)\s+"
        r"(?:电\s*话|联系电话)\s*[：:]\s*([^\s，。；;]+)",
        text,
        re.S,
    )
    if not match:
        match = re.search(
            r"项目联系人\s*[|：:]?\s*(.+?)\s+(?:项目联系电话|联系电话)\s*[|：:]?\s*([^\s，。；;]+)",
            text,
            re.S,
        )
    if not match:
        return None
    return {
        "name": _normalize_space(match.group(1)),
        "title": "项目联系人",
        "phone": _normalize_space(match.group(2)),
        "email": None,
    }


def _extract_package_products(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"第[一二三四五六七八九十]+包\s*[：:]\s*(.+?)(?:的采购|；|;|。)",
        text,
        re.S,
    ):
        name = _normalize_space(match.group(1)).strip("，,：:；;。")
        if not name or len(name) > 500 or name in seen:
            continue
        seen.add(name)
        items.append(
            {
                "raw_name": name,
                "category": None,
                "quantity": None,
                "specification": None,
            }
        )
    return items


def parse_ccgp_public_tender_text(
    text: str,
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_source_url(source_url)
    normalized = _normalize_space(text.replace("\xa0", " "))
    if "公开招标公告" not in normalized:
        raise CcgpDetailParseError("CCGP_NOTICE_TYPE_NOT_PUBLIC_TENDER")

    project_number = _extract_project_number(normalized)
    project_name = _extract_project_name(normalized)
    buyer_name = _extract_buyer(normalized)
    region = _extract_region(normalized)
    published_at = _extract_publish_date(normalized)
    registration_deadline = _extract_registration_deadline(normalized)
    bid_deadline = _extract_bid_deadline(normalized)
    budget_cny = _extract_budget_cny(normalized)
    product_items = _extract_package_products(normalized)
    public_contact = _extract_contact(normalized)

    facts: dict[str, Any] = {
        "project_number": project_number,
        "project_name": project_name,
        "buyer_name": buyer_name,
        "hospital_name": None,
        "department": None,
        "region": region,
        "lifecycle_state": "BIDDING",
        "notice_type": "公开招标公告",
        "published_at": published_at,
        "registration_deadline": registration_deadline,
        "bid_deadline": bid_deadline,
        "expected_procurement_at": None,
        "expected_procurement_precision": None,
        "budget_cny": budget_cny,
        "procurement_method": "公开招标",
        "product_categories": [],
        "product_items": product_items,
        "public_contact": public_contact,
    }

    evidence_paths: list[tuple[str, str]] = [
        ("facts.project_number", "一、项目基本情况/项目编号"),
        ("facts.project_name", "一、项目基本情况/项目名称"),
        ("facts.buyer_name", "七、采购人信息/名称"),
        ("facts.lifecycle_state", "公告类型=公开招标公告/确定性生命周期映射"),
        ("facts.notice_type", "公告类型/公开招标公告"),
        ("facts.published_at", "公告发布日期"),
        ("facts.registration_deadline", "三、获取招标文件/时间"),
        ("facts.bid_deadline", "四、提交投标文件截止时间、开标时间和地点"),
        ("facts.procurement_method", "公告类型=公开招标公告/确定性采购方式映射"),
    ]
    if region:
        evidence_paths.append(("facts.region", "公告概要/行政区域"))
    if budget_cny is not None:
        evidence_paths.append(("facts.budget_cny", "一、项目基本情况/预算金额"))
    if product_items:
        evidence_paths.append(("facts.product_items", "一、项目基本情况/采购需求/分包设备清单"))
    if public_contact:
        evidence_paths.append(("facts.public_contact", "七、项目联系方式"))

    record = {
        "schema_version": "0.1",
        "opportunity_id": opportunity_id,
        "source": {
            "source_id": f"ccgp:{project_number}",
            "source_type": "CCGP_NOTICE",
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


def parse_ccgp_public_tender_html(
    html: str,
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    return parse_ccgp_public_tender_text(
        html_to_text(html),
        source_url=source_url,
        observed_at=observed_at,
        opportunity_id=opportunity_id,
    )


def fetch_ccgp_detail_html(source_url: str, *, timeout_seconds: int = 30) -> str:
    _assert_source_url(source_url)
    request = Request(
        source_url,
        headers={
            "User-Agent": "MedicalChannelAI/0.1 (+evidence-first public procurement verification)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"CCGP_DETAIL_HTTP_{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("CCGP_DETAIL_NETWORK_ERROR") from exc


def parse_observed_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
