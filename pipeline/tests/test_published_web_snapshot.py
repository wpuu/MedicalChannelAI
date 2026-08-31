from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_ROOT.parent


class PublishedWebSnapshotTests(unittest.TestCase):
    def test_published_web_snapshot_matches_pipeline_output(self) -> None:
        actual = json.loads(
            (REPO_ROOT / 'web' / 'public' / 'data' / 'today-actions.public.json').read_text(
                encoding='utf-8'
            )
        )
        published_as_of = datetime.fromisoformat(actual['snapshot_as_of'].replace('Z', '+00:00'))

        live_path = PIPELINE_ROOT / 'data' / 'tianjin_live_ccgp_records.json'
        live_records = json.loads(live_path.read_text(encoding='utf-8'))
        if not isinstance(live_records, list):
            raise ValueError('live CCGP state must contain a JSON array')

        records = []
        ccgp_source = (
            live_records
            if live_records
            else json.loads(
                (PIPELINE_ROOT / 'data' / 'tianjin_verified_seed.json').read_text(
                    encoding='utf-8'
                )
            )
        )
        records.extend(ccgp_source)
        records.extend(
            json.loads(
                (PIPELINE_ROOT / 'data' / 'tianjin_official_institution_seed.json').read_text(
                    encoding='utf-8'
                )
            )
        )

        notice_events = json.loads(
            (PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json').read_text(encoding='utf-8')
        )
        expected = build_public_snapshot(records, published_as_of, notice_events)
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
