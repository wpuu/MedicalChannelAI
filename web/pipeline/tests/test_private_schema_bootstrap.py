from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class PrivateSchemaBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db = (WEB_ROOT / "api" / "_privateDb.js").read_text(encoding="utf-8")

    def test_current_schema_skips_repeated_full_ddl(self) -> None:
        self.assertIn("const PRIVATE_SCHEMA_VERSION =", self.db)
        self.assertIn("async function schemaVersionCurrent(sql)", self.db)
        ensure_start = self.db.index("export async function ensurePrivateSchema")
        ensure_block = self.db[ensure_start:]
        fast_path = ensure_block.index("if (await schemaVersionCurrent(sql)) return")
        migration_loop = ensure_block.index("for (const statement of SCHEMA_STATEMENTS)")
        self.assertLess(fast_path, migration_loop)

    def test_schema_migration_is_serialized_and_versioned(self) -> None:
        self.assertIn("private_schema_meta", self.db)
        self.assertIn("pg_advisory_xact_lock", self.db)
        self.assertIn("PRIVATE_SCHEMA_LOCK_KEY", self.db)
        self.assertIn("ON CONFLICT (schema_key) DO UPDATE SET", self.db)
        self.assertIn("schema_version = EXCLUDED.schema_version", self.db)


if __name__ == "__main__":
    unittest.main()
