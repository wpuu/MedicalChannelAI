from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class TodayPreferenceSchemaPressureTests(unittest.TestCase):
    def test_ui_preference_table_is_owned_by_private_schema_bootstrap(self) -> None:
        private_db = (WEB_ROOT / "api" / "_privateDb.js").read_text(encoding="utf-8")
        preference = (WEB_ROOT / "api" / "_todayDisplayPreference.js").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS private_user_ui_preferences", private_db)
        self.assertIn("private_user_ui_preferences", preference)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS", preference)
        self.assertNotIn("schemaPromise", preference)


if __name__ == "__main__":
    unittest.main()
