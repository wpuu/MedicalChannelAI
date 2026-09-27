#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline.ccgp_detail import (  # noqa: E402
    fetch_ccgp_detail_html,
    parse_ccgp_competitive_consultation_html,
    parse_ccgp_public_tender_html,
)
from medical_channel_pipeline.ccgp_discovery import (  # noqa: E402
    REGION_ZONE_IDS,
    build_search_url,
    fetch_search_page,
    is_primary_opportunity_candidate,
    parse_search_html,
)
from medical_channel_pipeline.ccgp_events import parse_ccgp_event_html  # noqa: E402
from medical_channel_pipeline.state import (  # noqa: E402
    active_ccgp_project_numbers,
    merge_canonical_records,
    merge_notice_events,
)

VERIFIED_NOTICE_ADAPTERS = {
    '公开招标': parse_ccgp_public_tender_html,
    '竞争性磋商': parse_ccgp_competitive_consultation_html,
}
DEFAULT_NOTICE_TYPES = ['公开招标', '竞争性磋商']
DEFAULT_REGION = '天津'


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]
    return f'{prefix}_{digest}'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_json_arrays(paths: list[Path], *, label: str) -> list[dict]:
    merged: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, list):
            raise ValueError(f'{label} must contain a JSON array: {path}')
        merged.extend(payload)
    return merged


def discovery_event(candidate, *, project_number: str, event_type: str, observed_at: str) -> dict:
    return {
        'schema_version': '0.1',
        'event_id': stable_id(event_type.lower(), candidate.detail_url),
        'event_type': event_type,
        'project_number': project_number,
        'project_name': candidate.title,
        'published_at': candidate.published_at,
        'source_url': candidate.detail_url,
        'observed_at': observed_at,
        'summary': 'DISCOVERY_ONLY_EVENT_REQUIRES_DETAIL_REVIEW',
        'changed_fact_paths': [],
        'fact_overrides': {},
        'unresolved_fact_paths': ['__discovery_only_event__'] if event_type == 'CORRECTION' else [],
        'requires_reconciliation': event_type == 'CORRECTION',
        'terminal': event_type == 'TERMINATION',
    }


def _fetch_kwargs(timeout_seconds: int | None) -> dict:
    return {} if timeout_seconds is None else {'timeout_seconds': timeout_seconds}


def scan_events(
    project_number: str,
    *,
    region: str,
    start_date: str,
    end_date: str,
    delay_seconds: float,
    observed_at: str,
    failures: list[dict],
    timeout_seconds: int | None = None,
) -> list[dict]:
    events: list[dict] = []
    for notice_type, event_type in (('更正公告', 'CORRECTION'), ('终止公告', 'TERMINATION')):
        search_url = build_search_url(
            keyword=project_number,
            notice_type=notice_type,
            page_index=1,
            start_date=start_date,
            end_date=end_date,
            region=region,
        )
        try:
            html = fetch_search_page(search_url, **_fetch_kwargs(timeout_seconds))
            candidates = parse_search_html(html, keyword=project_number)
        except Exception as exc:  # explicit report; no bypass/retry storm
            failures.append(
                {
                    'stage': 'event_search',
                    'region': region,
                    'project_number': project_number,
                    'notice_type': notice_type,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )
            continue

        for candidate in candidates:
            if project_number.lower() not in candidate.title.lower():
                continue
            event = None
            try:
                time.sleep(delay_seconds)
                detail_html = fetch_ccgp_detail_html(candidate.detail_url, **_fetch_kwargs(timeout_seconds))
                event = parse_ccgp_event_html(
                    detail_html,
                    source_url=candidate.detail_url,
                    observed_at=observed_at,
                    event_id=stable_id(event_type.lower(), candidate.detail_url),
                )
            except Exception as exc:
                failures.append(
                    {
                        'stage': 'event_detail',
                        'region': region,
                        'project_number': project_number,
                        'url': candidate.detail_url,
                        'error': type(exc).__name__,
                        'message': str(exc)[:300],
                    }
                )
                if candidate.published_at:
                    # Conservative fallback: official discovery of a correction/termination
                    # is enough to suppress the stale card, but never enough to rewrite facts.
                    event = discovery_event(
                        candidate,
                        project_number=project_number,
                        event_type=event_type,
                        observed_at=observed_at,
                    )
            if event:
                events.append(event)
        time.sleep(delay_seconds)
    return events


def discover_candidates(
    *,
    keyword: str,
    region: str,
    notice_types: list[str],
    start_date: str,
    end_date: str,
    delay_seconds: float,
    failures: list[dict],
    timeout_seconds: int | None = None,
) -> list[tuple[str, object]]:
    discovered: list[tuple[str, object]] = []
    seen_urls: set[str] = set()
    for index, notice_type in enumerate(notice_types):
        if notice_type not in VERIFIED_NOTICE_ADAPTERS:
            raise ValueError(f'notice type has no VERIFIED adapter: {notice_type}')
        search_url = build_search_url(
            keyword=keyword,
            notice_type=notice_type,
            page_index=1,
            start_date=start_date,
            end_date=end_date,
            region=region,
        )
        try:
            html = fetch_search_page(search_url, **_fetch_kwargs(timeout_seconds))
            candidates = parse_search_html(html, keyword=keyword)
        except Exception as exc:
            failures.append(
                {
                    'stage': 'discovery_search',
                    'region': region,
                    'notice_type': notice_type,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )
            candidates = []
        for candidate in candidates:
            if not is_primary_opportunity_candidate(candidate):
                continue
            if candidate.detail_url in seen_urls:
                continue
            seen_urls.add(candidate.detail_url)
            discovered.append((notice_type, candidate))
        if index + 1 < len(notice_types):
            time.sleep(delay_seconds)

    discovered.sort(
        key=lambda item: (item[1].published_at or '', item[1].detail_url),
        reverse=True,
    )
    return discovered


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Stateful low-frequency CCGP Pilot sync: Tianjin discovery -> VERIFIED detail -> active-project event watch.'
    )
    parser.add_argument('--keyword', required=True)
    parser.add_argument('--start-date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--end-date', required=True, help='YYYY-MM-DD')
    parser.add_argument(
        '--region',
        choices=sorted(REGION_ZONE_IDS),
        default=DEFAULT_REGION,
        help='CCGP province-level region selector. Tianjin Pilot defaults to 天津.',
    )
    parser.add_argument(
        '--notice-type',
        action='append',
        choices=sorted(VERIFIED_NOTICE_ADAPTERS),
        default=None,
        help='Repeat to select VERIFIED-supported CCGP notice types. Defaults to public tender + competitive consultation.',
    )
    parser.add_argument(
        '--existing-records-input',
        action='append',
        type=Path,
        default=[],
        help='Previous canonical-record JSON array. Repeat to merge source stores before this sync.',
    )
    parser.add_argument(
        '--existing-events-input',
        action='append',
        type=Path,
        default=[],
        help='Previous correction/termination event JSON array. Repeat to preserve event history.',
    )
    parser.add_argument('--max-candidates', type=int, default=5)
    parser.add_argument('--max-event-watch-projects', type=int, default=20)
    parser.add_argument('--delay-seconds', type=float, default=4.0)
    parser.add_argument('--records-output', required=True, type=Path)
    parser.add_argument('--events-output', required=True, type=Path)
    parser.add_argument('--report-output', required=True, type=Path)
    args = parser.parse_args()

    if not 1 <= args.max_candidates <= 20:
        raise ValueError('--max-candidates must be between 1 and 20')
    if not 1 <= args.max_event_watch_projects <= 100:
        raise ValueError('--max-event-watch-projects must be between 1 and 100')
    if args.delay_seconds < 3:
        raise ValueError('--delay-seconds must be >= 3')

    notice_types = args.notice_type or DEFAULT_NOTICE_TYPES
    observed_at = now_iso()
    observed_datetime = datetime.fromisoformat(observed_at)
    failures: list[dict] = []
    new_records: list[dict] = []
    new_events: list[dict] = []

    existing_records = load_json_arrays(args.existing_records_input, label='existing records')
    existing_events = load_json_arrays(args.existing_events_input, label='existing events')

    discovered = discover_candidates(
        keyword=args.keyword,
        region=args.region,
        notice_types=notice_types,
        start_date=args.start_date,
        end_date=args.end_date,
        delay_seconds=args.delay_seconds,
        failures=failures,
    )
    candidates = discovered[: args.max_candidates]

    for notice_type, candidate in candidates:
        adapter = VERIFIED_NOTICE_ADAPTERS[notice_type]
        try:
            time.sleep(args.delay_seconds)
            detail_html = fetch_ccgp_detail_html(candidate.detail_url)
            record = adapter(
                detail_html,
                source_url=candidate.detail_url,
                observed_at=observed_at,
                opportunity_id=stable_id('ccgp', candidate.detail_url),
            )
            new_records.append(record)
        except Exception as exc:
            failures.append(
                {
                    'stage': 'verified_detail',
                    'region': args.region,
                    'notice_type': notice_type,
                    'title': candidate.title,
                    'url': candidate.detail_url,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )

    merged_records = merge_canonical_records(existing_records, new_records)
    watch_projects = active_ccgp_project_numbers(merged_records, observed_datetime)
    if len(watch_projects) > args.max_event_watch_projects:
        raise RuntimeError(
            f'ACTIVE_EVENT_WATCH_CAP_EXCEEDED:{len(watch_projects)}>'
            f'{args.max_event_watch_projects}'
        )

    for project_number in watch_projects:
        new_events.extend(
            scan_events(
                project_number,
                region=args.region,
                start_date=args.start_date,
                end_date=args.end_date,
                delay_seconds=args.delay_seconds,
                observed_at=observed_at,
                failures=failures,
            )
        )

    merged_events = merge_notice_events(existing_events, new_events)

    report = {
        'schema_version': '0.1',
        'observed_at': observed_at,
        'region': args.region,
        'region_zone_id': REGION_ZONE_IDS[args.region],
        'keyword': args.keyword,
        'notice_types': notice_types,
        'candidate_count': len(candidates),
        'existing_record_count': len(existing_records),
        'new_verified_record_count': len(new_records),
        'merged_record_count': len(merged_records),
        'event_watch_project_count': len(watch_projects),
        'existing_event_count': len(existing_events),
        'new_notice_event_count': len(new_events),
        'merged_event_count': len(merged_events),
        'failure_count': len(failures),
        'failures': failures,
        'policy': {
            'region_is_explicitly_scoped_in_ccgp_query': True,
            'previous_canonical_state_is_preserved': True,
            'active_old_projects_continue_event_monitoring': True,
            'event_watch_over_cap_fails_closed': True,
            'discovery_only_never_becomes_verified_without_detail': True,
            'primary_candidate_budget_excludes_result_and_event_notices': True,
            'only_notice_types_with_explicit_verified_adapter_are_collected': True,
            'rate_limit_bypass': False,
            'minimum_request_delay_seconds': args.delay_seconds,
        },
    }

    write_json(args.records_output, merged_records)
    write_json(args.events_output, merged_events)
    write_json(args.report_output, report)
    print(
        f'region={args.region} candidates={len(candidates)} new_verified={len(new_records)} '
        f'merged_records={len(merged_records)} watched={len(watch_projects)} '
        f'new_events={len(new_events)} failures={len(failures)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
