from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'tianjin-medical-refresh.yml'
TEMP_PROBE_PATH = REPO_ROOT / '.github' / 'workflows' / 'tjmugh-live-probe.yml'


class TianjinRefreshWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding='utf-8')

    def test_teda_uses_shared_authoritative_refresh_clock(self) -> None:
        match = re.search(
            r'- name: Sync verified TEDA Hospital early-demand state\n(?P<body>.*?)(?=\n      - name:)',
            self.workflow,
            flags=re.S,
        )
        self.assertIsNotNone(match)
        body = match.group('body') if match else ''
        self.assertIn("--as-of '${{ steps.clock.outputs.as_of }}'", body)
        self.assertIn('--lookback-days 90', body)
        self.assertIn('--index-pages 4', body)
        self.assertIn('--max-candidates 20', body)
        self.assertIn('--delay-seconds 3', body)

    def test_teda_records_feed_public_snapshot_and_refresh_commit(self) -> None:
        self.assertIn('--records-output web/pipeline/data/tianjin_live_teda_records.json', self.workflow)
        self.assertIn('--report-output web/pipeline/data/tianjin_teda_sync_report.json', self.workflow)
        self.assertIn('--input web/pipeline/data/tianjin_live_teda_records.json', self.workflow)
        self.assertGreaterEqual(self.workflow.count('web/pipeline/data/tianjin_live_teda_records.json'), 4)
        self.assertIn('web/pipeline/data/tianjin_teda_sync_report.json', self.workflow)

    def test_first_central_hospital_uses_shared_clock_and_bounded_verified_sync(self) -> None:
        match = re.search(
            r'- name: Sync verified First Central Hospital in-hospital procurement state\n(?P<body>.*?)(?=\n      - name:)',
            self.workflow,
            flags=re.S,
        )
        self.assertIsNotNone(match)
        body = match.group('body') if match else ''
        self.assertIn('sync_tjfch_procurement.py', body)
        self.assertIn("--as-of '${{ steps.clock.outputs.as_of }}'", body)
        self.assertIn('--lookback-days 45', body)
        self.assertIn('--max-candidates 20', body)
        self.assertIn('--delay-seconds 3', body)
        self.assertIn('--existing-records-input web/pipeline/data/tianjin_live_tjfch_records.json', body)
        self.assertIn('--records-output web/pipeline/data/tianjin_live_tjfch_records.json', body)
        self.assertIn('--report-output web/pipeline/data/tianjin_tjfch_sync_report.json', body)

    def test_first_central_hospital_early_test_recruitment_runs_after_procurement(self) -> None:
        procurement = self.workflow.index('Sync verified First Central Hospital in-hospital procurement state')
        early = self.workflow.index('Sync verified First Central Hospital pre-procurement test recruitment')
        publish = self.workflow.index('Publish H5-safe verified snapshot')
        self.assertLess(procurement, early)
        self.assertLess(early, publish)

        match = re.search(
            r'- name: Sync verified First Central Hospital pre-procurement test recruitment\n(?P<body>.*?)(?=\n      - name:)',
            self.workflow,
            flags=re.S,
        )
        self.assertIsNotNone(match)
        body = match.group('body') if match else ''
        self.assertIn('sync_tjfch_test_recruitment.py', body)
        self.assertIn("--as-of '${{ steps.clock.outputs.as_of }}'", body)
        self.assertIn('--lookback-days 14', body)
        self.assertIn('--max-candidates 30', body)
        self.assertIn('--delay-seconds 3', body)
        self.assertIn('--existing-records-input web/pipeline/data/tianjin_live_tjfch_records.json', body)
        self.assertIn('--records-output web/pipeline/data/tianjin_live_tjfch_records.json', body)
        self.assertIn('--report-output web/pipeline/data/tianjin_tjfch_test_sync_report.json', body)

    def test_first_central_hospital_records_feed_public_snapshot_and_refresh_commit(self) -> None:
        self.assertIn('--input web/pipeline/data/tianjin_live_tjfch_records.json', self.workflow)
        self.assertGreaterEqual(self.workflow.count('web/pipeline/data/tianjin_live_tjfch_records.json'), 6)
        self.assertIn('web/pipeline/data/tianjin_tjfch_sync_report.json', self.workflow)
        self.assertIn('web/pipeline/data/tianjin_tjfch_test_sync_report.json', self.workflow)

    def test_temporary_teda_probe_workflow_is_removed(self) -> None:
        self.assertFalse(TEMP_PROBE_PATH.exists())


if __name__ == '__main__':
    unittest.main()
