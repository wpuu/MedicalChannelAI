from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class AuthSessionTouchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.auth = (WEB_ROOT / "api" / "_auth.js").read_text(encoding="utf-8")

    def test_authenticated_lookup_reads_last_seen_without_unconditional_write(self) -> None:
        start = self.auth.index("export async function authenticatedUser")
        end = self.auth.index("\n\nexport function bootstrapInviteHashes", start)
        block = self.auth[start:end]
        self.assertIn("s.last_seen_at", block)
        self.assertIn("const SESSION_TOUCH_INTERVAL_MS = 10 * 60 * 1000", self.auth)
        self.assertIn("const touchDue =", block)
        self.assertIn("if (touchDue) {", block)
        update_index = block.index("UPDATE private_sessions")
        guard_index = block.index("if (touchDue) {")
        self.assertLess(guard_index, update_index)
        self.assertIn("last_seen_at < now() - interval '10 minutes'", block)


if __name__ == "__main__":
    unittest.main()
