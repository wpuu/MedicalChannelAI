from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .channel_scope import is_medical_channel_relevant_text
from .validation import validate_record

ALLOWED_HOSTS = {'tjzxfc.cn', 'www.tjzxfc.cn'}
HOSPITAL_NAME = '天津市中心妇产科医院'


class TjzxfcParseError(ValueError):
    pass


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.rows: list[list[str]] = []
        self._ignored_depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {'script', 'style'}:
            self._ignored_depth += 1
        if self._ignored_depth:
            return
        if tag == 'tr':
            self._row = []
        elif tag in {'td', 'th'} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style'}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag in {'td', 'th'} and self._cell is not None and self._row is not None:
            cell = re.sub(r'\s+', ' ', ''.join(self._cell)).strip()
            self._row.append(cell)
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._ignored_depth or not data.strip():
            return
        text = data.strip()
        self.parts.append(text)
        if self._cell is not None:
            self._cell.append(text)


def _parse_html(html: str) -> tuple[str, list[list[str]]]:
    parser = _DetailParser()
    parser.feed(html)
    return ' '.join(parser.parts), parser.rows


def _normalize(value: str) -> str:
    return re.sub(r'\s+', '', value)


def _assert_official_url(url: str, *, code: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise TjzxfcParseError(code)


def _extract_published_date(text: str) -> str:
    match = re.search(r'时间\s*[：:]\s*(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?', text)
    if not match:
        raise TjzxfcParseError('TJZXFC_PUBLISHED_DATE_NOT_FOUND')
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise TjzxfcParseError('TJZXFC_PUBLISHED_DATE_INVALID') from exc


def _extract_deadline(text: str) -> tuple[str | None, str | None]:
    compact = re.sub(r'(?<=\d)\s+(?=\d)', '', text)
    exact_patterns = (
        r'(?:截至|截止|调研时间|提交时间|报名时限|填报时间)[^。；;]{0,80}?(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?[^0-9]{0,20}(\d{1,2})\s*[：:]\s*(\d{2})',
        r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?[^0-9]{0,20}(\d{1,2})\s*[：:]\s*(\d{2})\s*(?:止|截止)',
    )
    for pattern in exact_patterns:
        match = re.search(pattern, compact)
        if not match:
            continue
        year, month, day, hour, minute = (int(part) for part in match.groups())
        try:
            parsed = date(year, month, day)
        except ValueError as exc:
            raise TjzxfcParseError('TJZXFC_DEADLINE_INVALID') from exc
        if hour > 23 or minute > 59:
            raise TjzxfcParseError('TJZXFC_DEADLINE_INVALID')
        return f'{parsed.isoformat()}T{hour:02d}:{minute:02d}:00+08:00', None

    for section in re.findall(r'(?:截至|截止|调研时间|提交时间|报名时限|填报时间)[^。；;]{0,100}', compact):
        dates = re.findall(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?', section)
        if not dates:
            continue
        year, month, day = (int(part) for part in dates[-1])
        try:
            return None, date(year, month, day).isoformat()
        except ValueError as exc:
            raise TjzxfcParseError('TJZXFC_DEADLINE_INVALID') from exc
    raise TjzxfcParseError('TJZXFC_REGISTRATION_DEADLINE_NOT_FOUND')


def _product_from_title(title: str, text: str) -> dict[str, Any] | None:
    compact = re.sub(r'\s+', '', title)
    match = re.search(r'(?:天津市中心妇产科医院)?(.{2,60}?)采购项目市场调研', compact)
    if not match:
        return None
    name = match.group(1).strip('：:，, ')
    if not name or name in {'设备', '医用设备'}:
        return None
    category = None
    for marker in ('病理', '检验', '影像', '超声', '内镜', '麻醉', '采血'):
        if marker in text:
            category = marker
            break
    return {'raw_name': name, 'category': category, 'quantity': None, 'specification': None}


def _products_from_tables(rows: list[list[str]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) < 2 or not re.fullmatch(r'\d{1,3}', row[0].strip()):
            continue
        name = row[1].strip(' ：:，,;；')
        if not name or len(name) > 120 or name in seen:
            continue
        seen.add(name)
        result.append({'raw_name': name, 'category': None, 'quantity': None, 'specification': None})
        if len(result) >= 50:
            break
    return result


def _scope_probe(title: str, product_items: list[dict[str, Any]]) -> str:
    parts = [title]
    for item in product_items:
        for key in ('raw_name', 'category'):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    return '\n'.join(parts)


def _extract_contact(text: str) -> dict[str, str | None] | None:
    phone_match = re.search(r'(?:联系电话|设备科电话)\s*[：:]?\s*(0?\d{2,3}-?\d{7,8}|\d{7,12})', text)
    if not phone_match:
        return None
    name_match = re.search(r'联系人\s*[：:]?\s*([^\s，。；;]{1,10})', text)
    return {
        'name': name_match.group(1) if name_match else None,
        'title': '设备科' if '设备科' in text else None,
        'phone': phone_match.group(1),
        'email': None,
    }


def parse_tjzxfc_market_research(
    html: str,
    *,
    source_url: str,
    index_url: str,
    index_published_at: str,
    expected_title: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_official_url(source_url, code='TJZXFC_SOURCE_HOST_REJECTED')
    _assert_official_url(index_url, code='TJZXFC_INDEX_HOST_REJECTED')
    if urlparse(source_url).hostname != urlparse(index_url).hostname:
        raise TjzxfcParseError('TJZXFC_INDEX_DETAIL_HOST_MISMATCH')
    try:
        date.fromisoformat(index_published_at)
    except ValueError as exc:
        raise TjzxfcParseError('TJZXFC_INDEX_PUBLISHED_DATE_INVALID') from exc

    text, rows = _parse_html(html)
    if HOSPITAL_NAME not in text:
        raise TjzxfcParseError('TJZXFC_HOSPITAL_IDENTITY_NOT_FOUND')
    if _normalize(expected_title) not in _normalize(text):
        raise TjzxfcParseError('TJZXFC_TITLE_MISMATCH')
    published_at = _extract_published_date(text)
    if published_at != index_published_at:
        raise TjzxfcParseError('TJZXFC_PUBLISHED_DATE_MISMATCH')
    if '调研' not in text:
        raise TjzxfcParseError('TJZXFC_NOT_MARKET_RESEARCH')

    product_items = _products_from_tables(rows)
    title_product = _product_from_title(expected_title, text)
    if title_product and all(item['raw_name'] != title_product['raw_name'] for item in product_items):
        product_items.insert(0, title_product)
    if not is_medical_channel_relevant_text(_scope_probe(expected_title, product_items)):
        raise TjzxfcParseError('TJZXFC_NON_MEDICAL_EARLY_SIGNAL')

    registration_deadline, registration_deadline_date = _extract_deadline(text)
    public_contact = _extract_contact(text)
    notice_type = '采购前市场调研' if '采购前' in text or '采购前' in expected_title else '市场调研公告'
    department = '设备科' if ('来源：设备科' in _normalize(text) or '设备科' in expected_title) else None

    facts: dict[str, Any] = {
        'project_number': None,
        'project_name': expected_title,
        'buyer_name': HOSPITAL_NAME,
        'hospital_name': HOSPITAL_NAME,
        'department': department,
        'region': '天津市',
        'lifecycle_state': 'MARKET_RESEARCH',
        'notice_type': notice_type,
        'published_at': published_at,
        'registration_deadline': registration_deadline,
        'registration_deadline_date': registration_deadline_date,
        'bid_deadline': None,
        'expected_procurement_at': None,
        'expected_procurement_precision': None,
        'budget_cny': None,
        'procurement_method': None,
        'product_categories': [],
        'product_items': product_items,
        'public_contact': public_contact,
    }
    evidence = [
        {'field_path': 'facts.project_name', 'source_url': source_url, 'locator': '详情页标题与官方招标公告列表标题一致'},
        {'field_path': 'facts.buyer_name', 'source_url': source_url, 'locator': '天津市中心妇产科医院官方页面主体'},
        {'field_path': 'facts.hospital_name', 'source_url': source_url, 'locator': '天津市中心妇产科医院官方页面主体'},
        {'field_path': 'facts.region', 'source_url': source_url, 'locator': '天津市中心妇产科医院官方页面主体'},
        {'field_path': 'facts.lifecycle_state', 'source_url': source_url, 'locator': '正文明确为采购前/院内市场调研；确定性生命周期映射'},
        {'field_path': 'facts.notice_type', 'source_url': source_url, 'locator': '详情页标题/正文市场调研表述'},
        {'field_path': 'facts.published_at', 'source_url': source_url, 'locator': '详情页“时间”字段，并与官方详情URL日期一致'},
    ]
    if department:
        evidence.append({'field_path': 'facts.department', 'source_url': source_url, 'locator': '详情页来源或标题明确为设备科'})
    if registration_deadline:
        evidence.append({'field_path': 'facts.registration_deadline', 'source_url': source_url, 'locator': '正文截止/提交/填报时间，包含官方具体时分'})
    else:
        evidence.append({'field_path': 'facts.registration_deadline_date', 'source_url': source_url, 'locator': '正文截止/提交/填报日期；原文未公布具体时分'})
    if product_items:
        evidence.append({'field_path': 'facts.product_items', 'source_url': source_url, 'locator': '正文调研设备表格或详情页采购项目标题/科室用途'})
    if public_contact:
        evidence.append({'field_path': 'facts.public_contact', 'source_url': source_url, 'locator': '正文联系电话/设备科电话'})

    record = {
        'schema_version': '0.1',
        'opportunity_id': opportunity_id,
        'source': {
            'source_id': f'tjzxfc:{opportunity_id}',
            'source_type': 'OFFICIAL_INSTITUTION_NOTICE',
            'url': source_url,
            'observed_at': observed_at,
        },
        'facts': facts,
        'evidence': evidence,
    }
    if registration_deadline_date:
        record['quality_flags'] = ['DEADLINE_TIME_NOT_PUBLISHED']
    return validate_record(record)
