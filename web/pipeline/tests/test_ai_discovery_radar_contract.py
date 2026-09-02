from __future__ import annotations

import json
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = WEB_ROOT.parent


class AiDiscoveryRadarContractTests(unittest.TestCase):
    def test_radar_uses_only_fixed_official_source_registry(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        registry = json.loads((WEB_ROOT / 'pipeline' / 'data' / 'agnes_discovery_sources.json').read_text(encoding='utf-8'))
        for source in registry['sources']:
            self.assertIn(source['source_id'], endpoint)
            for seed_url in source['seed_urls']:
                self.assertIn(seed_url, endpoint)
        self.assertIn("sourceIdFromBody(body)", endpoint)
        self.assertNotIn('body.url', endpoint)
        self.assertNotIn('body.seed_url', endpoint)

    def test_radar_is_shadow_only_and_rejects_ungrounded_model_urls(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn("production_data_mutated: false", endpoint)
        self.assertIn("DISCOVERED_UNVERIFIED", endpoint)
        self.assertIn("const anchor = allowed.get(rawUrl)", endpoint)
        self.assertIn("rejectedUngrounded += 1", endpoint)
        self.assertNotIn('publish_web_snapshot', endpoint)
        self.assertNotIn('private_followups', endpoint)

    def test_radar_has_same_origin_and_rate_limit_cost_guards(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn('sameOriginAllowed(request)', endpoint)
        self.assertIn('rateLimited(request)', endpoint)
        self.assertIn("AI_RADAR_RATE_LIMITED", endpoint)
        self.assertIn("MAX_ANCHORS = 80", endpoint)
        self.assertIn("PROVIDER_TIMEOUT_MS = 12_000", endpoint)

    def test_radar_page_is_reachable_and_explains_verification_boundary(self):
        app = (WEB_ROOT / 'src' / 'App.tsx').read_text(encoding='utf-8')
        layout = (WEB_ROOT / 'src' / 'components' / 'layout' / 'AppLayout.tsx').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('path="/radar"', app)
        self.assertIn('to="/radar"', layout)
        self.assertIn('不给AI预置商机', page)
        self.assertIn('不会自动进入正式商机池', page)
        self.assertIn('模型编造链接会被拒绝', page)


if __name__ == '__main__':
    unittest.main()
