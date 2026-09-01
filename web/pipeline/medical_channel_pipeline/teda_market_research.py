from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .validation import validate_record

ALLOWED_HOSTS = {'tedahospital.com.cn', 'www.tedahospital.com.cn'}


class TedaParseError(ValueError):
    pass


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {'script', 'style'}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style'} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data.strip())


def _visible_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return ' '.join(parser.parts)


def _compact_fragmented_digits(text: str) -> str:
    return re.sub(r'(?<=\d)\s+(?=\d)', '', text)


def _normalize(text: str) -> str:
    return re.sub(r'\s+', '', text)


def _assert_official_url(url: str, *, code: str, detail_required: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise TedaParseError(code)
    if detail_required and not re.fullmatch(r'/article/show/9/\d+', parsed.path.rstrip('/')):
        raise TedaParseError(code)


def _verify_title(text: str, expected_title: str) -> str:
    normalized_expected = _normalize(expected_title)
    if not normalized_expected or normalized_expected not in _normalize(text):
        raise TedaParseError('TEDA_TITLE_MISMATCH')
    return re.sub(r'\s+', ' ', expected_title).strip()


def _verify_medical_early_signal(text: str) -> None:
    normalized = _normalize(text)
    demand_research = '医疗设备采购需求调研' in normalized
    medical_argument = '医疗设备采购' in normalized and '论证' in normalized
    if not (demand_research or medical_argument):
        raise TedaParseError('TEDA_MEDICAL_EARLY_SIGNAL_NOT_VERIFIED')


def _parse_iso_date(value: str, *, code: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise TedaParseError(code) from exc


def _extract_detail_published_at(text: str) -> str | None:
    parse_text = _compact_fragmented_digits(text)
    patterns = (
        r'天津市泰达医院\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
        r'天津市泰达医院\s*(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})',
    )
    matches: list[tuple[str, str, str]] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, parse_text))
    if not matches:
        return None
    year, month, day = (int(value) for value in matches[-1])
    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise TedaParseError('TEDA_PUBLISHED_DATE_INVALID') from exc


def _resolve_published_at(text: str, index_published_at: str | None) -> tuple[str, bool]:
    detail_date = _extract_detail_published_at(text)
    index_date = (
        _parse_iso_date(index_published_at, code='TEDA_INDEX_PUBLISHED_DATE_INVALID')
        if index_published_at
        else None
    )
    if detail_date and index_date and detail_date != index_date:
        raise TedaParseError('TEDA_PUBLISHED_DATE_MISMATCH')
    if detail_date:
        return detail_date, False
    if index_date:
        return index_date, True
    raise TedaParseError('TEDA_PUBLISHED_DATE_NOT_FOUND')


def _parse_money(value: str, unit: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise TedaParseError('TEDA_BUDGET_INVALID') from exc
    multiplier = Decimal(10_000 if unit == '万' else 1)
    yuan = amount * multiplier
    integral = yuan.to_integral_value()
    if amount < 0 or yuan != integral:
        raise TedaParseError('TEDA_BUDGET_INVALID')
    return int(integral)


def _product_segment_to_item(segment: str) -> tuple[dict[str, Any], int | None]:
    segment = re.sub(r'\s+', ' ', segment).strip(' ;；,，')
    budget_match = re.search(
        r'预算\s*[：:]?\s*([0-9]+(?:\.[0-9]+)?)\s*(万元|万|元)',
        segment,
    )
    budget = None
    if budget_match:
        unit = '万' if budget_match.group(2) in {'万', '万元'} else '元'
        budget = _parse_money(budget_match.group(1), unit)
    quantity_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(台|套|个|批|件|组)', segment)
    quantity = ''.join(quantity_match.groups()) if quantity_match else None
    name_end_candidates = [
        match.start()
        for match in (quantity_match, budget_match)
        if match is not None
    ]
    name_end = min(name_end_candidates) if name_end_candidates else len(segment)
    raw_name = segment[:name_end].strip(' ：:;；,，')
    raw_name = re.sub(r'^设备明细\s*[：:]?\s*', '', raw_name).strip()
    if not raw_name or raw_name in {'设备明细', '其他需求'}:
        raise TedaParseError('TEDA_PRODUCT_NAME_EMPTY')
    return (
        {
            'raw_name': raw_name,
            'category': None,
            'quantity': quantity,
            'specification': None,
        },
        budget,
    )


def _extract_product_segments(section: str) -> list[str]:
    detail_match = re.search(
        r'(?:^|\s)1[、.．]\s*设备明细\s*[：:]?\s*(.+?)(?=(?:\s|^)2[、.．]\s*其他需求|$)',
        section,
    )
    if detail_match:
        detail_section = detail_match.group(1).strip()
        nested_markers = list(re.finditer(r'(?:^|\s)(\d{1,2})\s*[）)]\s*', detail_section))
        if nested_markers:
            segments: list[str] = []
            for index, marker in enumerate(nested_markers):
                start = marker.end()
                end = nested_markers[index + 1].start() if index + 1 < len(nested_markers) else len(detail_section)
                value = detail_section[start:end].strip(' ;；,，')
                if value:
                    segments.append(value)
            return segments
        if detail_section:
            return [detail_section]

    markers = list(re.finditer(r'(?:^|\s)(\d{1,2})[、.．]\s*', section))
    segments = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(section)
        value = section[start:end].strip(' ;；,，')
        if value:
            segments.append(value)
    return segments


def _extract_product_items(text: str) -> tuple[list[dict[str, Any]], int | None]:
    section_match = re.search(
        r'一[、.．]\s*拟采购设备项目\s*[：:]?\s*(.+?)(?=\s*二[、.．]\s*报名资料)',
        text,
    )
    if not section_match:
        section_match = re.search(
            r'拟采购设备项目\s*[：:]?\s*(.+?)(?=\s*二[、.．]\s*报名资料)',
            text,
        )
    if not section_match:
        raise TedaParseError('TEDA_PRODUCT_SECTION_NOT_FOUND')
    segments = _extract_product_segments(section_match.group(1).strip())
    if not segments:
        raise TedaParseError('TEDA_PRODUCT_ITEMS_NOT_FOUND')

    items: list[dict[str, Any]] = []
    item_budgets: list[int | None] = []
    for segment in segments:
        item, budget = _product_segment_to_item(segment)
        items.append(item)
        item_budgets.append(budget)
    budget_cny = None
    if item_budgets and all(value is not None for value in item_budgets):
        budget_cny = sum(value for value in item_budgets if value is not None)
    return items, budget_cny


def _extract_deadline(text: str) -> tuple[str | None, str | None, list[str]]:
    parse_text = _compact_fragmented_digits(text)
    match = re.search(
        r'报名截止时间\s*[：:]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'
        r'(?:\s*(上午|下午)?\s*(\d{1,2})\s*[：:]\s*(\d{2}))?',
        parse_text,
    )
    if not match:
        raise TedaParseError('TEDA_REGISTRATION_DEADLINE_NOT_FOUND')
    year, month, day = (int(value) for value in match.group(1, 2, 3))
    try:
        parsed_date = date(year, month, day)
    except ValueError as exc:
        raise TedaParseError('TEDA_REGISTRATION_DEADLINE_INVALID') from exc
    daypart, hour_text, minute_text = match.group(4, 5, 6)
    if hour_text is None or minute_text is None:
        return None, parsed_date.isoformat(), ['DEADLINE_TIME_NOT_PUBLISHED']
    hour = int(hour_text)
    minute = int(minute_text)
    if minute > 59 or hour > 23:
        raise TedaParseError('TEDA_REGISTRATION_DEADLINE_INVALID')
    if daypart == '下午' and hour < 12:
        hour += 12
    if daypart == '上午' and hour == 12:
        hour = 0
    return (
        f'{parsed_date.isoformat()}T{hour:02d}:{minute:02d}:00+08:00',
        None,
        [],
    )


def _extract_contact(text: str) -> dict[str, str | None] | None:
    parse_text = _compact_fragmented_digits(text)
    contact_match = re.search(
        r'(?:联系方式\s*[：:]?\s*)?([\u4e00-\u9fff]{1,4}\s*老师)\s*[：:]?\s*([0-9-]{7,20})',
        parse_text,
    )
    email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text)
    if not contact_match and not email_match:
        return None
    title = '医疗设备部' if '医疗设备部' in text else None
    return {
        'name': _normalize(contact_match.group(1)) if contact_match else None,
        'title': title,
        'phone': contact_match.group(2) if contact_match else None,
        'email': email_match.group(0) if email_match else None,
    }


def parse_teda_market_research(
    html: str,
    *,
    source_url: str,
    index_url: str,
    index_published_at: str | None,
    expected_title: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_official_url(source_url, code='TEDA_SOURCE_URL_REJECTED', detail_required=True)
    _assert_official_url(index_url, code='TEDA_INDEX_URL_REJECTED')
    text = _visible_text(html)
    title = _verify_title(text, expected_title)
    _verify_medical_early_signal(text)
    published_at, published_from_index = _resolve_published_at(text, index_published_at)
    product_items, budget_cny = _extract_product_items(text)
    registration_deadline, registration_deadline_date, quality_flags = _extract_deadline(text)
    public_contact = _extract_contact(text)
    notice_type = '设备需求调研' if '需求调研' in _normalize(title) else '医疗设备论证邀请'

    facts: dict[str, Any] = {
        'project_number': None,
        'project_name': title,
        'buyer_name': '天津市泰达医院',
        'hospital_name': '天津市泰达医院',
        'department': None,
        'region': '天津市',
        'lifecycle_state': 'MARKET_RESEARCH',
        'notice_type': notice_type,
        'published_at': published_at,
        'registration_deadline': registration_deadline,
        'registration_deadline_date': registration_deadline_date,
        'bid_deadline': None,
        'expected_procurement_at': None,
        'expected_procurement_precision': None,
        'budget_cny': budget_cny,
        'procurement_method': None,
        'product_categories': [],
        'product_items': product_items,
        'public_contact': public_contact,
    }
    evidence: list[dict[str, str]] = [
        {'field_path': 'facts.project_name', 'source_url': source_url, 'locator': '详情页标题'},
        {'field_path': 'facts.buyer_name', 'source_url': source_url, 'locator': '医院官网主体/正文'},
        {'field_path': 'facts.hospital_name', 'source_url': source_url, 'locator': '医院官网主体/正文'},
        {'field_path': 'facts.region', 'source_url': source_url, 'locator': '天津市泰达医院官方页面主体'},
        {
            'field_path': 'facts.lifecycle_state',
            'source_url': source_url,
            'locator': '正文明确为医疗设备采购需求调研或采购前论证；确定性生命周期映射',
        },
        {'field_path': 'facts.notice_type', 'source_url': source_url, 'locator': '详情页标题/正文调研类型'},
        {
            'field_path': 'facts.published_at',
            'source_url': index_url if published_from_index else source_url,
            'locator': '官方招标公告列表发布日期' if published_from_index else '正文落款发布日期',
        },
        {'field_path': 'facts.product_items', 'source_url': source_url, 'locator': '一、拟采购设备项目/设备明细'},
    ]
    deadline_path = 'facts.registration_deadline' if registration_deadline else 'facts.registration_deadline_date'
    evidence.append({'field_path': deadline_path, 'source_url': source_url, 'locator': '报名截止时间'})
    if budget_cny is not None:
        evidence.append({'field_path': 'facts.budget_cny', 'source_url': source_url, 'locator': '拟采购设备项目/设备明细预算'})
    if public_contact:
        evidence.append({'field_path': 'facts.public_contact', 'source_url': source_url, 'locator': '调研文件提交/联系方式'})

    record: dict[str, Any] = {
        'schema_version': '0.1',
        'opportunity_id': opportunity_id,
        'source': {
            'source_id': f'teda:{opportunity_id}',
            'source_type': 'OFFICIAL_INSTITUTION_NOTICE',
            'url': source_url,
            'observed_at': observed_at,
        },
        'facts': facts,
        'evidence': evidence,
    }
    if quality_flags:
        record['quality_flags'] = quality_flags
    return validate_record(record)
