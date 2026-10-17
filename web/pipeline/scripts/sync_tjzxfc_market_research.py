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
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PIPELINE_ROOT))

from atomic_json_io import validate_json_output_paths, write_json_atomic, write_json_bundle_atomic  # noqa: E402
from medical_channel_pipeline.state import merge_canonical_records  # noqa: E402
from medical_channel_pipeline.tjzxfc_discovery import (  # noqa: E402
    INDEX_URL,
    fetch_tjzxfc_page,
    parse_tjzxfc_index_html,
    select_candidates_since,
    stable_opportunity_id,
)
from medical_channel_pipeline.tjzxfc_market_research import (  # noqa: E402
    TjzxfcParseError,
    parse_tjzxfc_market_research,
)

SHANGHAI = ZoneInfo('Asia/Shanghai')
MIN_DETAIL_DELAY_SECONDS = 3.0
FETCH_ATTEMPTS = 2
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}
UNSUPPORTED_DETAIL_CODES = {'TJZXFC_NON_MEDICAL_EARLY_SIGNAL'}


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
    write_json_atomic(path, payload)


def is_retryable_fetch_error(exc: Exception) -> bool:
    message = str(exc)
    if message == 'TJZXFC_NETWORK_ERROR':
        return True
    match = re.fullmatch(r'TJZXFC_HTTP_(\d{3})', message)
    return bool(match and int(match.group(1)) in RETRYABLE_HTTP_CODES)


def fetch_page_with_retry(url: str, *, delay_seconds: float, attempts: int = FETCH_ATTEMPTS) -> str:
    if attempts < 1:
        raise ValueError('attempts must be >= 1')
    for attempt in range(1, attempts + 1):
        try:
            return fetch_tjzxfc_page(url)
        except RuntimeError as exc:
            if attempt >= attempts or not is_retryable_fetch_error(exc):
                raise
            time.sleep(delay_seconds)
    raise AssertionError('unreachable')


def publish_gate(
    *,
    index_discovery_succeeded: bool,
    selected_candidate_count: int,
    new_verified_record_count: int,
    unresolved_failure_count: int,
) -> tuple[bool, str]:
    if not index_discovery_succeeded:
        return False, 'INDEX_DISCOVERY_FAILED'
    if selected_candidate_count and not new_verified_record_count:
        return False, 'NO_SELECTED_DETAIL_VERIFIED'
    if unresolved_failure_count:
        return False, 'SUPPORTED_OR_UNKNOWN_DETAILS_INCOMPLETE'
    return True, 'PASS'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Sync supported Tianjin Central Hospital of Gynecology Obstetrics pre-procurement market-research notices.'
    )
    parser.add_argument('--as-of', default=None, help='ISO-8601 timestamp with timezone; defaults to now.')
    parser.add_argument('--lookback-days', type=int, default=7)
    parser.add_argument('--max-candidates', type=int, default=15)
    parser.add_argument('--delay-seconds', type=float, default=MIN_DETAIL_DELAY_SECONDS)
    parser.add_argument('--existing-records-input', action='append', type=Path, default=[])
    parser.add_argument('--records-output', required=True, type=Path)
    parser.add_argument('--report-output', required=True, type=Path)
    args = parser.parse_args()

    validate_json_output_paths(
        report_output=args.report_output,
        data_outputs={'records': args.records_output},
        input_paths={'records': args.existing_records_input},
    )

    if not 1 <= args.lookback_days <= 30:
        raise ValueError('--lookback-days must be between 1 and 30')
    if not 1 <= args.max_candidates <= 50:
        raise ValueError('--max-candidates must be between 1 and 50')
    if args.delay_seconds < MIN_DETAIL_DELAY_SECONDS:
        raise ValueError(f'--delay-seconds must be >= {MIN_DETAIL_DELAY_SECONDS:g}')

    as_of = parse_as_of(args.as_of)
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=args.lookback_days - 1)
    observed_at = as_of.astimezone(timezone.utc).isoformat()
    existing_records = load_json_arrays(args.existing_records_input)

    try:
        index_html = fetch_page_with_retry(INDEX_URL, delay_seconds=args.delay_seconds)
        discovered = parse_tjzxfc_index_html(index_html)
    except Exception as exc:
        report = {
            'schema_version': '0.1',
            'observed_at': observed_at,
            'source': 'TJZXFC_OFFICIAL_MARKET_RESEARCH',
            'index_url': INDEX_URL,
            'publish_allowed': False,
            'publish_gate_reason': 'INDEX_DISCOVERY_FAILED',
            'existing_record_count': len(existing_records),
            'merged_record_count': len(existing_records),
            'records_output_written': False,
            'records_output_status': 'PRESERVED_UNCHANGED',
            'failure_count': 1,
            'failures': [{'stage': 'index_discovery', 'error': type(exc).__name__, 'message': str(exc)[:300]}],
        }
        write_json(args.report_output, report)
        return 2

    selected = select_candidates_since(
        discovered,
        start_date=start_date,
        end_date=local_date,
        max_candidates=args.max_candidates,
    )
    new_records: list[dict] = []
    failures: list[dict] = []
    unsupported: list[dict] = []
    failed_ids: list[str] = []

    for candidate in selected:
        opportunity_id = stable_opportunity_id(candidate.detail_url)
        time.sleep(args.delay_seconds)
        try:
            detail_html = fetch_page_with_retry(candidate.detail_url, delay_seconds=args.delay_seconds)
            record = parse_tjzxfc_market_research(
                detail_html,
                source_url=candidate.detail_url,
                index_url=INDEX_URL,
                index_published_at=candidate.published_at,
                expected_title=candidate.title,
                observed_at=observed_at,
                opportunity_id=opportunity_id,
            )
            new_records.append(record)
        except TjzxfcParseError as exc:
            if str(exc) in UNSUPPORTED_DETAIL_CODES:
                unsupported.append({
                    'opportunity_id': opportunity_id,
                    'title': candidate.title,
                    'url': candidate.detail_url,
                    'reason': str(exc),
                })
                continue
            failed_ids.append(opportunity_id)
            failures.append({
                'stage': 'verified_detail', 'opportunity_id': opportunity_id,
                'title': candidate.title, 'url': candidate.detail_url,
                'error': type(exc).__name__, 'message': str(exc)[:300],
            })
        except Exception as exc:
            failed_ids.append(opportunity_id)
            failures.append({
                'stage': 'verified_detail', 'opportunity_id': opportunity_id,
                'title': candidate.title, 'url': candidate.detail_url,
                'error': type(exc).__name__, 'message': str(exc)[:300],
            })

    existing_ids = {
        record.get('opportunity_id') for record in existing_records
        if isinstance(record, dict) and isinstance(record.get('opportunity_id'), str)
    }
    unresolved_failure_ids = [opportunity_id for opportunity_id in failed_ids if opportunity_id not in existing_ids]
    publish_allowed, publish_gate_reason = publish_gate(
        index_discovery_succeeded=True,
        selected_candidate_count=len(selected),
        new_verified_record_count=len(new_records),
        unresolved_failure_count=len(unresolved_failure_ids),
    )
    # A blocked run must not enter canonical merge: bad historical data must not
    # mask this run's discovery/detail failure or prevent its report from being written.
    merged_records = merge_canonical_records(existing_records, new_records) if publish_allowed else existing_records
    report = {
        'schema_version': '0.1',
        'observed_at': observed_at,
        'source': 'TJZXFC_OFFICIAL_MARKET_RESEARCH',
        'index_url': INDEX_URL,
        'start_date': start_date.isoformat(),
        'end_date': local_date.isoformat(),
        'discovered_early_signal_count': len(discovered),
        'selected_candidate_count': len(selected),
        'new_verified_record_count': len(new_records),
        'existing_record_count': len(existing_records),
        'unsupported_non_medical_count': len(unsupported),
        'unsupported': unsupported,
        'failure_count': len(failures),
        'failures': failures,
        'unresolved_failure_count': len(unresolved_failure_ids),
        'unresolved_failure_opportunity_ids': unresolved_failure_ids,
        'merged_record_count': len(merged_records),
        'publish_allowed': publish_allowed,
        'publish_gate_reason': publish_gate_reason,
        'records_output_written': publish_allowed,
        'records_output_status': 'WRITTEN' if publish_allowed else 'PRESERVED_UNCHANGED',
        'policy': {
            'official_index_required': True,
            'broad_market_research_discovery_then_strict_medical_detail_scope': True,
            'non_medical_market_research_is_unsupported_not_failure': True,
            'title_and_publication_date_must_match_official_detail': True,
            'deadline_time_never_invented': True,
            'failed_detail_never_replaces_existing_verified_record': True,
            'minimum_detail_delay_seconds': args.delay_seconds,
            'fetch_attempts': FETCH_ATTEMPTS,
            'intraday_scheduler_enabled': False,
        },
    }
    if publish_allowed:
        write_json_bundle_atomic({args.records_output: merged_records, args.report_output: report})
    else:
        report['merged_record_count'] = len(existing_records)
        write_json(args.report_output, report)
    print(
        f'discovered={len(discovered)} selected={len(selected)} verified={len(new_records)} '
        f'unsupported={len(unsupported)} failures={len(failures)} unresolved={len(unresolved_failure_ids)} '
        f'gate={publish_gate_reason}'
    )
    return 0 if publish_allowed else 2


if __name__ == '__main__':
    raise SystemExit(main())
