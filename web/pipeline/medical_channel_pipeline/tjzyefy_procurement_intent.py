from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .channel_scope import is_medical_channel_relevant_text
from .tjzyefy_discovery import ALLOWED_HOSTS
from .validation import validate_record

HOSPITAL_NAME = '天津中医药大学第二附属医院'
EXPECTED_PROCUREMENT_WINDOW_UNSTRUCTURED = 'EXPECTED_PROCUREMENT_MONTH_WINDOW_UNSTRUCTURED'
EXPECTED_PROCUREMENT_WINDOW_TEXT_PREFIX = 'EXPECTED_PROCUREMENT_MONTH_WINDOW_TEXT='
OFFICIAL_FOLLOWUP_SOURCE_PREFIX = 'OFFICIAL_FOLLOWUP_SOURCE='
OFFICIAL_FOLLOWUP_SOURCE_CEB = 'CEB_PUBLIC_SERVICE'
OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC = 'TIANJIN_GPC'


class TjzyefyIntentParseError(ValueError):
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
        raise TjzyefyIntentParseError(code)


def _extract_published_date(text: str) -> str:
    match = re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b', text)
    if not match:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_PUBLISHED_DATE_NOT_FOUND')
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_PUBLISHED_DATE_INVALID') from exc


def _split_product_names(raw: str) -> list[str]:
    value = re.sub(r'\s+', '', raw).strip('：:，,。；; ')
    value = re.sub(r'(?:采购项目(?:服务)?|项目)$', '', value)
    names = [part.strip('：:，,。；; ') for part in re.split(r'[、，,]', value)]
    result: list[str] = []
    for name in names:
        name = re.sub(r'等(?:医疗设备|医用耗材|耗材|试剂|设备)?$', '', name).strip()
        if name and name not in result:
            result.append(name)
    return result


def _extract_product_items(text: str, title: str) -> list[dict[str, Any]]:
    raw: str | None = None
    body = re.search(r'我院将于近期对(?:天津中医药大学第二附属医院)?(.{1,300}?)进行采购', text)
    if body:
        raw = body.group(1)
    if not raw:
        compact_title = _normalize(title)
        title_match = re.search(r'[-—](.+?)(?:采购项目|项目)$', compact_title)
        if title_match:
            raw = title_match.group(1)
    if not raw:
        return []
    return [
        {'raw_name': name, 'category': None, 'quantity': None, 'specification': None}
        for name in _split_product_names(raw)
    ]


def _extract_contact(text: str) -> dict[str, str | None] | None:
    phone_match = re.search(r'联系电话\s*[：:]?\s*(0?\d{2,3}-?\d{7,8}|\d{7,12})', text)
    name_match = re.search(r'联系人\s*[：:]?\s*([^\s，,。；;、]{1,12})', text)
    if not phone_match and not name_match:
        return None
    return {
        'name': name_match.group(1) if name_match else None,
        'title': None,
        'phone': phone_match.group(1) if phone_match else None,
        'email': None,
    }


def _extract_expected_procurement_month_window(text: str) -> str | None:
    match = re.search(
        r'预计采购时间\s*(?:为|[:：])?\s*(20\d{2}\s*年\s*\d{1,2}(?:\s*[-—至]\s*\d{1,2})?\s*月)',
        text,
    )
    if not match:
        return None
    return re.sub(r'\s+', '', match.group(1))


def _extract_official_followup_sources(text: str) -> list[str]:
    # Only trust a platform reference when it is bound to the hospital's
    # explicit project-specific follow-up sentence. A platform name elsewhere
    # in navigation/footer text is not a procurement-source instruction.
    match = re.search(
        r'本项目具体招标信息请于近期关注\s*[：:]?\s*(.{1,220}?)(?=联系电话|联系人|$)',
        text,
    )
    if not match:
        return []
    instruction = _normalize(match.group(1)).lower()
    result: list[str] = []
    if '中国招标投标公共服务平台' in instruction or 'cebpubservice.com' in instruction:
        result.append(OFFICIAL_FOLLOWUP_SOURCE_CEB)
    if (
        '天津市政采网' in instruction
        or '天津市政采中心' in instruction
        or '天津市政府采购中心' in instruction
        or 'tjgpc.zwfwb.tj.gov.cn' in instruction
    ):
        result.append(OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC)
    return result


def _product_categories(title: str) -> list[str]:
    compact = _normalize(title)
    if '医用耗材' in compact or '耗材' in compact or '试剂' in compact:
        return ['医用耗材']
    if '医疗设备' in compact or '医疗器械' in compact:
        return ['医疗设备']
    return []


def parse_tjzyefy_procurement_intent(
    html: str,
    *,
    source_url: str,
    index_url: str,
    index_published_at: str,
    expected_title: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_official_url(source_url, code='TJZYEFY_INTENT_SOURCE_HOST_REJECTED')
    _assert_official_url(index_url, code='TJZYEFY_INTENT_INDEX_HOST_REJECTED')
    if urlparse(source_url).hostname != urlparse(index_url).hostname:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_INDEX_DETAIL_HOST_MISMATCH')
    try:
        date.fromisoformat(index_published_at)
    except ValueError as exc:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_INDEX_PUBLISHED_DATE_INVALID') from exc

    text = _visible_text(html)
    if HOSPITAL_NAME not in text:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_HOSPITAL_IDENTITY_NOT_FOUND')
    if _normalize(expected_title) not in _normalize(text):
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_TITLE_MISMATCH')
    if '采购意向公告' not in expected_title or '采购意向公告' not in text[:600]:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_NOTICE_TYPE_NOT_FOUND')
    if '欢迎' not in text or ('供应商咨询' not in text and '服务商咨询' not in text):
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_SUPPLIER_CONSULTATION_NOT_FOUND')

    published_at = _extract_published_date(text)
    if published_at != index_published_at:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_PUBLISHED_DATE_MISMATCH')

    product_items = _extract_product_items(text, expected_title)
    categories = _product_categories(expected_title)
    scope_probe = '\n'.join(
        [expected_title, *categories, *[str(item.get('raw_name') or '') for item in product_items]]
    )
    if not is_medical_channel_relevant_text(scope_probe):
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_NON_MEDICAL')
    if not product_items:
        raise TjzyefyIntentParseError('TJZYEFY_INTENT_PRODUCT_ITEMS_NOT_FOUND')

    public_contact = _extract_contact(text)
    flags: list[str] = []
    expected_window = _extract_expected_procurement_month_window(text)
    if expected_window:
        # Preserve the exact official month/month-range wording for display and
        # audit. Do not convert it into an invented day or timestamp because
        # the canonical exact-datetime field is intentionally left empty.
        flags.append(EXPECTED_PROCUREMENT_WINDOW_UNSTRUCTURED)
        flags.append(f'{EXPECTED_PROCUREMENT_WINDOW_TEXT_PREFIX}{expected_window}')
    for followup_source in _extract_official_followup_sources(text):
        flags.append(f'{OFFICIAL_FOLLOWUP_SOURCE_PREFIX}{followup_source}')

    facts: dict[str, Any] = {
        'project_number': None,
        'project_name': expected_title,
        'buyer_name': HOSPITAL_NAME,
        'hospital_name': HOSPITAL_NAME,
        'department': None,
        'region': '天津市',
        'lifecycle_state': 'PROCUREMENT_INTENT',
        'notice_type': '采购意向公告',
        'published_at': published_at,
        'registration_deadline': None,
        'registration_deadline_date': None,
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
        {'field_path': 'facts.project_name', 'source_url': source_url, 'locator': '官方采购意向详情页标题与公告通知列表标题一致'},
        {'field_path': 'facts.buyer_name', 'source_url': source_url, 'locator': '天津中医药大学第二附属医院官方页面主体'},
        {'field_path': 'facts.hospital_name', 'source_url': source_url, 'locator': '天津中医药大学第二附属医院官方页面主体'},
        {'field_path': 'facts.region', 'source_url': source_url, 'locator': '天津中医药大学第二附属医院官方页面主体'},
        {'field_path': 'facts.lifecycle_state', 'source_url': source_url, 'locator': '标题与正文明确为采购意向公告；确定性映射为PROCUREMENT_INTENT'},
        {'field_path': 'facts.notice_type', 'source_url': source_url, 'locator': '详情页标题明确采购意向公告'},
        {'field_path': 'facts.published_at', 'source_url': source_url, 'locator': '详情页官方发布时间，并与详情URL日期一致'},
        {'field_path': 'facts.product_items', 'source_url': source_url, 'locator': '正文“近期对…进行采购”及详情页项目标题明确采购对象'},
    ]
    if categories:
        evidence.append({'field_path': 'facts.product_categories', 'source_url': source_url, 'locator': '详情页标题明确医疗设备或医用耗材/试剂类别'})
    if public_contact:
        evidence.append({'field_path': 'facts.public_contact', 'source_url': source_url, 'locator': '正文欢迎供应商咨询并公布联系人/联系电话'})

    record: dict[str, Any] = {
        'schema_version': '0.1',
        'opportunity_id': opportunity_id,
        'source': {
            'source_id': f'tjzyefy-intent:{opportunity_id}',
            'source_type': 'OFFICIAL_INSTITUTION_NOTICE',
            'url': source_url,
            'observed_at': observed_at,
        },
        'facts': facts,
        'evidence': evidence,
    }
    if flags:
        record['quality_flags'] = flags
    return validate_record(record)
