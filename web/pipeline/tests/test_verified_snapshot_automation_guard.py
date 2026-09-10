from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
ANALYZE = WEB_ROOT / 'api' / 'ai' / 'analyze.js'
AI_CLIENT = WEB_ROOT / 'src' / 'services' / 'aiDecisionApi.ts'
OUTREACH = WEB_ROOT / 'src' / 'components' / 'followup' / 'OutreachDrawer.tsx'
COLLECTOR_RUNTIME = WEB_ROOT / 'collector_runtime.py'
VERIFIED_SNAPSHOT = WEB_ROOT / 'api' / '_verifiedSnapshot.js'


class VerifiedSnapshotAutomationGuardTests(unittest.TestCase):
    def test_private_ai_wrapper_rejects_stale_invalid_and_future_snapshot_before_opportunity_use(self) -> None:
        source = ANALYZE.read_text(encoding='utf-8')

        self.assertIn('MAX_VERIFIED_SNAPSHOT_AGE_MS = 30 * 60 * 60 * 1000', source)
        self.assertIn('MAX_VERIFIED_SNAPSHOT_FUTURE_SKEW_MS = 10 * 60 * 1000', source)
        self.assertIn("return 'VERIFIED_SNAPSHOT_NOT_FRESH'", source)
        self.assertIn('const snapshotError = verifiedSnapshotAutomationError(snapshot)', source)
        self.assertIn('if (snapshotError) return sendJson(response, 409, { error: snapshotError })', source)

        # The freshness fence must run before a verified card is selected or
        # before route=outreach can generate outbound copy.
        self.assertLess(
            source.index('const snapshotError = verifiedSnapshotAutomationError(snapshot)'),
            source.index('const card = rawVerifiedCard(snapshot, opportunityId)'),
        )
        self.assertLess(
            source.index('if (snapshotError) return sendJson(response, 409, { error: snapshotError })'),
            source.index("if (routeName(request) === 'outreach')"),
        )

    def test_ai_and_outreach_clients_explain_server_freshness_rejection(self) -> None:
        ai = AI_CLIENT.read_text(encoding='utf-8')
        outreach = OUTREACH.read_text(encoding='utf-8')

        self.assertIn("cause.code === 'VERIFIED_SNAPSHOT_NOT_FRESH'", ai)
        self.assertIn('待数据刷新后再使用AI分析', ai)
        self.assertIn("error.message === 'VERIFIED_SNAPSHOT_NOT_FRESH'", outreach)
        self.assertIn('待数据刷新后再生成沟通草稿', outreach)

    def test_native_collector_and_snapshot_reader_share_stable_runtime_key_with_monotonic_guard(self) -> None:
        collector = COLLECTOR_RUNTIME.read_text(encoding='utf-8')
        reader = VERIFIED_SNAPSHOT.read_text(encoding='utf-8')
        stable_key = 'medicalchannelai:verified-snapshot:latest:v1'

        self.assertIn(f'LATEST_RUNTIME_SNAPSHOT_KEY = "{stable_key}"', collector)
        self.assertIn(f"COLLECTOR_RUNTIME_SNAPSHOT_KEY = '{stable_key}'", reader)
        self.assertIn('selectCollectorRuntimeSnapshot', reader)
        self.assertIn('if (candidateMs <= baselineMs) return null', reader)
        self.assertIn('RUNTIME_SNAPSHOT_FUTURE_TOLERANCE_MS = 15 * 60 * 1000', reader)
        self.assertLess(
            reader.index('cache.get(COLLECTOR_RUNTIME_SNAPSHOT_KEY)'),
            reader.index('cache.get(BUNDLED_RUNTIME_SNAPSHOT_KEY)'),
        )


if __name__ == '__main__':
    unittest.main()
