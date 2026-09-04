from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .channel_scope import is_medical_channel_relevant_text
from .validation import validate_record

ALLOWED_HOSTS = {'tjzyefy.com', 'www.tjzyefy.com'}
HOSPITAL_NAME = '天津中医药大学第二附属医院'


class TjzyefyParseError(ValueError):
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


def _normalize(value: str) -> str:
    return re.sub(r'\s+', '', value)


def _assert_official_url(url: str, *, code: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise TjzyefyParseError(code)


def _extract_published_date(text: str) -> str:
    match = re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b', text)
    if not match:
        raise TjzyefyParseError('TJZYEFY_PUBLISHED_DATE_NOT_FOUND')
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise TjzyefyParseError('TJZYEFY_PUBLISHED_DATE_INVALID') from exc


def _split_product_names(raw: str) -> list[str]:
    value = re.sub(r'\s+', '', raw).strip('：:，,。；; ')
    if not value:
        return []
    value = re.sub(r'(?:采购项目(?:服务)?|项目)$', '', value)
    names = [part.strip('：:，,。；; ') for part in re.split(r'[、，,]', value)]
    result: list[str] = []
    for name in names:
        name = re.sub(r'等(?:医疗设备|医用耗材|耗材|试剂)?$', '', name).strip()
        if name and name not in result:
            result.append(name)
    return result


def _extract_product_items(text: str, title: str) -> list[dict[str, Any]]:
    raw: str | None = None
    body_match = re.search(r'我院拟对(.{1,500}?)进行院内调研', text)
    if body_match:
        raw = body_match.group(1)
    if not raw:
        compact_title = _normalize(title)
        title_match = re.search(r'[-—](.+?)(?:医疗设备采购项目|医用耗材(?:（试剂）)?采购项目|耗材采购项目|试剂采购项目)', compact_title)
        if title_match:
            raw = title_match.group(1)
    if not raw:
        return []
    return [
        {'raw_name': name, 'category': None, 'quantity': None, 'specification': None}
        for name in _split_product_names(raw)
    ]


def _extract_registration_deadline(text: str) -> tuple[str | None, str | None]:
    compact = re.sub(r'(?<=\d)\s+(?=\d)', '', text)
    section_match = re.search(r'报名时间\s*[：:]?\s*([^。；;]{1,100})', compact)
    if not section_match:
        raise TjzyefyParseError('TJZYEFY_REGISTRATION_WINDOW_NOT_FOUND')
    section = section_match.group(1)
    dates = re.findall(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?', section)
    if not dates:
        raise TjzyefyParseError('TJZYEFY_REGISTRATION_DATE_NOT_FOUND')
    year, month, day = (int(part) for part in dates[-1])
    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise TjzyefyParseError('TJZYEFY_REGISTRATION_DATE_INVALID') from exc
    tail = section[section.rfind(str(dates[-1][2])) + len(str(dates[-1][2])):]
    time_match = re.search(r'(\d{1,2})\s*[：:]\s*(\d{2})', tail)
    if time_match:
        hour, minute = (int(part) for part in time_match.groups())
        if hour > 23 or minute > 59:
            raise TjzyefyParseError('TJZYEFY_REGISTRATION_TIME_INVALID')
        return f'{parsed.isoformat()}T{hour:02d}:{minute:02d}:00+08:00', None
    return None, parsed.isoformat()


def _extract_contact(text: str) -> dict[str, str | None] | None:
    phone_match = re.search(r'联系电话\s*[：:]?\s*(0?\d{2,3}-?\d{7,8}|\d{7,12})', text)
    email_match = re.search(r'(?:电子邮箱|邮箱)\s*[：:]?\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', text)
    name_match = re.search(r'联系人\s*[：:]?\s*([^\s，。；;]{1,12})', text)
    if not phone_match and not email_match:
        return None
    return {
        'name': name_match.group(1) if name_match else None,
        'title': '国有资产管理科' if '国有资产管理科' in text else None,
        'phone': phone_match.group(1) if phone_match else None,
        'email': email_match.group(1) if email_match else None,
    }


def _product_categories(title: str) -> list[str]:
    compact = _normalize(title)
    if '医用耗材' in compact or '耗材' in compact or '试剂' in compact:
        return ['医用耗材']
    if '医疗设备' in compact or '医疗器械' in compact:
        return ['医疗设备']
    return []


def parse_tjzyefy_market_research(
    html: str,
    *,
    source_url: str,
    index_url: str,
    index_published_at: str,
    expected_title: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_official_url(source_url, code='TJZYEFY_SOURCE_HOST_REJECTED')
    _assert_official_url(index_url, code='TJZYEFY_INDEX_HOST_REJECTED')
    if urlparse(source_url).hostname != urlparse(index_url).hostname:
        raise TjzyefyParseError('TJZYEFY_INDEX_DETAIL_HOST_MISMATCH')
    try:
        date.fromisoformat(index_published_at)
    except ValueError as exc:
        raise TjzyefyParseError('TJZYEFY_INDEX_PUBLISHED_DATE_INVALID') from exc

    text = _visible_text(html)
    if HOSPITAL_NAME not in text:
        raise TjzyefyParseError('TJZYEFY_HOSPITAL_IDENTITY_NOT_FOUND')
    if _normalize(expected_title) not in _normalize(text):
        raise TjzyefyParseError('TJZYEFY_TITLE_MISMATCH')
    if '采购意向公告' in expected_title or '采购意向公告' in text[:500]:
        raise TjzyefyParseError('TJZYEFY_PROCUREMENT_INTENT_NOT_SUPPORTED')
    if '调研' not in expected_title or '院内调研' not in text:
        raise TjzyefyParseError('TJZYEFY_NOT_MARKET_RESEARCH')

    published_at = _extract_published_date(text)
    if published_at != index_published_at:
        raise TjzyefyParseError('TJZYEFY_PUBLISHED_DATE_MISMATCH')

    product_items = _extract_product_items(text, expected_title)
    categories = _product_categories(expected_title)
    scope_probe = '\n'.join(
        [expected_title, *categories, *[str(item.get('raw_name') or '') for item in product_items]]
    )
    if not is_medical_channel_relevant_text(scope_probe):
        raise TjzyefyParseError('TJZYEFY_NON_MEDICAL_RESEARCH')
    if not product_items:
        raise TjzyefyParseError('TJZYEFY_PRODUCT_ITEMS_NOT_FOUND')

    registration_deadline, registration_deadline_date = _extract_registration_deadline(text)
    public_contact = _extract_contact(text)
    notice_type = '医用耗材（试剂）调研公告' if ('耗材' in expected_title or '试剂' in expected_title) else '院内调研公告'

    facts: dict[str, Any] = {
        'project_number': None,
        'project_name': expected_title,
        'buyer_name': HOSPITAL_NAME,
        'hospital_name': HOSPITAL_NAME,
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
        'budget_cny': None,
        'procurement_method': None,
        'product_categories': categories,
        'product_items': product_items,
        'public_contact': public_contact,
    }
    evidence: list[dict[str, str]] = [
        {'field_path': 'facts.project_name', 'source_url': source_url, 'locator': '官方公告详情页标题与公告通知列表标题一致'},
        {'field_path': 'facts.buyer_name', 'source_url': source_url, 'locator': '天津中医药大学第二附属医院官方页面主体'},
        {'field_path': 'facts.hospital_name', 'source_url': source_url, 'locator': '天津中医药大学第二附属医院官方页面主体'},
        {'field_path': 'facts.region', 'source_url': source_url, 'locator': '天津中医药大学第二附属医院官方页面主体'},
        {'field_path': 'facts.lifecycle_state', 'source_url': source_url, 'locator': '正文明确为院内调研；确定性生命周期映射'},
        {'field_path': 'facts.notice_type', 'source_url': source_url, 'locator': '详情页标题明确调研公告类型'},
        {'field_path': 'facts.published_at', 'source_url': source_url, 'locator': '详情页官方发布时间，并与详情URL日期一致'},
        {'field_path': 'facts.product_items', 'source_url': source_url, 'locator': '正文“我院拟对…进行院内调研”明确产品/设备/维保对象'},
    ]
    if categories:
        evidence.append({'field_path': 'facts.product_categories', 'source_url': source_url, 'locator': '详情页标题明确医疗设备或医用耗材/试剂类别'})
    if registration_deadline:
        evidence.append({'field_path': 'facts.registration_deadline', 'source_url': source_url, 'locator': '正文报名时间结束日期及官方具体时分'})
    else:
        evidence.append({'field_path': 'facts.registration_deadline_date', 'source_url': source_url, 'locator': '正文报名时间结束日期；原文未公布具体时分'})
    if public_contact:
        evidence.append({'field_path': 'facts.public_contact', 'source_url': source_url, 'locator': '正文报名邮箱/联系人/联系电话/国有资产管理科'})

    record: dict[str, Any] = {
        'schema_version': '0.1',
        'opportunity_id': opportunity_id,
        'source': {
            'source_id': f'tjzyefy:{opportunity_id}',
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
