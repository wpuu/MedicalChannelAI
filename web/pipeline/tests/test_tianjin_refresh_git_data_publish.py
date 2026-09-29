from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'tianjin-medical-refresh.yml'

EXPECTED_GENERATED_PATHS = {
    'web/pipeline/data/tianjin_live_ccgp_records.json',
    'web/pipeline/data/tianjin_live_tjmugh_records.json',
    'web/pipeline/data/tianjin_live_tjnothop_records.json',
    'web/pipeline/data/tianjin_live_tjzxfc_records.json',
    'web/pipeline/data/tianjin_live_tjzyefy_records.json',
    'web/pipeline/data/tianjin_live_tjzyefy_intent_records.json',
    'web/pipeline/data/tianjin_live_teda_records.json',
    'web/pipeline/data/tianjin_live_tjfch_records.json',
    'web/pipeline/data/tianjin_notice_events.json',
    'web/pipeline/data/tianjin_award_records.json',
    'web/pipeline/data/tianjin_award_sync_report.json',
    'web/pipeline/data/tianjin_sync_report.json',
    'web/pipeline/data/tianjin_tjmugh_sync_report.json',
    'web/pipeline/data/tianjin_tjnothop_sync_report.json',
    'web/pipeline/data/tianjin_tjzxfc_sync_report.json',
    'web/pipeline/data/tianjin_tjzyefy_sync_report.json',
    'web/pipeline/data/tianjin_tjzyefy_intent_sync_report.json',
    'web/pipeline/data/tianjin_teda_sync_report.json',
    'web/pipeline/data/tianjin_tjfch_sync_report.json',
    'web/pipeline/data/tianjin_tjfch_test_sync_report.json',
    'web/public/data/today-actions.public.json',
}


class TianjinRefreshGitDataPublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
        match = re.search(
            r'- name: Commit verified refresh only when data changed\n(?P<body>.*)$',
            cls.workflow,
            flags=re.S,
        )
        if match is None:
            raise AssertionError('Tianjin refresh commit step is missing')
        cls.commit_step = match.group('body')

    def test_refresh_commit_uses_existing_git_data_api_publisher(self) -> None:
        self.assertIn('GITHUB_TOKEN: ${{ github.token }}', self.commit_step)
        self.assertIn('python3 web/pipeline/scripts/publish_generated_data_github.py', self.commit_step)
        self.assertIn('--branch "${GITHUB_REF_NAME}"', self.commit_step)
        self.assertIn("--message 'data: refresh Tianjin verified opportunities'", self.commit_step)

    def test_refresh_commit_has_no_local_git_cli_dependency(self) -> None:
        for forbidden in ('git config', 'git add', 'git diff', 'git commit', 'git push'):
            self.assertNotIn(forbidden, self.commit_step)

    def test_refresh_commit_preserves_all_generated_targets(self) -> None:
        for path in EXPECTED_GENERATED_PATHS:
            self.assertIn(path, self.commit_step)
        generated_lines = {
            line.strip().rstrip('\\').strip()
            for line in self.commit_step.splitlines()
            if line.strip().startswith(('web/pipeline/data/', 'web/public/data/'))
        }
        self.assertEqual(generated_lines, EXPECTED_GENERATED_PATHS)

    def test_workflow_keeps_contents_write_permission(self) -> None:
        self.assertIn('permissions:\n  contents: write', self.workflow)


if __name__ == '__main__':
    unittest.main()
