from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = WEB_ROOT.parent
ANALYZE = WEB_ROOT / 'api' / 'ai' / 'analyze.js'
AI_CLIENT = WEB_ROOT / 'src' / 'services' / 'aiDecisionApi.ts'
OUTREACH = WEB_ROOT / 'src' / 'components' / 'followup' / 'OutreachDrawer.tsx'
VERIFIED_SNAPSHOT = WEB_ROOT / 'api' / '_verifiedSnapshot.js'
PUBLIC_SNAPSHOT = WEB_ROOT / 'api' / 'public-snapshot.js'
PUBLISH_WEB = WEB_ROOT / 'pipeline' / 'scripts' / 'publish_web_snapshot.py'
TIANJIN_WORKFLOW = REPO_ROOT / '.github' / 'workflows' / 'tianjin-medical-refresh.yml'
REGIONAL_WORKFLOW = REPO_ROOT / '.github' / 'workflows' / 'regional-medical-refresh.yml'


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

    def test_runtime_publish_lane_is_distinct_from_tianjin_only_collector_and_monotonic(self) -> None:
        source = VERIFIED_SNAPSHOT.read_text(encoding='utf-8')

        self.assertIn(
            "PUBLISHED_RUNTIME_SNAPSHOT_KEY = 'medicalchannelai:verified-snapshot:published:v1'",
            source,
        )
        self.assertIn('selectPublishedRuntimeSnapshot', source)
        self.assertIn('publishVerifiedSnapshotToRuntimeCache', source)
        self.assertIn('if (candidateMs <= baselineMs) return null', source)
        self.assertIn("throw new Error('RUNTIME_SNAPSHOT_ROLLBACK_REJECTED')", source)
        self.assertIn("throw new Error('RUNTIME_SNAPSHOT_REVISION_CONFLICT')", source)
        self.assertIn('RUNTIME_SNAPSHOT_FUTURE_TOLERANCE_MS = 15 * 60 * 1000', source)
        self.assertIn("collector's legacy \"latest:v1\" key is intentionally not", source)

    def test_same_origin_publish_endpoint_fails_closed_and_readback_is_not_cdn_cached(self) -> None:
        source = PUBLIC_SNAPSHOT.read_text(encoding='utf-8')

        self.assertIn("process.env.VERIFIED_SNAPSHOT_PUBLISH_TOKEN", source)
        self.assertIn('timingSafeEqual', source)
        self.assertIn("{ error: 'VERIFIED_SNAPSHOT_PUBLISH_NOT_CONFIGURED' }", source)
        self.assertIn("{ error: 'UNAUTHORIZED' }", source)
        self.assertIn("request.method === 'PUT' || request.method === 'POST'", source)
        self.assertIn("'no-store, max-age=0'", source)
        self.assertNotIn('return sendJson(response, 200, snapshot, { cacheable: true })', source)

    def test_both_daily_refreshes_can_publish_and_roundtrip_the_combined_snapshot(self) -> None:
        tianjin = TIANJIN_WORKFLOW.read_text(encoding='utf-8')
        regional = REGIONAL_WORKFLOW.read_text(encoding='utf-8')
        publisher = PUBLISH_WEB.read_text(encoding='utf-8')

        for workflow in (tianjin, regional):
            self.assertIn('VERIFIED_SNAPSHOT_PUBLISH_URL', workflow)
            self.assertIn('VERIFIED_SNAPSHOT_PUBLISH_TOKEN', workflow)
            self.assertIn('VERIFIED_SNAPSHOT_READ_URL', workflow)
            self.assertIn('publish_snapshot_http.py', workflow)
            self.assertIn('verify_snapshot_roundtrip.py', workflow)

        self.assertLess(
            regional.index('Publish combined verified snapshot'),
            regional.index('Publish and verify optional external snapshot'),
        )
        self.assertIn('REGIONAL_INPUT = PIPELINE_ROOT / "data" / "regional_live_ccgp_records.json"', publisher)
        self.assertIn('if REGIONAL_INPUT.exists() and REGIONAL_INPUT not in input_paths:', publisher)
        self.assertIn('input_paths.append(REGIONAL_INPUT)', publisher)


if __name__ == '__main__':
    unittest.main()
