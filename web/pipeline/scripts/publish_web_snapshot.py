#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402
from medical_channel_pipeline.award_price_reference import combine_award_price_references  # noqa: E402
from medical_channel_pipeline.ccgp_award import MAX_LEDGER_ENTRIES  # noqa: E402
from medical_channel_pipeline.legal_windows import working_calendar_payload  # noqa: E402
from medical_channel_pipeline.public_snapshot import MAX_NOTICE_SUPPRESSED_PROJECTS  # noqa: E402

DEFAULT_INPUTS = [
    PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json',
    PIPELINE_ROOT / 'data' / 'tianjin_official_institution_seed.json',
]
REGIONAL_INPUT = PIPELINE_ROOT / 'data' / 'regional_live_ccgp_records.json'
DEFAULT_EVENT_INPUTS = [PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json']
REGIONAL_EVENT_INPUT = PIPELINE_ROOT / 'data' / 'regional_notice_events.json'
DEFAULT_AWARD_INPUTS = [
    PIPELINE_ROOT / 'data' / 'tianjin_award_records.json',
    PIPELINE_ROOT / 'data' / 'regional_award_records.json',
]
DEFAULT_OUTPUT = WEB_ROOT / 'public' / 'data' / 'today-actions.public.json'
SHANGHAI = ZoneInfo('Asia/Shanghai')


def regional_notice_events(events: list[dict]) -> list[dict]:
    """Regional 更正/终止 events must carry their market: an event without one
    could reach any regional record that reuses the project number."""
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('regional event must be an object')
        market_code = str(event.get('market_code') or '').strip().upper()
        if not market_code or market_code == 'TJ':
            raise ValueError(f'REGIONAL_EVENT_MARKET_CODE_REQUIRED:{event.get("event_id")}')
    return events


def load_arrays(paths: list[Path], *, label: str) -> list[dict]:
    merged: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, list):
            raise ValueError(f'{label} must contain a JSON array: {path}')
        for record in payload:
            if not isinstance(record, dict):
                raise ValueError(f'{label} record must be an object: {path}')
            facts = record.setdefault('facts', {})
            market_code = str(facts.get('market_code') or '').strip().upper()
            if not market_code:
                if not path.name.startswith('tianjin_'):
                    raise ValueError(f'MARKET_CODE_REQUIRED:{path}:{record.get("opportunity_id")}')
                facts['market_code'] = 'TJ'
                facts['market_name'] = '天津'
                facts['market_admin_code'] = '120000'
            elif market_code == 'TJ':
                facts.setdefault('market_name', '天津')
                facts.setdefault('market_admin_code', '120000')
            elif not facts.get('market_name') or not facts.get('market_admin_code'):
                raise ValueError(f'MARKET_METADATA_REQUIRED:{path}:{record.get("opportunity_id")}')
            merged.append(record)
    return merged


def parse_card_datetime(value: object, *, end_of_day: bool = False) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SHANGHAI)
        return parsed
    except ValueError:
        try:
            parsed_date = date.fromisoformat(raw[:10])
            return datetime.combine(parsed_date, time.max if end_of_day else time.min, tzinfo=SHANGHAI)
        except ValueError:
            return None


def card_sort_key(card: dict) -> tuple[float, float, float, str]:
    facts = card.get('facts') or {}
    score = float((card.get('priority') or {}).get('score') or 0)
    deadline = (
        parse_card_datetime(facts.get('registration_deadline'))
        or parse_card_datetime(facts.get('registration_deadline_date'), end_of_day=True)
        or parse_card_datetime(facts.get('bid_deadline'))
    )
    published = parse_card_datetime(facts.get('published_at'))
    return (
        -score,
        deadline.timestamp() if deadline else float('inf'),
        -(published.timestamp() if published else 0.0),
        str(card.get('opportunity_id') or ''),
    )


def market_metadata(records: list[dict]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for record in records:
        opportunity_id = str(record.get('opportunity_id') or '').strip()
        facts = record.get('facts') or {}
        if not opportunity_id:
            continue
        result[opportunity_id] = {
            'market_code': str(facts.get('market_code') or '').strip().upper(),
            'market_name': str(facts.get('market_name') or '').strip(),
            'market_admin_code': str(facts.get('market_admin_code') or '').strip(),
        }
    return result


def inject_market(card: dict, metadata: dict[str, dict[str, str]]) -> dict:
    copied = deepcopy(card)
    meta = metadata.get(str(copied.get('opportunity_id') or ''))
    if meta:
        copied.setdefault('facts', {}).update(meta)
    return copied


def combine_award_ledgers(*snapshots: dict) -> list[dict]:
    """Union of per-market award ledgers: unique award_id, newest first, bounded."""
    seen: set[str] = set()
    merged: list[dict] = []
    for snapshot in snapshots:
        for entry in snapshot.get('award_ledger') or []:
            award_id = str(entry.get('award_id') or '')
            if not award_id or award_id in seen:
                continue
            seen.add(award_id)
            merged.append(deepcopy(entry))
    merged.sort(key=lambda entry: (str(entry.get('published_at') or ''), str(entry.get('award_id') or '')), reverse=True)
    return merged[:MAX_LEDGER_ENTRIES]


def combine_notice_suppressed_projects(*snapshots: dict) -> tuple[int, list[dict]]:
    """(exact total, bounded newest-first list) across per-market snapshots."""
    total = sum(int(snapshot.get('notice_suppressed_project_count') or 0) for snapshot in snapshots)
    merged: list[dict] = []
    for snapshot in snapshots:
        merged.extend(deepcopy(item) for item in snapshot.get('notice_suppressed_projects') or [])
    merged.sort(
        key=lambda item: (str(item.get('published_at') or ''), str(item.get('project_number') or '')),
        reverse=True,
    )
    return total, merged[:MAX_NOTICE_SUPPRESSED_PROJECTS]


def split_awards_by_market(award_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """(Tianjin awards, other-market awards). Awards without a market code are
    legacy Tianjin-pilot records and stay on the Tianjin side."""
    tianjin: list[dict] = []
    regional: list[dict] = []
    for record in award_records:
        code = str(((record.get('facts') or {}).get('market_code')) or 'TJ').strip().upper()
        (tianjin if code == 'TJ' else regional).append(record)
    return tianjin, regional


def combine_snapshots(
    tianjin_snapshot: dict,
    regional_snapshot: dict,
    records: list[dict],
    as_of: datetime,
) -> dict:
    meta = market_metadata(records)
    pool = [
        inject_market(card, meta)
        for card in [
            *(tianjin_snapshot.get('opportunity_pool') or tianjin_snapshot.get('cards') or []),
            *(regional_snapshot.get('opportunity_pool') or regional_snapshot.get('cards') or []),
        ]
    ]
    seen: set[str] = set()
    unique_pool: list[dict] = []
    for card in sorted(pool, key=card_sort_key):
        opportunity_id = str(card.get('opportunity_id') or '')
        if not opportunity_id or opportunity_id in seen:
            continue
        seen.add(opportunity_id)
        unique_pool.append(card)
    for index, card in enumerate(unique_pool, start=1):
        card['rank'] = index
    cards = [deepcopy(card) for card in unique_pool[:5]]
    for index, card in enumerate(cards, start=1):
        card['rank'] = index
    suppressed_count, suppressed_projects = combine_notice_suppressed_projects(tianjin_snapshot, regional_snapshot)
    return {
        'schema_version': '0.1',
        'mode': 'TODAY_ACTIONS',
        'snapshot_as_of': as_of.isoformat(),
        'input_candidate_count': int(tianjin_snapshot.get('input_candidate_count') or 0)
        + int(regional_snapshot.get('input_candidate_count') or 0),
        'matched_count': len(unique_pool),
        'card_count': len(cards),
        'opportunity_pool_count': len(unique_pool),
        'model_request_count': 0,
        'coverage_warning': 'PARTIAL_OR_SOURCE_SPECIFIC_COVERAGE_MAY_APPLY',
        'working_calendar': working_calendar_payload(),
        'awarded_project_count': int(tianjin_snapshot.get('awarded_project_count') or 0)
        + int(regional_snapshot.get('awarded_project_count') or 0),
        'notice_suppressed_project_count': suppressed_count,
        'notice_suppressed_projects': suppressed_projects,
        'award_ledger': combine_award_ledgers(tianjin_snapshot, regional_snapshot),
        'award_price_reference': combine_award_price_references(
            tianjin_snapshot.get('award_price_reference'),
            regional_snapshot.get('award_price_reference'),
        ),
        'cards': cards,
        'opportunity_pool': unique_pool,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Regenerate the verified static-trial snapshot consumed by web/.'
    )
    parser.add_argument('--as-of', required=True, help='ISO-8601 timestamp with timezone')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        '--input',
        action='append',
        type=Path,
        default=None,
        help='Canonical-record JSON array. Repeat to combine verified source stores.',
    )
    parser.add_argument(
        '--event-input',
        action='append',
        type=Path,
        default=None,
        help='Tianjin notice-event JSON array. Regional events stay disabled until they have composite market identity.',
    )
    parser.add_argument(
        '--award-input',
        action='append',
        type=Path,
        default=None,
        help='AWARD_RESULT JSON arrays (中标/成交). Defaults to the Tianjin and regional award stores when present.',
    )
    parser.add_argument(
        '--regional-event-input',
        action='append',
        type=Path,
        default=None,
        help='Regional notice-event JSON arrays (every event carries market_code). Defaults to the regional event store when present.',
    )
    args = parser.parse_args()

    input_paths = list(args.input or DEFAULT_INPUTS)
    if REGIONAL_INPUT.exists() and REGIONAL_INPUT not in input_paths:
        input_paths.append(REGIONAL_INPUT)
    event_paths = args.event_input or DEFAULT_EVENT_INPUTS
    records = load_arrays(input_paths, label='input')
    notice_events = load_arrays(event_paths, label='event input')
    award_paths = args.award_input if args.award_input is not None else [
        path for path in DEFAULT_AWARD_INPUTS if path.exists()
    ]
    award_records = load_arrays(award_paths, label='award input')
    tianjin_awards, regional_awards = split_awards_by_market(award_records)
    regional_event_paths = args.regional_event_input if args.regional_event_input is not None else (
        [REGIONAL_EVENT_INPUT] if REGIONAL_EVENT_INPUT.exists() else []
    )
    regional_events = regional_notice_events(load_arrays(regional_event_paths, label='regional event input'))

    as_of = datetime.fromisoformat(args.as_of.replace('Z', '+00:00'))
    if as_of.tzinfo is None:
        raise ValueError('--as-of must include timezone')

    tianjin_records = [
        record for record in records
        if str((record.get('facts') or {}).get('market_code') or '').strip().upper() == 'TJ'
    ]
    regional_records = [
        record for record in records
        if str((record.get('facts') or {}).get('market_code') or '').strip().upper() != 'TJ'
    ]

    # Critical boundary: the Tianjin notice-event store carries no market key, so
    # it is applied to Tianjin records only. Regional events carry an explicit
    # market_code and are keyed (market, project number) inside the builder, so
    # a matching number in another province can never inherit a correction or
    # termination. Awards follow the same boundary.
    tianjin_snapshot = build_public_snapshot(tianjin_records, as_of, notice_events, tianjin_awards)
    regional_snapshot = build_public_snapshot(regional_records, as_of, regional_events, regional_awards)
    snapshot = combine_snapshots(tianjin_snapshot, regional_snapshot, records, as_of)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(
        f'published {len(snapshot["cards"])} cards from '
        f'{len(tianjin_records)} Tianjin + {len(regional_records)} regional records; '
        f'Tianjin events={len(notice_events)} regional events={len(regional_events)} awards={len(award_records)} -> {args.output}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
