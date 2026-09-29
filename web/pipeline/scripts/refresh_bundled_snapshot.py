#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from medical_channel_pipeline import build_public_snapshot  # noqa: E402
from publish_web_snapshot import combine_snapshots  # noqa: E402

OPTIONAL_LIVE_SOURCES = (
    ('tianjin_live_tjnothop_records.json', 'live Tianjin Hospital state'),
    ('tianjin_live_tjzxfc_records.json', 'live Central Obstetrics and Gynecology Hospital state'),
    ('tianjin_live_tjzyefy_records.json', 'live TJZYEFY state'),
    ('tianjin_live_tjzyefy_intent_records.json', 'live TJZYEFY procurement-intent state'),
    ('tianjin_live_teda_records.json', 'live TEDA Hospital state'),
    ('tianjin_live_tjfch_records.json', 'live First Central Hospital state'),
)
REGIONAL_LIVE_SOURCE = (
    'regional_live_ccgp_records.json',
    'live regional CCGP state',
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


def ensure_tianjin_market_metadata(records: list[dict]) -> None:
    for record in records:
        facts = record.setdefault('facts', {})
        market_code = str(facts.get('market_code') or '').strip().upper()
        if market_code and market_code != 'TJ':
            raise ValueError(
                f'TIANJIN_SOURCE_MARKET_MISMATCH:{record.get("opportunity_id")}:{market_code}'
            )
        facts['market_code'] = 'TJ'
        facts.setdefault('market_name', '天津')
        facts.setdefault('market_admin_code', '120000')


def validate_regional_market_metadata(records: list[dict]) -> None:
    for record in records:
        facts = record.get('facts') or {}
        market_code = str(facts.get('market_code') or '').strip().upper()
        market_name = str(facts.get('market_name') or '').strip()
        market_admin_code = str(facts.get('market_admin_code') or '').strip()
        if not market_code or market_code == 'TJ':
            raise ValueError(
                f'REGIONAL_MARKET_CODE_INVALID:{record.get("opportunity_id")}:{market_code}'
            )
        if not market_name or not market_admin_code:
            raise ValueError(
                f'REGIONAL_MARKET_METADATA_REQUIRED:{record.get("opportunity_id")}'
            )


def published_market_counts(payload: dict) -> str:
    counts = Counter(
        str((card.get('facts') or {}).get('market_code') or '').strip().upper() or 'UNKNOWN'
        for card in payload.get('opportunity_pool') or []
    )
    return ','.join(f'{code}:{counts[code]}' for code in sorted(counts))


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

    tianjin_records = [*ccgp_source, *tmugh_source]
    for filename, label in OPTIONAL_LIVE_SOURCES:
        tianjin_records.extend(load_optional_array(PIPELINE_ROOT / 'data' / filename, label=label))
    ensure_tianjin_market_metadata(tianjin_records)

    regional_filename, regional_label = REGIONAL_LIVE_SOURCE
    regional_records = load_optional_array(
        PIPELINE_ROOT / 'data' / regional_filename,
        label=regional_label,
    )
    validate_regional_market_metadata(regional_records)

    notice_events = load_array(
        PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json',
        label='notice events',
    )
    # 中标/成交 results are a separate canonical store; they retire awarded
    # projects from the pool and feed the compact public award ledger.
    award_records = load_optional_array(
        PIPELINE_ROOT / 'data' / 'tianjin_award_records.json',
        label='Tianjin award results',
    )

    # Keep Tianjin notice events isolated from regional records. Regional event
    # monitoring remains disabled until those events carry explicit market identity.
    tianjin_snapshot = build_public_snapshot(tianjin_records, published_as_of, notice_events, award_records)
    regional_snapshot = build_public_snapshot(regional_records, published_as_of, [])
    payload = combine_snapshots(
        tianjin_snapshot,
        regional_snapshot,
        [*tianjin_records, *regional_records],
        published_as_of,
    )
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(
        'Bundled snapshot refreshed with current ranking logic from '
        f'{len(tianjin_records)} Tianjin + {len(regional_records)} regional verified canonical records; '
        f'published opportunities={payload["opportunity_pool_count"]}; '
        f'awarded retired={payload["awarded_project_count"]}; award ledger={len(payload["award_ledger"])}; '
        f'markets={published_market_counts(payload)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
