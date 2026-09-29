from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from scripts.publish_web_snapshot import combine_snapshots

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PIPELINE_ROOT.parent
REPO_ROOT = WEB_ROOT.parent

OPTIONAL_LIVE_SOURCES = (
    ('tianjin_live_tjnothop_records.json', 'live Tianjin Hospital state'),
    ('tianjin_live_tjzxfc_records.json', 'live Central Obstetrics and Gynecology Hospital state'),
    ('tianjin_live_tjzyefy_records.json', 'live TJZYEFY state'),
    ('tianjin_live_tjzyefy_intent_records.json', 'live TJZYEFY procurement-intent state'),
    ('tianjin_live_teda_records.json', 'live TEDA state'),
    ('tianjin_live_tjfch_records.json', 'live First Central Hospital state'),
)
REGIONAL_LIVE_SOURCE = ('regional_live_ccgp_records.json', 'live regional CCGP state')


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


def ensure_tianjin_market_metadata(records: list[dict]) -> None:
    for record in records:
        facts = record.setdefault('facts', {})
        facts['market_code'] = 'TJ'
        facts.setdefault('market_name', '天津')
        facts.setdefault('market_admin_code', '120000')


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

        ccgp_source = live_ccgp if live_ccgp else load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json', label='CCGP seed'
        )
        tmugh_source = live_tjmugh if live_tjmugh else load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_official_institution_seed.json', label='TMUGH seed'
        )
        tianjin_records = [*ccgp_source, *tmugh_source]
        for filename, label in OPTIONAL_LIVE_SOURCES:
            tianjin_records.extend(
                load_optional_array(PIPELINE_ROOT / 'data' / filename, label=label)
            )
        ensure_tianjin_market_metadata(tianjin_records)

        regional_filename, regional_label = REGIONAL_LIVE_SOURCE
        regional_records = load_optional_array(
            PIPELINE_ROOT / 'data' / regional_filename,
            label=regional_label,
        )

        notice_events = load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json', label='notice events'
        )
        award_records = load_optional_array(
            PIPELINE_ROOT / 'data' / 'tianjin_award_records.json', label='Tianjin award results'
        )
        tianjin_snapshot = build_public_snapshot(
            tianjin_records,
            published_as_of,
            notice_events,
            award_records,
        )
        regional_snapshot = build_public_snapshot(
            regional_records,
            published_as_of,
            [],
        )
        expected = combine_snapshots(
            tianjin_snapshot,
            regional_snapshot,
            [*tianjin_records, *regional_records],
            published_as_of,
        )
        self.assertEqual(actual, expected)

    def test_local_refresh_source_set_matches_daily_deep_snapshot_inputs(self) -> None:
        refresh_source = (PIPELINE_ROOT / 'scripts' / 'refresh_bundled_snapshot.py').read_text(
            encoding='utf-8'
        )
        publisher_source = (PIPELINE_ROOT / 'scripts' / 'publish_web_snapshot.py').read_text(
            encoding='utf-8'
        )
        daily_workflow = (REPO_ROOT / '.github' / 'workflows' / 'tianjin-medical-refresh.yml').read_text(
            encoding='utf-8'
        )
        filenames = (
            'tianjin_live_ccgp_records.json',
            'tianjin_live_tjmugh_records.json',
            'tianjin_live_tjnothop_records.json',
            'tianjin_live_tjzxfc_records.json',
            'tianjin_live_tjzyefy_records.json',
            'tianjin_live_tjzyefy_intent_records.json',
            'tianjin_live_teda_records.json',
            'tianjin_live_tjfch_records.json',
        )
        for filename in filenames:
            with self.subTest(filename=filename):
                self.assertIn(filename, refresh_source)
                self.assertIn(f'--input web/pipeline/data/{filename}', daily_workflow)

        regional_filename = REGIONAL_LIVE_SOURCE[0]
        self.assertIn(regional_filename, refresh_source)
        self.assertIn(regional_filename, publisher_source)
        self.assertIn('publish_web_snapshot.py', daily_workflow)

        # 中标/成交 award store: refreshed by the workflow, consumed by both publishers.
        self.assertIn('tianjin_award_records.json', refresh_source)
        self.assertIn('tianjin_award_records.json', publisher_source)
        self.assertIn('sync_ccgp_awards.py', daily_workflow)
        self.assertIn('--award-input web/pipeline/data/tianjin_award_records.json', daily_workflow)


if __name__ == '__main__':
    unittest.main()
