from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .tjzyefy_procurement_intent import (
    OFFICIAL_FOLLOWUP_SOURCE_CEB,
    OFFICIAL_FOLLOWUP_SOURCE_PREFIX,
    OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
)

SHANGHAI = ZoneInfo('Asia/Shanghai')
MAX_INTENT_AGE_DAYS = 120
MAX_DIRECTED_TASKS = 6
MAX_CCGP_KEYWORDS = 4
GENERIC_KEYWORDS = {
    '采购',
    '项目',
    '设备',
    '医疗设备',
    '医疗器械',
    '耗材',
    '医用耗材',
    '服务',
}


def _quality_flags(record: dict[str, Any]) -> list[str]:
    value = record.get('quality_flags')
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _official_followup_sources(record: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for flag in _quality_flags(record):
        if not flag.startswith(OFFICIAL_FOLLOWUP_SOURCE_PREFIX):
            continue
        source = flag[len(OFFICIAL_FOLLOWUP_SOURCE_PREFIX):].strip()
        if source in {OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC, OFFICIAL_FOLLOWUP_SOURCE_CEB} and source not in result:
            result.append(source)
    return result


def _published_age_days(record: dict[str, Any], as_of: datetime) -> int | None:
    facts = record.get('facts')
    if not isinstance(facts, dict):
        return None
    raw = facts.get('published_at')
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        published = datetime.fromisoformat(raw.strip()).date()
    except ValueError:
        return None
    return (as_of.astimezone(SHANGHAI).date() - published).days


def _project_subject(record: dict[str, Any]) -> str | None:
    facts = record.get('facts')
    if not isinstance(facts, dict):
        return None
    raw = facts.get('project_name')
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    value = re.sub(r'^采购意向公告（[^）]+）\s*[-—]\s*', '', value)
    return value.strip() or None


def _search_keyword(record: dict[str, Any]) -> str | None:
    facts = record.get('facts')
    if not isinstance(facts, dict):
        return None
    items = facts.get('product_items')
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = item.get('raw_name')
            if not isinstance(raw, str):
                continue
            keyword = re.sub(r'\s+', '', raw).strip('：:，,。；; ')
            if 2 <= len(keyword) <= 60 and keyword not in GENERIC_KEYWORDS:
                return keyword
    subject = _project_subject(record)
    if not subject:
        return None
    keyword = re.sub(r'(?:采购项目|项目)$', '', re.sub(r'\s+', '', subject)).strip()
    if 2 <= len(keyword) <= 60 and keyword not in GENERIC_KEYWORDS:
        return keyword
    return None


def build_procurement_intent_followup_plan(
    records: list[dict[str, Any]],
    *,
    as_of: datetime,
    max_tasks: int = MAX_DIRECTED_TASKS,
    max_ccgp_keywords: int = MAX_CCGP_KEYWORDS,
) -> dict[str, Any]:
    if as_of.tzinfo is None:
        raise ValueError('FOLLOWUP_PLAN_AS_OF_TIMEZONE_REQUIRED')
    if not 1 <= max_tasks <= MAX_DIRECTED_TASKS:
        raise ValueError('FOLLOWUP_PLAN_TASK_CAP_INVALID')
    if not 1 <= max_ccgp_keywords <= MAX_CCGP_KEYWORDS:
        raise ValueError('FOLLOWUP_PLAN_CCGP_KEYWORD_CAP_INVALID')

    eligible: list[tuple[str, dict[str, Any]]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        facts = record.get('facts')
        if not isinstance(facts, dict) or facts.get('lifecycle_state') != 'PROCUREMENT_INTENT':
            continue
        age_days = _published_age_days(record, as_of)
        if age_days is None or age_days < 0 or age_days > MAX_INTENT_AGE_DAYS:
            continue
        opportunity_id = record.get('opportunity_id')
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            continue
        eligible.append((str(facts.get('published_at') or ''), record))

    eligible.sort(key=lambda item: (item[0], str(item[1].get('opportunity_id') or '')), reverse=True)

    tasks: list[dict[str, Any]] = []
    ccgp_keywords: list[str] = []
    seen_task_keys: set[tuple[str, str]] = set()

    for _, record in eligible:
        if len(tasks) >= max_tasks:
            break
        opportunity_id = str(record['opportunity_id']).strip()
        facts = record['facts']
        keyword = _search_keyword(record)
        subject = _project_subject(record)
        for source in _official_followup_sources(record):
            if len(tasks) >= max_tasks:
                break
            task_key = (opportunity_id, source)
            if task_key in seen_task_keys:
                continue
            seen_task_keys.add(task_key)

            executable = source == OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC and bool(keyword)
            task = {
                'intent_opportunity_id': opportunity_id,
                'official_followup_source': source,
                'buyer_name': facts.get('buyer_name'),
                'project_subject': subject,
                'search_keyword': keyword,
                'execution_adapter': 'CCGP_QUERY' if executable else None,
                'status': 'READY' if executable else 'UNSUPPORTED_SOURCE_ADAPTER',
            }
            tasks.append(task)
            if executable and keyword not in ccgp_keywords and len(ccgp_keywords) < max_ccgp_keywords:
                ccgp_keywords.append(keyword)

    ready_count = sum(1 for task in tasks if task['status'] == 'READY')
    unsupported_count = sum(1 for task in tasks if task['status'] == 'UNSUPPORTED_SOURCE_ADAPTER')
    return {
        'schema_version': '0.1',
        'tasks': tasks,
        'ccgp_keywords': ccgp_keywords,
        'task_count': len(tasks),
        'ready_task_count': ready_count,
        'unsupported_task_count': unsupported_count,
        'policy': {
            'verified_procurement_intent_only': True,
            'official_followup_source_flag_required': True,
            'maximum_intent_age_days': MAX_INTENT_AGE_DAYS,
            'maximum_tasks': max_tasks,
            'maximum_ccgp_keywords': max_ccgp_keywords,
            'tianjin_gpc_routes_to_existing_ccgp_discovery_only': True,
            'ceb_has_no_verified_adapter_yet': True,
            'task_is_discovery_hint_not_fact_evidence': True,
            'task_never_creates_lineage_or_crm_state': True,
            'no_followup_url_is_invented': True,
        },
    }
