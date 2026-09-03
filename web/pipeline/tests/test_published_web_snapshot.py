from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PIPELINE_ROOT.parent


def load_array(path: Path, *, label: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError(f'{label} must contain a JSON array')
    return payload


def load_optional_array(path: Path, *, label: str) -> list[dict]:
    if not path.exists():
        return []
    return load_array(path, label=label)


def _normalize_legacy_card(card: dict) -> dict:
    normalized = dict(card)
    facts = dict(normalized.get('facts') or {})
    facts.setdefault('registration_deadline_date', None)
    if 'registration_deadline_precision' not in facts:
        if facts.get('registration_deadline'):
            facts['registration_deadline_precision'] = 'MINUTE'
        elif facts.get('registration_deadline_date'):
            facts['registration_deadline_precision'] = 'DAY'
        else:
            facts['registration_deadline_precision'] = None
    normalized['facts'] = facts

    priority = dict(normalized.get('priority') or {})
    components = []
    for component in list(priority.get('components') or []):
        row = dict(component)
        if row.get('code') == 'INTERVENTION_STAGE':
            paths = list(row.get('opportunity_paths') or [])
            if 'facts.registration_deadline_date' not in paths:
                try:
                    bid_index = paths.index('facts.bid_deadline')
                except ValueError:
                    bid_index = len(paths)
                paths.insert(bid_index, 'facts.registration_deadline_date')
            row['opportunity_paths'] = paths
        components.append(row)
    priority['components'] = components
    normalized['priority'] = priority
    return normalized


def normalize_legacy_bundled_snapshot(payload: dict) -> dict:
    normalized = dict(payload)
    cards = [_normalize_legacy_card(card) for card in list(payload.get('cards') or [])]
    normalized['cards'] = cards

    raw_pool = payload.get('opportunity_pool')
    pool = (
        [_normalize_legacy_card(card) for card in raw_pool]
        if isinstance(raw_pool, list)
        else list(cards)
    )
    normalized['opportunity_pool_count'] = payload.get('opportunity_pool_count', len(pool))
    normalized['opportunity_pool'] = pool
    return normalized


class PublishedWebSnapshotTests(unittest.TestCase):
    def test_published_web_snapshot_matches_pipeline_output(self) -> None:
        actual_raw = json.loads(
            (WEB_ROOT / 'public' / 'data' / 'today-actions.public.json').read_text(
                encoding='utf-8'
            )
        )
        actual = normalize_legacy_bundled_snapshot(actual_raw)
        published_as_of = datetime.fromisoformat(actual['snapshot_as_of'].replace('Z', '+00:00'))

        live_ccgp = load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_live_ccgp_records.json',
            label='live CCGP state',
        )
        live_tjmugh = load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_live_tjmugh_records.json',
            label='live TMUGH state',
        )
        live_tjnothop = load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_live_tjnothop_records.json',
            label='live Tianjin Hospital state',
        )
        live_teda = load_optional_array(
            PIPELINE_ROOT / 'data' / 'tianjin_live_teda_records.json',
            label='live TEDA state',
        )
        live_tjfch = load_optional_array(
            PIPELINE_ROOT / 'data' / 'tianjin_live_tjfch_records.json',
            label='live First Central Hospital state',
        )

        ccgp_source = live_ccgp if live_ccgp else load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json', label='CCGP seed'
        )
        tmugh_source = live_tjmugh if live_tjmugh else load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_official_institution_seed.json', label='TMUGH seed'
        )
        records = [*ccgp_source, *tmugh_source, *live_tjnothop, *live_teda, *live_tjfch]

        notice_events = load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json', label='notice events'
        )
        expected = build_public_snapshot(records, published_as_of, notice_events)
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
