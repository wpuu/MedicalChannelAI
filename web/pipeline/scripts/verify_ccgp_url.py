#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline.ccgp_detail import (  # noqa: E402
    fetch_ccgp_detail_html,
    parse_ccgp_public_tender_html,
)


def stable_opportunity_id(url: str) -> str:
    digest = hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]
    return f'ccgp_{digest}'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Fetch one official CCGP public-tender detail page and emit a VERIFIED canonical record.'
    )
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--observed-at', default=None, help='ISO-8601; defaults to current UTC time')
    parser.add_argument('--opportunity-id', default=None)
    args = parser.parse_args()

    observed_at = args.observed_at or datetime.now(timezone.utc).isoformat()
    html = fetch_ccgp_detail_html(args.url)
    record = parse_ccgp_public_tender_html(
        html,
        source_url=args.url,
        observed_at=observed_at,
        opportunity_id=args.opportunity_id or stable_opportunity_id(args.url),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(f'verified {record["facts"]["project_number"]} -> {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
