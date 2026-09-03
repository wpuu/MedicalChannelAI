from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class AiDiscoveryPilotAuthTests(unittest.TestCase):
    def test_private_pilot_radar_requires_authenticated_session(self) -> None:
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn("import { authenticatedUser } from '../_auth.js'", endpoint)
        self.assertIn("import { privateDatabaseConfigured } from '../_privateDb.js'", endpoint)
        self.assertIn('function privatePilotEnabled()', endpoint)
        self.assertIn('async function requirePrivatePilotSession(request, response)', endpoint)
        self.assertIn("sendJson(response, 401, { error: 'AUTH_REQUIRED' })", endpoint)
        self.assertIn('if (!await requirePrivatePilotSession(request, response)) return', endpoint)

    def test_public_demo_keeps_same_origin_radar_without_private_account_dependency(self) -> None:
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn('if (!privatePilotEnabled()) return true', endpoint)
        self.assertIn('sameOriginAllowed(request)', endpoint)
        self.assertIn('rateLimited(request)', endpoint)

    def test_continuation_get_still_returns_method_not_allowed_before_auth(self) -> None:
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        method_guard = endpoint.index("if (request.method !== 'POST')")
        auth_guard = endpoint.index('if (!await requirePrivatePilotSession(request, response)) return')
        continuation_dispatch = endpoint.index("if (routeName === 'continuation') return continuationDiscoveryHandler(request, response)", method_guard)
        self.assertLess(method_guard, auth_guard)
        self.assertLess(continuation_dispatch, auth_guard)


if __name__ == '__main__':
    unittest.main()
