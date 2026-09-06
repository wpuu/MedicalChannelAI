from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class PrivateProfileQueryPressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (WEB_ROOT / "api" / "_privateProfileContext.js").read_text(encoding="utf-8")

    def test_profile_load_uses_one_bounded_database_roundtrip(self) -> None:
        start = self.source.index("export async function loadPrivateProfileForUser")
        end = self.source.index("export function minimalPrivateContextFromProfile", start)
        block = self.source[start:end]
        self.assertIn("const rows = await sql`", block)
        self.assertNotIn("Promise.all", block)
        self.assertEqual(block.count("await sql`"), 1)
        self.assertIn("LIMIT 50", block)
        self.assertGreaterEqual(block.count("LIMIT 100"), 2)
        self.assertIn("private_user_preferences", block)
        self.assertIn("COALESCE", block)
        self.assertIn("jsonb_agg", block)

    def test_profile_query_keeps_user_and_organization_scope(self) -> None:
        start = self.source.index("export async function loadPrivateProfileForUser")
        end = self.source.index("export function minimalPrivateContextFromProfile", start)
        block = self.source[start:end]
        self.assertGreaterEqual(
            block.count("user_id = ${user.id} AND organization_id = ${user.organization_id}"),
            3,
        )
        self.assertIn("WHERE user_id = ${user.id}", block)


if __name__ == "__main__":
    unittest.main()
