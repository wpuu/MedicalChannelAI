from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class DiscoveryContinuationContractTests(unittest.TestCase):
    def setUp(self):
        self.endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover-continuation.js').read_text(encoding='utf-8')
        self.client = (WEB_ROOT / 'src' / 'services' / 'discoveryContinuationApi.ts').read_text(encoding='utf-8')
        self.ledger = (WEB_ROOT / 'src' / 'services' / 'discoveryContinuationLedger.ts').read_text(encoding='utf-8')

    def test_continuation_is_separate_shadow_segment_not_root_snapshot_replacement(self):
        self.assertIn("mode: 'AI_DISCOVERY_CONTINUATION_SHADOW'", self.endpoint)
        self.assertIn("analysis_version: CONTINUATION_ANALYSIS_VERSION", self.endpoint)
        self.assertIn('root_content_fingerprint: root.fingerprint', self.endpoint)
        self.assertIn('production_data_mutated: false', self.endpoint)
        self.assertNotIn('publish_web_snapshot', self.endpoint)
        self.assertNotIn('private_followups', self.endpoint)
        self.assertIn("fetch('/api/ai/discover-continuation'", self.client)
        self.assertNotIn("fetch('/api/ai/discover'", self.client)

    def test_only_complete_root_scans_with_real_coverage_gap_are_eligible(self):
        self.assertIn('if (raw.coverage_partial !== false) return null', self.endpoint)
        self.assertIn("raw.coverage_page_limit_applied !== true && raw.anchor_cap_applied !== true", self.endpoint)
        self.assertIn("AI_RADAR_CONTINUATION_NOT_ELIGIBLE", self.endpoint)
        self.assertIn('root.coverage_partial === false', self.ledger)
        self.assertIn('root.coverage_page_limit_applied === true || root.anchor_cap_applied === true', self.ledger)

    def test_resume_chain_is_bounded_and_reuses_last_checked_page_only_as_probe(self):
        self.assertIn('MAX_SEGMENT_ANCHORS = 80', self.endpoint)
        self.assertIn('MAX_SEGMENT_PAGE_FETCHES = 3', self.endpoint)
        self.assertIn('MAX_PRIOR_SEGMENTS = 5', self.endpoint)
        self.assertIn('previous.segments.length >= MAX_PRIOR_SEGMENTS', self.endpoint)
        self.assertIn('lastSegment?.nextResume ?? root.pageUrls[root.pageUrls.length - 1]', self.endpoint)
        self.assertIn('nextResumeFromPageUrl = page.url', self.endpoint)
        self.assertIn('segment_index: segmentIndex', self.endpoint)
        self.assertIn('next_resume_from_page_url', self.client)

    def test_root_and_prior_anchors_are_excluded_from_new_segments(self):
        self.assertIn('new Set(root.anchors.map((item) => item.url))', self.endpoint)
        self.assertIn('if (seenAnchors.has(anchor.url)) return null', self.endpoint)
        self.assertIn('!seenAnchorUrls.has(item.url)', self.endpoint)
        self.assertIn('CONTINUATION_SEGMENT_DUPLICATE_ANCHOR', self.ledger)

    def test_continuation_fetch_keeps_public_network_and_same_origin_guards(self):
        self.assertIn('sameOriginAllowed(request)', self.endpoint)
        self.assertIn('rateLimited(request)', self.endpoint)
        self.assertIn('assertPublicHostname', self.endpoint)
        self.assertIn('privateIp(', self.endpoint)
        self.assertIn("redirect: 'manual'", self.endpoint)
        self.assertIn("parsed.protocol !== 'https:'", self.endpoint)
        self.assertIn('canonicalOfficialUrl', self.endpoint)
        self.assertIn('MAX_SOURCE_BYTES', self.endpoint)
        self.assertIn('MAX_REQUEST_BODY_BYTES = 262_144', self.endpoint)

    def test_segment_ledger_is_independent_indexeddb_state_tied_to_root_fingerprint(self):
        self.assertIn("DB_NAME = 'medicalchannelai.discovery.continuation.local'", self.ledger)
        self.assertIn("indexedDB.open(DB_NAME, DB_VERSION)", self.ledger)
        self.assertIn('root_content_fingerprint', self.ledger)
        self.assertIn('stored.root_content_fingerprint === root.content_fingerprint', self.ledger)
        self.assertIn('appendContinuationSegment', self.ledger)
        self.assertIn('clearContinuationLedger', self.ledger)
        self.assertIn('MAX_SEGMENTS_PER_ROOT = 5', self.ledger)

    def test_client_fails_closed_on_segment_contract_mismatch(self):
        self.assertIn("body?.mode === 'AI_DISCOVERY_CONTINUATION_SHADOW'", self.client)
        self.assertIn("body?.schema_version === '0.1'", self.client)
        self.assertIn("body?.analysis_version === 'agnes-discovery-continuation-v1'", self.client)
        self.assertIn('body?.root_content_fingerprint === root.content_fingerprint', self.client)
        self.assertIn('body?.segment_index === previousSegments.length + 1', self.client)
        self.assertIn('body?.production_data_mutated === false', self.client)
        self.assertIn("throw new DiscoveryRadarError('AI_RADAR_RESPONSE_INVALID', 502)", self.client)


if __name__ == '__main__':
    unittest.main()
