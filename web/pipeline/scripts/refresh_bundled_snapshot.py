#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402

OPTIONAL_LIVE_SOURCES = (
    ('tianjin_live_tjnothop_records.json', 'live Tianjin Hospital state'),
    ('tianjin_live_tjzxfc_records.json', 'live Central Obstetrics and Gynecology Hospital state'),
    ('tianjin_live_tjzyefy_records.json', 'live TJZYEFY state'),
    ('tianjin_live_tjzyefy_intent_records.json', 'live TJZYEFY procurement-intent state'),
    ('tianjin_live_teda_records.json', 'live TEDA Hospital state'),
    ('tianjin_live_tjfch_records.json', 'live First Central Hospital state'),
)


def load_array(path: Path, *, label: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError(f'{label} must contain a JSON array')
    return payload


def load_optional_array(path: Path, *, label: str) -> list[dict]:
    if not path.exists():
        return []
    return load_array(path, label=label)


def parse_as_of(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('--as-of must include timezone')
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Refresh the bundled frontend-safe snapshot from all verified live source files currently present.'
    )
    parser.add_argument(
        '--as-of',
        default=None,
        help='Optional ISO-8601 snapshot clock with timezone. Defaults to the currently bundled snapshot clock.',
    )
    args = parser.parse_args()

    output = WEB_ROOT / 'public' / 'data' / 'today-actions.public.json'
    current = json.loads(output.read_text(encoding='utf-8'))
    published_as_of = parse_as_of(args.as_of or current['snapshot_as_of'])

    live_ccgp = load_array(
        PIPELINE_ROOT / 'data' / 'tianjin_live_ccgp_records.json',
        label='live CCGP state',
    )
    live_tjmugh = load_array(
        PIPELINE_ROOT / 'data' / 'tianjin_live_tjmugh_records.json',
        label='live TMUGH state',
    )

    ccgp_source = live_ccgp if live_ccgp else load_array(
        PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json',
        label='CCGP seed',
    )
    tmugh_source = live_tjmugh if live_tjmugh else load_array(
        PIPELINE_ROOT / 'data' / 'tianjin_official_institution_seed.json',
        label='TMUGH seed',
    )

    records = [*ccgp_source, *tmugh_source]
    for filename, label in OPTIONAL_LIVE_SOURCES:
        records.extend(load_optional_array(PIPELINE_ROOT / 'data' / filename, label=label))

    notice_events = load_array(
        PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json',
        label='notice events',
    )

    payload = build_public_snapshot(records, published_as_of, notice_events)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(
        'Bundled snapshot refreshed with current ranking logic '
        f'from {len(records)} verified canonical records'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
