from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DB = WEB_ROOT / "api" / "_publicIntelligenceDb.js"
PUBLIC_ENDPOINT = WEB_ROOT / "api" / "public-snapshot.js"
VERIFIED = WEB_ROOT / "api" / "_verifiedSnapshot.js"


class DurableVerifiedSnapshotStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db = PUBLIC_DB.read_text(encoding="utf-8")
        cls.endpoint = PUBLIC_ENDPOINT.read_text(encoding="utf-8")
        cls.verified = VERIFIED.read_text(encoding="utf-8")

    def test_schema_stores_complete_verified_snapshot_payload(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS public_verified_snapshots", self.db)
        self.assertIn("snapshot_as_of TIMESTAMPTZ NOT NULL UNIQUE", self.db)
        self.assertIn("payload JSONB NOT NULL", self.db)
        self.assertIn("public_verified_snapshots_as_of_idx", self.db)

    def test_authenticated_publish_validates_then_persists_before_runtime_cache(self) -> None:
        self.assertIn("persistPublicVerifiedSnapshot", self.endpoint)
        validated = self.endpoint.index("validateVerifiedSnapshot(await requestBodyValue(request))")
        durable = self.endpoint.index("await persistPublicVerifiedSnapshot(snapshot)")
        cache = self.endpoint.index("await publishVerifiedSnapshotToRuntimeCache(snapshot)")
        self.assertLess(validated, durable)
        self.assertLess(durable, cache)

    def test_same_timestamp_conflicting_payload_fails_closed(self) -> None:
        self.assertIn("PUBLIC_SNAPSHOT_REVISION_CONFLICT", self.db)
        self.assertIn("WHERE snapshot_as_of = ${snapshotAsOf}", self.db)
        self.assertIn("existing[0].snapshot_hash !== snapshotHash", self.db)

    def test_database_snapshot_accepts_equal_bundle_revision_as_durable_authority(self) -> None:
        self.assertIn("latestPublicVerifiedSnapshot", self.verified)
        self.assertIn("selectDurableVerifiedSnapshot(durableValue)", self.verified)
        self.assertIn("if (candidateMs < baselineMs) return null", self.verified)
        self.assertIn("if (candidateMs <= baselineMs) return null", self.verified)
        db_mode = self.verified.index("lastSourceMode = 'DATABASE'")
        runtime_load = self.verified.index("const runtimeResult = await loadRuntimeCachedSnapshot()")
        self.assertLess(db_mode, runtime_load)

    def test_runtime_and_durable_snapshot_freshness_rules_stay_distinct(self) -> None:
        runtime_start = self.verified.index("export function selectPublishedRuntimeSnapshot")
        durable_start = self.verified.index("export function selectDurableVerifiedSnapshot")
        publish_start = self.verified.index("export async function publishVerifiedSnapshotToRuntimeCache")
        runtime_body = self.verified[runtime_start:durable_start]
        durable_body = self.verified[durable_start:publish_start]
        self.assertIn("candidateMs <= baselineMs", runtime_body)
        self.assertNotIn("candidateMs < baselineMs", runtime_body)
        self.assertIn("candidateMs < baselineMs", durable_body)
        self.assertNotIn("candidateMs <= baselineMs", durable_body)

    def test_database_unconfigured_remains_backward_compatible(self) -> None:
        self.assertIn("if (!publicIntelligenceDatabaseConfigured()) return null", self.db)
        self.assertIn("configured: false, persisted: false", self.db)


if __name__ == "__main__":
    unittest.main()
