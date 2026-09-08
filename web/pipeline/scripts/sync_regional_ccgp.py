#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline.ccgp_detail import fetch_ccgp_detail_html  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import REGION_ZONE_IDS  # noqa: E402
from medical_channel_pipeline.state import merge_canonical_records  # noqa: E402
from sync_ccgp_query import (  # noqa: E402
    VERIFIED_NOTICE_ADAPTERS,
    discover_candidates,
    load_json_arrays,
    stable_id,
    write_json,
)

DEFAULT_PLAN = PIPELINE_ROOT / 'data' / 'multi_region_query_plan.json'
SHANGHAI = ZoneInfo('Asia/Shanghai')


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('--as-of must include timezone')
    return parsed


def load_plan(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != '0.1':
        raise ValueError('MULTI_REGION_QUERY_PLAN_INVALID')
    markets = payload.get('markets')
    if not isinstance(markets, list) or not markets:
        raise ValueError('MULTI_REGION_MARKETS_REQUIRED')
    seen_codes: set[str] = set()
    for market in markets:
        if not isinstance(market, dict):
            raise ValueError('MULTI_REGION_MARKET_INVALID')
        code = str(market.get('market_code') or '').strip().upper()
        name = str(market.get('name') or '').strip()
        admin_code = str(market.get('admin_code') or '').strip()
        zone_id = str(market.get('ccgp_zone_id') or '').strip()
        if code in seen_codes or not code or not name or len(admin_code) != 6:
            raise ValueError(f'MULTI_REGION_MARKET_INVALID:{market}')
        if REGION_ZONE_IDS.get(name) != zone_id:
            raise ValueError(f'MULTI_REGION_ZONE_MISMATCH:{name}:{zone_id}')
        if admin_code[:2] != zone_id:
            raise ValueError(f'MULTI_REGION_ADMIN_CODE_MISMATCH:{name}:{admin_code}:{zone_id}')
        seen_codes.add(code)
    keywords = payload.get('keywords')
    notice_types = payload.get('notice_types')
    if not isinstance(keywords, list) or not keywords or not all(isinstance(item, str) and item.strip() for item in keywords):
        raise ValueError('MULTI_REGION_KEYWORDS_INVALID')
    if not isinstance(notice_types, list) or not notice_types:
        raise ValueError('MULTI_REGION_NOTICE_TYPES_INVALID')
    if any(item not in VERIFIED_NOTICE_ADAPTERS for item in notice_types):
        raise ValueError('MULTI_REGION_NOTICE_TYPE_UNSUPPORTED')
    lookback_days = int(payload.get('lookback_days', 3))
    max_candidates = int(payload.get('max_candidates_per_market', 10))
    delay_seconds = float(payload.get('delay_seconds', 4.0))
    if not 1 <= lookback_days <= 14:
        raise ValueError('MULTI_REGION_LOOKBACK_INVALID')
    if not 1 <= max_candidates <= 30:
        raise ValueError('MULTI_REGION_MAX_CANDIDATES_INVALID')
    if delay_seconds < 3:
        raise ValueError('MULTI_REGION_DELAY_TOO_LOW')
    return {
        'markets': markets,
        'keywords': [item.strip() for item in keywords],
        'notice_types': list(notice_types),
        'lookback_days': lookback_days,
        'max_candidates_per_market': max_candidates,
        'delay_seconds': delay_seconds,
    }


def date_window(as_of: datetime, lookback_days: int) -> tuple[str, str]:
    local_date = as_of.astimezone(SHANGHAI).date()
    return (local_date - timedelta(days=lookback_days - 1)).isoformat(), local_date.isoformat()


def annotate_market(record: dict, market: dict) -> dict:
    facts = record.setdefault('facts', {})
    facts['market_code'] = str(market['market_code']).strip().upper()
    facts['market_name'] = str(market['name']).strip()
    facts['market_admin_code'] = str(market['admin_code']).strip()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Verified CCGP refresh for Beijing, Hebei, Liaoning, Jilin and Heilongjiang.'
    )
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    parser.add_argument('--as-of', default=None)
    parser.add_argument('--existing-records-input', action='append', type=Path, default=[])
    parser.add_argument('--records-output', required=True, type=Path)
    parser.add_argument('--report-output', required=True, type=Path)
    args = parser.parse_args()

    plan = load_plan(args.plan)
    as_of = parse_as_of(args.as_of)
    start_date, end_date = date_window(as_of, plan['lookback_days'])
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records = load_json_arrays(args.existing_records_input, label='existing regional records')

    new_records: list[dict] = []
    market_reports: list[dict] = []
    total_query_success = 0

    for market_index, market in enumerate(plan['markets']):
        market_name = str(market['name'])
        market_code = str(market['market_code']).upper()
        failures: list[dict] = []
        discovered_by_url: dict[str, tuple[str, object]] = {}
        query_count = len(plan['keywords']) * len(plan['notice_types'])

        for keyword_index, keyword in enumerate(plan['keywords']):
            discovered = discover_candidates(
                keyword=keyword,
                region=market_name,
                notice_types=plan['notice_types'],
                start_date=start_date,
                end_date=end_date,
                delay_seconds=plan['delay_seconds'],
                failures=failures,
            )
            for notice_type, candidate in discovered:
                discovered_by_url.setdefault(candidate.detail_url, (notice_type, candidate))
            if keyword_index + 1 < len(plan['keywords']):
                time.sleep(plan['delay_seconds'])

        discovery_failures = [item for item in failures if item.get('stage') == 'discovery_search']
        query_success = max(0, query_count - len(discovery_failures))
        total_query_success += query_success
        discovered = sorted(
            discovered_by_url.values(),
            key=lambda item: (getattr(item[1], 'published_at', None) or '', getattr(item[1], 'detail_url', '')),
            reverse=True,
        )
        selected = discovered[: plan['max_candidates_per_market']]
        market_new_count = 0

        for notice_type, candidate in selected:
            try:
                time.sleep(plan['delay_seconds'])
                html = fetch_ccgp_detail_html(candidate.detail_url)
                record = VERIFIED_NOTICE_ADAPTERS[notice_type](
                    html,
                    source_url=candidate.detail_url,
                    observed_at=observed_at,
                    opportunity_id=stable_id(f'ccgp_{market_code.lower()}', candidate.detail_url),
                )
                new_records.append(annotate_market(record, market))
                market_new_count += 1
            except Exception as exc:
                failures.append({
                    'stage': 'verified_detail',
                    'market_code': market_code,
                    'region': market_name,
                    'notice_type': notice_type,
                    'title': getattr(candidate, 'title', None),
                    'url': getattr(candidate, 'detail_url', None),
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                })

        market_reports.append({
            'market_code': market_code,
            'market_name': market_name,
            'admin_code': market['admin_code'],
            'ccgp_zone_id': market['ccgp_zone_id'],
            'planned_query_count': query_count,
            'discovery_success_count': query_success,
            'unique_candidate_count': len(discovered),
            'selected_candidate_count': len(selected),
            'new_verified_record_count': market_new_count,
            'failure_count': len(failures),
            'failures': failures,
        })
        if market_index + 1 < len(plan['markets']):
            time.sleep(plan['delay_seconds'])

    if total_query_success <= 0:
        raise RuntimeError('ALL_MULTI_REGION_DISCOVERY_QUERIES_FAILED')

    merged_records = merge_canonical_records(existing_records, new_records)
    report = {
        'schema_version': '0.1',
        'observed_at': observed_at,
        'start_date': start_date,
        'end_date': end_date,
        'markets': market_reports,
        'existing_record_count': len(existing_records),
        'new_verified_record_count': len(new_records),
        'merged_record_count': len(merged_records),
        'policy': {
            'business_market_is_explicit_not_geolocated': True,
            'market_admin_codes_are_validated_against_configured_ccgp_zone': True,
            'official_detail_required_before_publication': True,
            'cross_market_project_number_dedupe_is_forbidden': True,
            'regional_event_monitoring_deferred_until_composite_market_event_key_is_enabled': True,
            'rate_limit_bypass': False,
        },
    }
    write_json(args.records_output, merged_records)
    write_json(args.report_output, report)
    print(
        f'markets={len(plan["markets"])} queries_ok={total_query_success} '
        f'new_verified={len(new_records)} merged_records={len(merged_records)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
