from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class AgnesCacheSourceFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        cls.client = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')

    def test_latest_ready_cache_is_separate_and_source_bound(self) -> None:
        self.assertIn("AI_CACHE_LATEST_PREFIX = 'medicalchannelai:agnes-discovery-latest:v1'", self.root)
        start = self.root.index('function aiLatestCacheKey(')
        end = self.root.index('function cachedCandidateRows', start)
        block = self.root[start:end]
        self.assertIn('ANALYSIS_VERSION', block)
        self.assertIn('aiCacheSourceSignature(source)', block)
        self.assertNotIn('fingerprint', block)

    def test_ready_refresh_persists_anchor_snapshot_and_latest_pointer(self) -> None:
        self.assertIn('anchor_snapshot: snapshotAnchors.map', self.root)
        self.assertIn('writeAiCache(aiLatestCacheKey(source), cacheValue, AI_CACHE_READY_TTL_SECONDS)', self.root)
        self.assertIn('snapshotAnchors: anchors', self.root)

    def test_source_failure_can_return_latest_ready_cache_but_force_ai_cannot(self) -> None:
        self.assertIn("sourceMessage.startsWith('SOURCE_') && body?.force_ai !== true", self.root)
        self.assertIn("cacheStatus: 'SERVER_AI_CACHE_SOURCE_UNAVAILABLE'", self.root)
        self.assertIn('coverage: fallbackCoverage', self.root)
        self.assertIn('partial: true', self.root)
        self.assertIn('errorCode: sourceMessage', self.root)

    def test_latest_cache_is_revalidated_against_anchor_snapshot(self) -> None:
        self.assertIn('previousAnchorSnapshot(value, source)', self.root)
        self.assertIn('anchorFingerprint(anchors) !== fingerprint', self.root)
        self.assertIn('validateAiCacheEntry(value, source, anchors, fingerprint)', self.root)

    def test_client_accepts_source_unavailable_cache_status(self) -> None:
        self.assertIn("| 'SERVER_AI_CACHE_SOURCE_UNAVAILABLE'", self.client)


if __name__ == '__main__':
    unittest.main()
