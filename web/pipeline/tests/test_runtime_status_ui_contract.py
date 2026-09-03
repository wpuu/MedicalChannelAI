from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
STATUS_API = WEB_ROOT / 'src' / 'services' / 'runtimeStatusApi.ts'
TODAY_PAGE = WEB_ROOT / 'src' / 'pages' / 'TodayPage.tsx'
SERVER_STATUS = WEB_ROOT / 'api' / 'status.js'


class RuntimeStatusUiContractTests(unittest.TestCase):
    def test_frontend_accepts_all_server_snapshot_source_modes(self) -> None:
        client = STATUS_API.read_text(encoding='utf-8')
        server = SERVER_STATUS.read_text(encoding='utf-8')
        for mode in ['BUNDLED', 'RUNTIME_CACHE', 'REMOTE', 'BUNDLED_FALLBACK', 'UNAVAILABLE']:
            self.assertIn(mode, client)
        self.assertIn("lastSourceMode = 'RUNTIME_CACHE'", (WEB_ROOT / 'api' / '_verifiedSnapshot.js').read_text(encoding='utf-8'))
        self.assertIn("lastSourceMode = 'BUNDLED_FALLBACK'", (WEB_ROOT / 'api' / '_verifiedSnapshot.js').read_text(encoding='utf-8'))
        self.assertIn('SNAPSHOT_STALE_AFTER_MINUTES = 30 * 60', server)

    def test_real_pilot_today_surfaces_stale_fallback_and_unavailable_snapshot(self) -> None:
        source = TODAY_PAGE.read_text(encoding='utf-8')
        self.assertIn('if (isApiMode || isVerifiedPublicDemo)', source)
        self.assertIn('getRuntimeStatus()', source)
        self.assertIn("status.snapshot.source_mode === 'BUNDLED_FALLBACK'", source)
        self.assertIn("status.snapshot.freshness === 'STALE'", source)
        self.assertIn("status.snapshot.freshness === 'INVALID'", source)
        self.assertIn("status.snapshot.freshness === 'UNAVAILABLE'", source)
        self.assertIn('官方依据', source)
        self.assertIn('snapshotWarning', source)


if __name__ == '__main__':
    unittest.main()
