#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline.state import merge_canonical_records  # noqa: E402
from medical_channel_pipeline.teda_discovery import (  # noqa: E402
    TedaCandidate,
    fetch_teda_page,
    index_page_url,
    parse_teda_index_html,
    stable_opportunity_id,
)
from medical_channel_pipeline.teda_market_research import (  # noqa: E402
    TedaParseError,
    parse_teda_market_research,
)

SHANGHAI = ZoneInfo('Asia/Shanghai')
MIN_REQUEST_DELAY_SECONDS = 3.0
FETCH_ATTEMPTS = 2
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}
UNSUPPORTED_DETAIL_CODES = {'TEDA_MEDICAL_EARLY_SIGNAL_NOT_VERIFIED'}


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('--as-of must include timezone')
    return parsed


def load_json_arrays(paths: list[Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, list):
            raise ValueError(f'input must contain a JSON array: {path}')
        records.extend(payload)
    return records


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def is_retryable_fetch_error(exc: Exception) -> bool:
    message = str(exc)
    if message == 'TEDA_NETWORK_ERROR':
        return True
    match = re.fullmatch(r'TEDA_HTTP_(\d{3})', message)
    return bool(match and int(match.group(1)) in RETRYABLE_HTTP_CODES)


def fetch_page_with_retry(
    url: str,
    *,
    delay_seconds: float,
    attempts: int = FETCH_ATTEMPTS,
) -> str:
    if attempts < 1:
        raise ValueError('attempts must be >= 1')
    for attempt in range(1, attempts + 1):
        try:
            return fetch_teda_page(url)
        except RuntimeError as exc:
            if attempt >= attempts or not is_retryable_fetch_error(exc):
                raise
            time.sleep(delay_seconds)
    raise AssertionError('unreachable')


def discover_candidates(
    *,
    index_pages: int,
    delay_seconds: float,
) -> list[TedaCandidate]:
    result: list[TedaCandidate] = []
    seen: set[str] = set()
    for page in range(1, index_pages + 1):
        if page > 1:
            time.sleep(delay_seconds)
        url = index_page_url(page)
        html = fetch_page_with_retry(url, delay_seconds=delay_seconds)
        for candidate in parse_teda_index_html(html, index_url=url):
            opportunity_id = stable_opportunity_id(candidate.detail_url)
            if opportunity_id in seen:
                continue
            seen.add(opportunity_id)
            result.append(candidate)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Sync verified TEDA Hospital medical-device demand research and pre-procurement argument notices.'
    )
    parser.add_argument('--as-of', default=None, help='ISO-8601 timestamp with timezone; defaults to now.')
    parser.add_argument('--lookback-days', type=int, default=30)
    parser.add_argument('--index-pages', type=int, default=4)
    parser.add_argument('--max-candidates', type=int, default=20)
    parser.add_argument('--delay-seconds', type=float, default=MIN_REQUEST_DELAY_SECONDS)
    parser.add_argument('--existing-records-input', action='append', type=Path, default=[])
    parser.add_argument('--records-output', required=True, type=Path)
    parser.add_argument('--report-output', required=True, type=Path)
    args = parser.parse_args()

    if not 1 <= args.lookback_days <= 90:
        raise ValueError('--lookback-days must be between 1 and 90')
    if not 1 <= args.index_pages <= 10:
        raise ValueError('--index-pages must be between 1 and 10')
    if not 1 <= args.max_candidates <= 50:
        raise ValueError('--max-candidates must be between 1 and 50')
    if args.delay_seconds < MIN_REQUEST_DELAY_SECONDS:
        raise ValueError(f'--delay-seconds must be >= {MIN_REQUEST_DELAY_SECONDS:g}')

    as_of = parse_as_of(args.as_of)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=args.lookback_days - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records = load_json_arrays(args.existing_records_input)

    try:
        discovered = discover_candidates(
            index_pages=args.index_pages,
            delay_seconds=args.delay_seconds,
        )
    except Exception as exc:
        report = {
            'schema_version': '0.1',
            'observed_at': observed_at,
            'source': 'TEDA_HOSPITAL_PROCUREMENT_INDEX',
            'index_pages': args.index_pages,
            'publish_allowed': False,
            'publish_gate_reason': 'INDEX_DISCOVERY_FAILED',
            'failure_count': 1,
            'failures': [
                {
                    'stage': 'index_discovery',
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            ],
        }
        write_json(args.report_output, report)
        print('TEDA index discovery failed; refusing to mark hospital-source state fresh', file=sys.stderr)
        return 2

    new_records: list[dict] = []
    failures: list[dict] = []
    unsupported: list[dict] = []
    out_of_window_count = 0
    for candidate in discovered[: args.max_candidates]:
        time.sleep(args.delay_seconds)
        try:
            detail_html = fetch_page_with_retry(
                candidate.detail_url,
                delay_seconds=args.delay_seconds,
            )
            record = parse_teda_market_research(
                detail_html,
                source_url=candidate.detail_url,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=stable_opportunity_id(candidate.detail_url),
            )
            published_at = datetime.fromisoformat(record['facts']['published_at']).date()
            if not start_date <= published_at <= local_date:
                out_of_window_count += 1
                continue
            new_records.append(record)
        except TedaParseError as exc:
            if str(exc) in UNSUPPORTED_DETAIL_CODES:
                unsupported.append(
                    {
                        'title': candidate.title,
                        'url': candidate.detail_url,
                        'reason': str(exc),
                    }
                )
                continue
            failures.append(
                {
                    'stage': 'verified_detail',
                    'title': candidate.title,
                    'url': candidate.detail_url,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )
        except Exception as exc:
            failures.append(
                {
                    'stage': 'verified_detail',
                    'title': candidate.title,
                    'url': candidate.detail_url,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )

    merged_records = merge_canonical_records(existing_records, new_records)
    publish_allowed = len(failures) == 0
    publish_gate_reason = 'PASS' if publish_allowed else 'CANDIDATE_VERIFICATION_INCOMPLETE'
    report = {
        'schema_version': '0.1',
        'observed_at': observed_at,
        'source': 'TEDA_HOSPITAL_PROCUREMENT_INDEX',
        'start_date': start_date.isoformat(),
        'end_date': local_date.isoformat(),
        'index_pages': args.index_pages,
        'discovered_early_title_count': len(discovered),
        'considered_candidate_count': min(len(discovered), args.max_candidates),
        'new_verified_record_count': len(new_records),
        'out_of_window_count': out_of_window_count,
        'unsupported_nonmedical_count': len(unsupported),
        'unsupported_candidates': unsupported,
        'existing_record_count': len(existing_records),
        'merged_record_count': len(merged_records),
        'failure_count': len(failures),
        'failures': failures,
        'publish_allowed': publish_allowed,
        'publish_gate_reason': publish_gate_reason,
        'policy': {
            'official_index_required': True,
            'bounded_index_pages': args.index_pages,
            'early_signal_title_prefilter_only': True,
            'medical_early_signal_must_be_verified_in_detail': True,
            'detail_must_pass_canonical_validation': True,
            'candidate_parse_failures_block_publish': True,
            'retry_transient_index_and_detail_fetch_errors': True,
            'fetch_attempts': FETCH_ATTEMPTS,
            'rate_limit_bypass': False,
            'minimum_request_delay_seconds': args.delay_seconds,
        },
    }
    write_json(args.records_output, merged_records)
    write_json(args.report_output, report)
    print(
        f'discovered={len(discovered)} verified={len(new_records)} old={out_of_window_count} '
        f'unsupported={len(unsupported)} failures={len(failures)} gate={publish_gate_reason}'
    )
    if not publish_allowed:
        print(f'TEDA refresh publish blocked: {publish_gate_reason}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
