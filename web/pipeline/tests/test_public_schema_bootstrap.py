from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class PublicSchemaBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (WEB_ROOT / "api" / "_publicIntelligenceDb.js").read_text(encoding="utf-8")

    def test_current_public_schema_skips_full_ddl(self) -> None:
        self.assertIn("const PUBLIC_SCHEMA_VERSION =", self.source)
        self.assertIn("async function publicSchemaVersionCurrent(sql)", self.source)
        start = self.source.index("export async function ensurePublicIntelligenceSchema")
        block = self.source[start:]
        fast_path = block.index("if (await publicSchemaVersionCurrent(sql)) return")
        migration_loop = block.index("for (const statement of PUBLIC_SCHEMA_STATEMENTS)")
        self.assertLess(fast_path, migration_loop)

    def test_public_schema_migration_is_serialized_and_versioned(self) -> None:
        self.assertIn("public_schema_meta", self.source)
        self.assertIn("PUBLIC_SCHEMA_LOCK_KEY", self.source)
        self.assertIn("pg_advisory_xact_lock", self.source)
        self.assertIn("ON CONFLICT (schema_key) DO UPDATE SET", self.source)
        self.assertIn("schema_version = EXCLUDED.schema_version", self.source)


if __name__ == "__main__":
    unittest.main()
