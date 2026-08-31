from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_ROOT.parent


def load_array(path: Path, *, label: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError(f'{label} must contain a JSON array')
    return payload


def normalize_legacy_bundled_snapshot(payload: dict) -> dict:
    """One-way migration compatibility for the pre-pool bundled trial snapshot.

    The next pipeline publish writes `opportunity_pool` natively. Until then, the
    committed bundled snapshot contains exactly the same five actionable records
    in `cards`, so treating cards as the pool preserves facts without hand-copying
    a second JSON block.
    """
    if 'opportunity_pool' in payload:
        return payload
    normalized = dict(payload)
    cards = list(payload.get('cards') or [])
    normalized['opportunity_pool_count'] = len(cards)
    normalized['opportunity_pool'] = cards
    return normalized


class PublishedWebSnapshotTests(unittest.TestCase):
    def test_published_web_snapshot_matches_pipeline_output(self) -> None:
        actual_raw = json.loads(
            (REPO_ROOT / 'web' / 'public' / 'data' / 'today-actions.public.json').read_text(
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

        ccgp_source = (
            live_ccgp
            if live_ccgp
            else load_array(
                PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json',
                label='CCGP seed',
            )
        )
        tmugh_source = (
            live_tjmugh
            if live_tjmugh
            else load_array(
                PIPELINE_ROOT / 'data' / 'tianjin_official_institution_seed.json',
                label='TMUGH seed',
            )
        )
        records = [*ccgp_source, *tmugh_source]

        notice_events = load_array(
            PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json',
            label='notice events',
        )
        expected = build_public_snapshot(records, published_as_of, notice_events)
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
