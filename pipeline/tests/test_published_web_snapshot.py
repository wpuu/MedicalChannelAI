from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_ROOT.parent
PUBLISHED_AS_OF = datetime.fromisoformat('2026-08-31T17:56:00+08:00')


class PublishedWebSnapshotTests(unittest.TestCase):
    def test_published_web_snapshot_matches_pipeline_output(self) -> None:
        records = []
        for name in ('tianjin_verified_seed.json', 'tianjin_official_institution_seed.json'):
            payload = json.loads((PIPELINE_ROOT / 'data' / name).read_text(encoding='utf-8'))
            records.extend(payload)

        notice_events = json.loads(
            (PIPELINE_ROOT / 'data' / 'tianjin_notice_events.json').read_text(encoding='utf-8')
        )
        expected = build_public_snapshot(records, PUBLISHED_AS_OF, notice_events)
        actual = json.loads(
            (REPO_ROOT / 'web' / 'public' / 'data' / 'today-actions.public.json').read_text(
                encoding='utf-8'
            )
        )
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
