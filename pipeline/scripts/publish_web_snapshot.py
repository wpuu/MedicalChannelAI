#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402

DEFAULT_INPUTS = [
    PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json',
    PIPELINE_ROOT / 'data' / 'tianjin_official_institution_seed.json',
]
DEFAULT_EVENT_INPUTS = [PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json']
DEFAULT_OUTPUT = REPO_ROOT / 'web' / 'public' / 'data' / 'today-actions.public.json'


def load_arrays(paths: list[Path], *, label: str) -> list[dict]:
    merged: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, list):
            raise ValueError(f'{label} must contain a JSON array: {path}')
        merged.extend(payload)
    return merged


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
        help='Canonical-record JSON array. Repeat to combine seed and live state. Defaults to verified CCGP + hospital seeds.',
    )
    parser.add_argument(
        '--event-input',
        action='append',
        type=Path,
        default=None,
        help='Notice-event JSON array. Repeat to combine retained event stores.',
    )
    args = parser.parse_args()

    input_paths = args.input or DEFAULT_INPUTS
    event_paths = args.event_input or DEFAULT_EVENT_INPUTS
    records = load_arrays(input_paths, label='input')
    notice_events = load_arrays(event_paths, label='event input')

    as_of = datetime.fromisoformat(args.as_of.replace('Z', '+00:00'))
    if as_of.tzinfo is None:
        raise ValueError('--as-of must include timezone')
    snapshot = build_public_snapshot(records, as_of, notice_events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(
        f'published {len(snapshot["cards"])} cards from '
        f'{len(input_paths)} record stores + {len(event_paths)} event stores -> {args.output}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
