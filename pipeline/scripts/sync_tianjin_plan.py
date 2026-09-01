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
from medical_channel_pipeline.state import (  # noqa: E402
    active_ccgp_project_numbers,
    merge_canonical_records,
    merge_notice_events,
)
from sync_ccgp_query import (  # noqa: E402
    VERIFIED_NOTICE_ADAPTERS,
    discover_candidates,
    load_json_arrays,
    scan_events,
    stable_id,
    write_json,
)

DEFAULT_PLAN = PIPELINE_ROOT / 'data' / 'tianjin_query_plan.json'
SHANGHAI = ZoneInfo('Asia/Shanghai')
PILOT_REGION = '天津'


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('--as-of must include timezone')
    return parsed


def ordered_unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = raw.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def load_plan(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != '0.1':
        raise ValueError('TIANJIN_QUERY_PLAN_INVALID')

    raw_keywords = payload.get('keywords')
    notice_types = payload.get('notice_types')
    if (
        not isinstance(raw_keywords, list)
        or not raw_keywords
        or not all(isinstance(item, str) for item in raw_keywords)
    ):
        raise ValueError('TIANJIN_QUERY_PLAN_KEYWORDS_INVALID')
    keywords = ordered_unique_strings(raw_keywords)
    if not keywords:
        raise ValueError('TIANJIN_QUERY_PLAN_KEYWORDS_INVALID')
    if not isinstance(notice_types, list) or not notice_types:
        raise ValueError('TIANJIN_QUERY_PLAN_NOTICE_TYPES_INVALID')
    unsupported = [item for item in notice_types if item not in VERIFIED_NOTICE_ADAPTERS]
    if unsupported:
        raise ValueError(f'TIANJIN_QUERY_PLAN_NOTICE_TYPE_UNSUPPORTED:{unsupported}')

    region = str(payload.get('region') or PILOT_REGION).strip()
    if region != PILOT_REGION:
        raise ValueError(f'TIANJIN_QUERY_PLAN_REGION_LOCKED:{region}')

    lookback_days = int(payload.get('lookback_days', 3))
    max_candidates = int(payload.get('max_candidates', 12))
    max_event_watch_projects = int(payload.get('max_event_watch_projects', 30))
    delay_seconds = float(payload.get('delay_seconds', 4.0))
    if not 1 <= lookback_days <= 14:
        raise ValueError('TIANJIN_QUERY_PLAN_LOOKBACK_INVALID')
    if not 1 <= max_candidates <= 50:
        raise ValueError('TIANJIN_QUERY_PLAN_MAX_CANDIDATES_INVALID')
    if not 1 <= max_event_watch_projects <= 100:
        raise ValueError('TIANJIN_QUERY_PLAN_EVENT_WATCH_INVALID')
    if delay_seconds < 3:
        raise ValueError('TIANJIN_QUERY_PLAN_DELAY_TOO_LOW')

    return {
        'region': region,
        'keywords': keywords,
        'notice_types': list(notice_types),
        'lookback_days': lookback_days,
        'max_candidates': max_candidates,
        'max_event_watch_projects': max_event_watch_projects,
        'delay_seconds': delay_seconds,
    }


def plan_date_window(as_of: datetime, lookback_days: int) -> tuple[str, str]:
    if as_of.tzinfo is None:
        raise ValueError('TIANJIN_PLAN_AS_OF_TIMEZONE_REQUIRED')
    if not 1 <= lookback_days <= 14:
        raise ValueError('TIANJIN_PLAN_LOOKBACK_INVALID')
    local_date = as_of.astimezone(SHANGHAI).date()
    start_date = local_date - timedelta(days=lookback_days - 1)
    return start_date.isoformat(), local_date.isoformat()


def merge_discovered_candidates(
    discovered_by_url: dict[str, tuple[str, object]],
    discovered_keywords: dict[str, set[str]],
    *,
    keyword: str,
    candidates: list[tuple[str, object]],
) -> None:
    for notice_type, candidate in candidates:
        detail_url = str(getattr(candidate, 'detail_url', '') or '').strip()
        if not detail_url:
            continue
        discovered_by_url.setdefault(detail_url, (notice_type, candidate))
        discovered_keywords.setdefault(detail_url, set()).add(keyword)


def publish_gate(
    *,
    discovery_success_count: int,
    selected_candidate_count: int,
    new_verified_record_count: int,
) -> tuple[bool, str]:
    if discovery_success_count <= 0:
        return False, 'ALL_DISCOVERY_QUERIES_FAILED'
    if selected_candidate_count > 0 and new_verified_record_count <= 0:
        return False, 'ALL_SELECTED_DETAILS_FAILED_VERIFICATION'
    return True, 'PASS'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Low-frequency Tianjin medical plan sync: multi-keyword discovery -> dedupe -> VERIFIED detail -> one event watch pass.'
    )
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    parser.add_argument('--as-of', default=None, help='Optional ISO-8601 timestamp with timezone; defaults to now.')
    parser.add_argument('--existing-records-input', action='append', type=Path, default=[])
    parser.add_argument('--existing-events-input', action='append', type=Path, default=[])
    parser.add_argument('--records-output', required=True, type=Path)
    parser.add_argument('--events-output', required=True, type=Path)
    parser.add_argument('--report-output', required=True, type=Path)
    args = parser.parse_args()

    plan = load_plan(args.plan)
    as_of = parse_as_of(args.as_of)
    start_text, end_text = plan_date_window(as_of, plan['lookback_days'])
    observed_at = as_of.astimezone(timezone.utc).isoformat()

    failures: list[dict] = []
    existing_records = load_json_arrays(args.existing_records_input, label='existing records')
    existing_events = load_json_arrays(args.existing_events_input, label='existing events')

    discovered_by_url: dict[str, tuple[str, object]] = {}
    discovered_keywords: dict[str, set[str]] = {}
    planned_discovery_queries = len(plan['keywords']) * len(plan['notice_types'])

    for keyword_index, keyword in enumerate(plan['keywords']):
        candidates = discover_candidates(
            keyword=keyword,
            region=plan['region'],
            notice_types=plan['notice_types'],
            start_date=start_text,
            end_date=end_text,
            delay_seconds=plan['delay_seconds'],
            failures=failures,
        )
        merge_discovered_candidates(
            discovered_by_url,
            discovered_keywords,
            keyword=keyword,
            candidates=candidates,
        )
        if keyword_index + 1 < len(plan['keywords']):
            time.sleep(plan['delay_seconds'])

    discovery_failures = [item for item in failures if item.get('stage') == 'discovery_search']
    discovery_success_count = max(0, planned_discovery_queries - len(discovery_failures))

    discovered = list(discovered_by_url.values())
    discovered.sort(
        key=lambda item: (getattr(item[1], 'published_at', None) or '', getattr(item[1], 'detail_url', '')),
        reverse=True,
    )
    selected = discovered[: plan['max_candidates']]

    new_records: list[dict] = []
    for notice_type, candidate in selected:
        adapter = VERIFIED_NOTICE_ADAPTERS[notice_type]
        try:
            time.sleep(plan['delay_seconds'])
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
                    'region': plan['region'],
                    'notice_type': notice_type,
                    'keywords': sorted(discovered_keywords.get(candidate.detail_url, set())),
                    'title': candidate.title,
                    'url': candidate.detail_url,
                    'error': type(exc).__name__,
                    'message': str(exc)[:300],
                }
            )

    merged_records = merge_canonical_records(existing_records, new_records)
    watch_projects = active_ccgp_project_numbers(merged_records, as_of)
    if len(watch_projects) > plan['max_event_watch_projects']:
        raise RuntimeError(
            f'ACTIVE_EVENT_WATCH_CAP_EXCEEDED:{len(watch_projects)}>'
            f"{plan['max_event_watch_projects']}"
        )

    new_events: list[dict] = []
    for project_number in watch_projects:
        new_events.extend(
            scan_events(
                project_number,
                region=plan['region'],
                start_date=start_text,
                end_date=end_text,
                delay_seconds=plan['delay_seconds'],
                observed_at=observed_at,
                failures=failures,
            )
        )
    merged_events = merge_notice_events(existing_events, new_events)

    publish_allowed, publish_gate_reason = publish_gate(
        discovery_success_count=discovery_success_count,
        selected_candidate_count=len(selected),
        new_verified_record_count=len(new_records),
    )

    report = {
        'schema_version': '0.1',
        'observed_at': observed_at,
        'region': plan['region'],
        'start_date': start_text,
        'end_date': end_text,
        'keywords': plan['keywords'],
        'notice_types': plan['notice_types'],
        'planned_discovery_query_count': planned_discovery_queries,
        'discovery_success_count': discovery_success_count,
        'unique_discovered_candidate_count': len(discovered),
        'selected_candidate_count': len(selected),
        'new_verified_record_count': len(new_records),
        'merged_record_count': len(merged_records),
        'event_watch_project_count': len(watch_projects),
        'new_notice_event_count': len(new_events),
        'merged_event_count': len(merged_events),
        'failure_count': len(failures),
        'failures': failures,
        'publish_allowed': publish_allowed,
        'publish_gate_reason': publish_gate_reason,
        'policy': {
            'region_locked_to_tianjin': True,
            'multi_keyword_discovery_is_deduplicated_before_detail_fetch': True,
            'event_watch_runs_once_after_all_keywords': True,
            'previous_canonical_state_is_preserved': True,
            'discovery_only_never_becomes_verified_without_detail': True,
            'all_discovery_queries_failed_blocks_publish': True,
            'all_selected_details_failed_verification_blocks_publish': True,
            'rate_limit_bypass': False,
            'minimum_request_delay_seconds': plan['delay_seconds'],
        },
    }

    write_json(args.records_output, merged_records)
    write_json(args.events_output, merged_events)
    write_json(args.report_output, report)

    print(
        f"queries_ok={discovery_success_count}/{planned_discovery_queries} "
        f"unique={len(discovered)} selected={len(selected)} verified={len(new_records)} "
        f"records={len(merged_records)} watched={len(watch_projects)} "
        f"events={len(new_events)} failures={len(failures)} gate={publish_gate_reason}"
    )
    if not publish_allowed:
        print(
            f'refresh publish blocked: {publish_gate_reason}',
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
