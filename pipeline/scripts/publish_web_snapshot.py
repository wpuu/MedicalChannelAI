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
DEFAULT_OUTPUT = REPO_ROOT / 'web' / 'public' / 'data' / 'today-actions.public.json'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Regenerate the verified static-trial snapshot consumed by web/.'
    )
    parser.add_argument('--as-of', required=True, help='ISO-8601 timestamp with timezone')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    records = []
    for path in DEFAULT_INPUTS:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, list):
            raise ValueError(f'input must contain a JSON array: {path}')
        records.extend(payload)

    as_of = datetime.fromisoformat(args.as_of.replace('Z', '+00:00'))
    snapshot = build_public_snapshot(records, as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(f'published {len(snapshot["cards"])} cards -> {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
