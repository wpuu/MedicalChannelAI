from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class AuthHandoffPressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api = (WEB_ROOT / 'src' / 'services' / 'apiConfig.ts').read_text(encoding='utf-8')
        cls.guard = (WEB_ROOT / 'src' / 'components' / 'auth' / 'RequirePilotSession.tsx').read_text(encoding='utf-8')

    def test_successful_login_and_register_create_short_one_shot_handoff(self) -> None:
        self.assertIn('const AUTH_HANDOFF_TTL_MS = 10_000', self.api)
        self.assertGreaterEqual(self.api.count('rememberAuthenticatedUser('), 3)
        self.assertIn('export function consumeRecentlyAuthenticatedPilotUser()', self.api)
        self.assertIn('recentAuthenticatedUser = null', self.api)
        self.assertIn('pending.expiresAt < Date.now()', self.api)

    def test_guard_reuses_server_confirmed_user_only_before_auth_me_fallback(self) -> None:
        self.assertIn('const recentUser = consumeRecentlyAuthenticatedPilotUser()', self.guard)
        self.assertIn('recentUser ? Promise.resolve(recentUser) : getPilotSession()', self.guard)
        self.assertIn('activateDiscoveryWorkspaceForAccount(user.local_scope)', self.guard)

    def test_refresh_and_cross_tab_isolation_remain_server_authoritative(self) -> None:
        self.assertNotIn('localStorage.setItem(', self.api.split('rememberAuthenticatedUser')[1].split('export function consumeRecentlyAuthenticatedPilotUser')[0])
        self.assertIn('PILOT_SESSION_CHANGE_KEY', self.guard)
        self.assertIn('window.location.reload()', self.guard)
        self.assertIn("fetch(`${apiBaseUrl}/auth/me`", self.api)
        self.assertIn('recentAuthenticatedUser = null\n  if (!isApiMode) return', self.api)


if __name__ == '__main__':
    unittest.main()
