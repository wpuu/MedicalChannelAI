#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline.ccgp_detail import fetch_ccgp_detail_html  # noqa: E402
from medical_channel_pipeline.ccgp_discovery import (  # noqa: E402
    CCGP_SEARCH_URL,
    RATE_LIMIT_MARKERS,
    REGION_ZONE_IDS,
    build_search_url,
    is_primary_opportunity_candidate,
    parse_search_html,
)
from medical_channel_pipeline.regional_candidate import (  # noqa: E402
    regional_candidate_priority,
    regional_candidate_selection_key,
    regional_candidate_skip_reason,
)
from medical_channel_pipeline.state import merge_canonical_records  # noqa: E402
from sync_ccgp_query import (  # noqa: E402
    VERIFIED_NOTICE_ADAPTERS,
    load_json_arrays,
    stable_id,
    write_json,
)

DEFAULT_PLAN = PIPELINE_ROOT / 'data' / 'multi_region_query_plan.json'
SHANGHAI = ZoneInfo('Asia/Shanghai')
NATIONAL_FALLBACK_MAX_PAGES = 3
_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


SEARCH_TIMEOUT_SECONDS = 90
WARMUP_TIMEOUT_SECONDS = 30


class CcgpSearchSession:
    def __init__(self, *, timeout_seconds: int = SEARCH_TIMEOUT_SECONDS) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.warmed = False
        self.timeout_seconds = int(timeout_seconds)

    def _read(self, url: str, *, timeout: int) -> str:
        request = urllib.request.Request(url, headers=_BROWSER_HEADERS)
        with self.opener.open(request, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset()
        if charset:
            return raw.decode(charset, errors='replace')
        for candidate in ('utf-8', 'gb18030'):
            try:
                return raw.decode(candidate)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace')

    def warmup(self) -> None:
        if self.warmed:
            return
        try:
            self._read('https://www.ccgp.gov.cn/', timeout=min(WARMUP_TIMEOUT_SECONDS, self.timeout_seconds))
        except Exception:
            # Search can still work if the homepage warm-up is temporarily unavailable.
            pass
        time.sleep(1.0)
        self.warmed = True

    def fetch(self, url: str) -> str:
        if not url.startswith(CCGP_SEARCH_URL):
            raise ValueError('CCGP_SEARCH_URL_REQUIRED')
        self.warmup()
        html = self._read(url, timeout=self.timeout_seconds)
        if any(marker in html for marker in RATE_LIMIT_MARKERS):
            raise RuntimeError('CCGP_RATE_LIMITED')
        return html


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


def candidate_market_code(region: str | None, markets: list[dict]) -> str | None:
    normalized = ''.join(str(region or '').split())
    if not normalized:
        return None
    for market in markets:
        name = str(market['name']).strip()
        aliases = {name, f'{name}省', f'{name}市'}
        if normalized in aliases or any(normalized.startswith(alias) for alias in aliases):
            return str(market['market_code']).strip().upper()
    return None


def fetch_candidates_page(
    session: CcgpSearchSession,
    *,
    keyword: str,
    notice_type: str,
    start_date: str,
    end_date: str,
    region: str | None,
    page_index: int,
) -> list[tuple[str, object]]:
    url = build_search_url(
        keyword=keyword,
        notice_type=notice_type,
        page_index=page_index,
        start_date=start_date,
        end_date=end_date,
        region=region,
    )
    html = session.fetch(url)
    return [
        (notice_type, candidate)
        for candidate in parse_search_html(html, keyword=keyword)
        if is_primary_opportunity_candidate(candidate)
    ]


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
    existing_source_urls = {
        str((record.get('source') or {}).get('url') or '')
        for record in existing_records
        if isinstance(record, dict) and str((record.get('source') or {}).get('url') or '')
    }
    session = CcgpSearchSession()

    markets = plan['markets']
    market_by_code = {str(item['market_code']).upper(): item for item in markets}
    market_candidates: dict[str, dict[str, tuple[str, object]]] = {
        code: {} for code in market_by_code
    }
    market_failures: dict[str, list[dict]] = {code: [] for code in market_by_code}
    market_skips: dict[str, dict[str, dict]] = {code: {} for code in market_by_code}
    scoped_success: dict[str, int] = {code: 0 for code in market_by_code}

    def record_candidate_skip(code: str, notice_type: str, candidate: object, reason: str) -> None:
        detail_url = str(getattr(candidate, 'detail_url', '') or '')
        if not detail_url:
            return
        market_skips[code].setdefault(detail_url, {
            'stage': 'candidate_classification',
            'market_code': code,
            'reason': reason,
            'notice_type': notice_type,
            'candidate_notice_type': getattr(candidate, 'notice_type', None),
            'candidate_region': getattr(candidate, 'region', None),
            'title': getattr(candidate, 'title', None),
            'url': detail_url,
        })
    scoped_region_mismatches: dict[str, int] = {code: 0 for code in market_by_code}

    # Province-scoped search is only discovery. Do not trust the request parameter
    # as proof of geography: every returned row must independently carry an official
    # region label that maps back to the requested market before it can be selected.
    for market in markets:
        code = str(market['market_code']).upper()
        name = str(market['name'])
        for keyword in plan['keywords']:
            for notice_type in plan['notice_types']:
                try:
                    items = fetch_candidates_page(
                        session,
                        keyword=keyword,
                        notice_type=notice_type,
                        start_date=start_date,
                        end_date=end_date,
                        region=name,
                        page_index=1,
                    )
                    scoped_success[code] += 1
                    for item_notice_type, candidate in items:
                        actual_code = candidate_market_code(getattr(candidate, 'region', None), markets)
                        if actual_code != code:
                            scoped_region_mismatches[code] += 1
                            continue
                        skip_reason = regional_candidate_skip_reason(candidate)
                        if skip_reason:
                            record_candidate_skip(code, item_notice_type, candidate, skip_reason)
                            continue
                        market_candidates[code].setdefault(
                            candidate.detail_url,
                            (item_notice_type, candidate),
                        )
                except Exception as exc:
                    market_failures[code].append({
                        'stage': 'scoped_discovery',
                        'market_code': code,
                        'region': name,
                        'keyword': keyword,
                        'notice_type': notice_type,
                        'error': type(exc).__name__,
                        'message': str(exc)[:300],
                    })
                time.sleep(plan['delay_seconds'])

    empty_codes = {code for code, items in market_candidates.items() if not items}
    fallback_query_success = 0
    fallback_failures: list[dict] = []

    # If province-scoped search produces no region-verified candidate for a market,
    # fall back to a bounded national search and distribute rows solely by the
    # official region label on each result. Search rows remain discovery-only;
    # publication still requires parsing the official detail page.
    if empty_codes:
        for keyword in plan['keywords']:
            for notice_type in plan['notice_types']:
                for page_index in range(1, NATIONAL_FALLBACK_MAX_PAGES + 1):
                    try:
                        items = fetch_candidates_page(
                            session,
                            keyword=keyword,
                            notice_type=notice_type,
                            start_date=start_date,
                            end_date=end_date,
                            region=None,
                            page_index=page_index,
                        )
                        fallback_query_success += 1
                    except Exception as exc:
                        fallback_failures.append({
                            'stage': 'national_fallback_discovery',
                            'keyword': keyword,
                            'notice_type': notice_type,
                            'page_index': page_index,
                            'error': type(exc).__name__,
                            'message': str(exc)[:300],
                        })
                        break
                    if not items:
                        break
                    for item_notice_type, candidate in items:
                        actual_code = candidate_market_code(getattr(candidate, 'region', None), markets)
                        if actual_code not in empty_codes:
                            continue
                        skip_reason = regional_candidate_skip_reason(candidate)
                        if skip_reason:
                            record_candidate_skip(actual_code, item_notice_type, candidate, skip_reason)
                            continue
                        market_candidates[actual_code].setdefault(
                            candidate.detail_url,
                            (item_notice_type, candidate),
                        )
                    time.sleep(plan['delay_seconds'])
                time.sleep(plan['delay_seconds'])

    if sum(scoped_success.values()) + fallback_query_success <= 0:
        raise RuntimeError('ALL_MULTI_REGION_DISCOVERY_QUERIES_FAILED')

    new_records: list[dict] = []
    market_reports: list[dict] = []

    for code, discovered_by_url in market_candidates.items():
        market = market_by_code[code]
        discovered = sorted(
            discovered_by_url.values(),
            key=lambda item: regional_candidate_selection_key(item[1], existing_source_urls),
            reverse=True,
        )
        selected = discovered[: plan['max_candidates_per_market']]
        selected_candidates = [
            {
                'title': getattr(candidate, 'title', None),
                'url': getattr(candidate, 'detail_url', None),
                'published_at': getattr(candidate, 'published_at', None),
                'priority': regional_candidate_priority(candidate),
                'was_existing_verified_url': str(getattr(candidate, 'detail_url', '') or '') in existing_source_urls,
            }
            for _, candidate in selected
        ]
        market_new_count = 0

        for notice_type, candidate in selected:
            # Final geography guard immediately before detail verification.
            if candidate_market_code(getattr(candidate, 'region', None), markets) != code:
                market_failures[code].append({
                    'stage': 'pre_detail_market_guard',
                    'market_code': code,
                    'candidate_region': getattr(candidate, 'region', None),
                    'url': getattr(candidate, 'detail_url', None),
                })
                continue
            try:
                time.sleep(plan['delay_seconds'])
                html = fetch_ccgp_detail_html(candidate.detail_url)
                record = VERIFIED_NOTICE_ADAPTERS[notice_type](
                    html,
                    source_url=candidate.detail_url,
                    observed_at=observed_at,
                    opportunity_id=stable_id(f'ccgp_{code.lower()}', candidate.detail_url),
                )
                new_records.append(annotate_market(record, market))
                market_new_count += 1
            except Exception as exc:
                market_failures[code].append({
                    'stage': 'verified_detail',
                    'market_code': code,
                    'region': market['name'],
                    'notice_type': notice_type,
                    'candidate_region': getattr(candidate, 'region', None),
                    'title': getattr(candidate, 'title', None),
                    'url': getattr(candidate, 'detail_url', None),
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                })

        market_reports.append({
            'market_code': code,
            'market_name': market['name'],
            'admin_code': market['admin_code'],
            'ccgp_zone_id': market['ccgp_zone_id'],
            'scoped_query_success_count': scoped_success[code],
            'scoped_region_mismatch_count': scoped_region_mismatches[code],
            'national_fallback_used': code in empty_codes,
            'skipped_candidate_count': len(market_skips[code]),
            'skipped_candidates': sorted(market_skips[code].values(), key=lambda item: (item['reason'], item['url'])),
            'unique_candidate_count': len(discovered),
            'selected_candidate_count': len(selected),
            'selected_unseen_candidate_count': sum(
                1 for item in selected_candidates if not item['was_existing_verified_url']
            ),
            'selected_existing_candidate_count': sum(
                1 for item in selected_candidates if item['was_existing_verified_url']
            ),
            'selected_candidates': selected_candidates,
            'new_verified_record_count': market_new_count,
            'failure_count': len(market_failures[code]),
            'failures': market_failures[code],
        })
        print(
            f'market={code} scoped_ok={scoped_success[code]} '
            f'scoped_mismatch={scoped_region_mismatches[code]} fallback={code in empty_codes} '
            f'candidates={len(discovered)} selected={len(selected)} verified={market_new_count} '
            f'failures={len(market_failures[code])}'
        )

    merged_records = merge_canonical_records(existing_records, new_records)
    report = {
        'schema_version': '0.1',
        'observed_at': observed_at,
        'start_date': start_date,
        'end_date': end_date,
        'markets': market_reports,
        'national_fallback_query_success_count': fallback_query_success,
        'national_fallback_failure_count': len(fallback_failures),
        'national_fallback_failures': fallback_failures,
        'existing_record_count': len(existing_records),
        'new_verified_record_count': len(new_records),
        'merged_record_count': len(merged_records),
        'policy': {
            'business_market_is_explicit_not_geolocated': True,
            'market_admin_codes_are_validated_against_configured_ccgp_zone': True,
            'scoped_query_parameter_is_not_geography_evidence': True,
            'every_candidate_requires_official_search_result_region_match': True,
            'scoped_empty_does_not_mean_no_market_activity': True,
            'national_fallback_uses_official_search_result_region_only': True,
            'national_fallback_max_pages_per_query': NATIONAL_FALLBACK_MAX_PAGES,
            'official_detail_required_before_publication': True,
            'candidate_prefilter_only_rejects_explicit_exclusions': True,
            'candidate_detail_budget_uses_recall_preserving_priority': True,
            'candidate_detail_budget_prioritizes_unseen_urls_before_rechecks': True,
            'cross_market_project_number_dedupe_is_forbidden': True,
            'regional_event_monitoring_deferred_until_composite_market_event_key_is_enabled': True,
            'rate_limit_bypass': False,
            'minimum_request_delay_seconds': plan['delay_seconds'],
        },
    }
    write_json(args.records_output, merged_records)
    write_json(args.report_output, report)
    print(
        f'markets={len(markets)} scoped_queries_ok={sum(scoped_success.values())} '
        f'fallback_queries_ok={fallback_query_success} new_verified={len(new_records)} '
        f'merged_records={len(merged_records)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
