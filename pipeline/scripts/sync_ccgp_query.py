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
    build_search_url,
    fetch_search_page,
    parse_search_html,
)
from medical_channel_pipeline.ccgp_events import parse_ccgp_event_html  # noqa: E402

VERIFIED_NOTICE_ADAPTERS = {
    '公开招标': parse_ccgp_public_tender_html,
    '竞争性磋商': parse_ccgp_competitive_consultation_html,
}
DEFAULT_NOTICE_TYPES = ['公开招标', '竞争性磋商']


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]
    return f'{prefix}_{digest}'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


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


def scan_events(
    project_number: str,
    *,
    start_date: str,
    end_date: str,
    delay_seconds: float,
    observed_at: str,
    failures: list[dict],
) -> list[dict]:
    events: list[dict] = []
    for notice_type, event_type in (('更正公告', 'CORRECTION'), ('终止公告', 'TERMINATION')):
        search_url = build_search_url(
            keyword=project_number,
            notice_type=notice_type,
            page_index=1,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            html = fetch_search_page(search_url)
            candidates = parse_search_html(html, keyword=project_number)
        except Exception as exc:  # explicit report; no bypass/retry storm
            failures.append(
                {
                    'stage': 'event_search',
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
                detail_html = fetch_ccgp_detail_html(candidate.detail_url)
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
    notice_types: list[str],
    start_date: str,
    end_date: str,
    delay_seconds: float,
    failures: list[dict],
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
        )
        try:
            html = fetch_search_page(search_url)
            candidates = parse_search_html(html, keyword=keyword)
        except Exception as exc:
            failures.append(
                {
                    'stage': 'discovery_search',
                    'notice_type': notice_type,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )
            candidates = []
        for candidate in candidates:
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
        description='Low-frequency CCGP Pilot sync: discovery -> VERIFIED detail -> event safety scan.'
    )
    parser.add_argument('--keyword', required=True)
    parser.add_argument('--start-date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--end-date', required=True, help='YYYY-MM-DD')
    parser.add_argument(
        '--notice-type',
        action='append',
        choices=sorted(VERIFIED_NOTICE_ADAPTERS),
        default=None,
        help='Repeat to select VERIFIED-supported CCGP notice types. Defaults to public tender + competitive consultation.',
    )
    parser.add_argument('--max-candidates', type=int, default=5)
    parser.add_argument('--delay-seconds', type=float, default=4.0)
    parser.add_argument('--records-output', required=True, type=Path)
    parser.add_argument('--events-output', required=True, type=Path)
    parser.add_argument('--report-output', required=True, type=Path)
    args = parser.parse_args()

    if not 1 <= args.max_candidates <= 20:
        raise ValueError('--max-candidates must be between 1 and 20')
    if args.delay_seconds < 3:
        raise ValueError('--delay-seconds must be >= 3')

    notice_types = args.notice_type or DEFAULT_NOTICE_TYPES
    observed_at = now_iso()
    failures: list[dict] = []
    records: list[dict] = []
    events: list[dict] = []

    discovered = discover_candidates(
        keyword=args.keyword,
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
            records.append(record)
        except Exception as exc:
            failures.append(
                {
                    'stage': 'verified_detail',
                    'notice_type': notice_type,
                    'title': candidate.title,
                    'url': candidate.detail_url,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )
            continue

        project_number = record['facts']['project_number']
        events.extend(
            scan_events(
                project_number,
                start_date=args.start_date,
                end_date=args.end_date,
                delay_seconds=args.delay_seconds,
                observed_at=observed_at,
                failures=failures,
            )
        )

    records_by_project = {}
    for record in records:
        records_by_project[record['facts']['project_number'].strip().lower()] = record
    records = list(records_by_project.values())

    events_by_id = {event['event_id']: event for event in events}
    events = list(events_by_id.values())

    report = {
        'schema_version': '0.1',
        'observed_at': observed_at,
        'keyword': args.keyword,
        'notice_types': notice_types,
        'candidate_count': len(candidates),
        'verified_record_count': len(records),
        'notice_event_count': len(events),
        'failure_count': len(failures),
        'failures': failures,
        'policy': {
            'discovery_only_never_becomes_verified_without_detail': True,
            'only_notice_types_with_explicit_verified_adapter_are_collected': True,
            'rate_limit_bypass': False,
            'minimum_request_delay_seconds': args.delay_seconds,
        },
    }

    write_json(args.records_output, records)
    write_json(args.events_output, events)
    write_json(args.report_output, report)
    print(
        f'candidates={len(candidates)} verified={len(records)} '
        f'events={len(events)} failures={len(failures)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
