from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / '.github' / 'workflows' / 'tianjin-medical-refresh.yml'
INCREMENTAL = REPO_ROOT / 'web' / 'collector_incremental.py'


class TjzyefyIntentDailyDeepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding='utf-8')

    def test_intent_daily_deep_is_bounded_and_uses_shared_clock(self) -> None:
        block_start = self.workflow.index(
            'Sync verified TCM Second Affiliated Hospital procurement-intent signals'
        )
        block_end = self.workflow.index(
            'Sync verified TEDA Hospital early-demand state',
            block_start,
        )
        block = self.workflow[block_start:block_end]
        self.assertIn('sync_tjzyefy_procurement_intent.py', block)
        self.assertIn("--as-of '${{ steps.clock.outputs.as_of }}'", block)
        self.assertIn('--lookback-days 30', block)
        self.assertIn('--max-candidates 20', block)
        self.assertIn('--delay-seconds 3', block)
        self.assertIn('tianjin_live_tjzyefy_intent_records.json', block)
        self.assertIn('tianjin_tjzyefy_intent_sync_report.json', block)

    def test_intent_records_feed_snapshot_and_verified_data_commit(self) -> None:
        self.assertGreaterEqual(
            self.workflow.count('tianjin_live_tjzyefy_intent_records.json'),
            4,
        )
        self.assertGreaterEqual(
            self.workflow.count('tianjin_tjzyefy_intent_sync_report.json'),
            2,
        )

    def test_intent_is_daily_deep_only_not_intraday(self) -> None:
        source = INCREMENTAL.read_text(encoding='utf-8')
        self.assertNotIn("'tjzyefy_intent'", source)
        self.assertNotIn('"tjzyefy_intent"', source)

    def test_daily_deep_still_uses_validated_self_hosted_runner(self) -> None:
        self.assertIn('- self-hosted', self.workflow)
        self.assertIn('- medicalchannelai-ci', self.workflow)
        self.assertNotIn('runs-on: ubuntu-latest', self.workflow)


if __name__ == '__main__':
    unittest.main()
