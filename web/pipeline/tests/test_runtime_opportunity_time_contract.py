from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class RuntimeOpportunityTimeContractTests(unittest.TestCase):
    def test_real_pilot_rechecks_verified_deadlines_at_request_time(self) -> None:
        helper = (WEB_ROOT / 'api' / '_runtimeOpportunityTime.js').read_text(encoding='utf-8')
        pilot = (WEB_ROOT / 'api' / '_pilotOpportunity.js').read_text(encoding='utf-8')
        self.assertIn('runtimeRefreshSnapshotPool', helper)
        self.assertIn("action.mode === 'ARCHIVE'", helper)
        self.assertIn("mode: 'LATE_WINDOW', interventionPoints: 8", helper)
        self.assertIn('deadlineUrgencyPoints(facts, now)', helper)
        self.assertIn('publicationFreshnessPoints(facts, now)', helper)
        self.assertIn("import { runtimeRefreshSnapshotPool } from './_runtimeOpportunityTime.js'", pilot)
        self.assertIn('runtimeSnapshotOpportunityPool(snapshot)', pilot)

    def test_runtime_layer_does_not_create_or_rewrite_public_facts(self) -> None:
        helper = (WEB_ROOT / 'api' / '_runtimeOpportunityTime.js').read_text(encoding='utf-8')
        self.assertIn('...card,', helper)
        self.assertNotIn('facts: {', helper)
        self.assertNotIn('registration_deadline:', helper)
        self.assertNotIn('bid_deadline:', helper)

    def test_verified_trial_keeps_runtime_deadline_and_recomputes_temporal_score(self) -> None:
        static = (WEB_ROOT / 'src' / 'services' / 'StaticSnapshotTodayActionsService.ts').read_text(encoding='utf-8')
        wrapper = (WEB_ROOT / 'src' / 'services' / 'RuntimeTrialTodayActionsService.ts').read_text(encoding='utf-8')
        index = (WEB_ROOT / 'src' / 'services' / 'index.ts').read_text(encoding='utf-8')
        self.assertIn('applyRuntimeActionability(', static)
        self.assertIn('LATE_WINDOW_POINTS = 8', static)
        self.assertIn('DEADLINE_URGENCY_MAX_POINTS = 10', wrapper)
        self.assertIn('PUBLICATION_FRESHNESS_MAX_POINTS = 7', wrapper)
        self.assertIn('refreshTrialTemporalPriority', wrapper)
        self.assertIn('new RuntimeTrialTodayActionsService(', index)


if __name__ == '__main__':
    unittest.main()
