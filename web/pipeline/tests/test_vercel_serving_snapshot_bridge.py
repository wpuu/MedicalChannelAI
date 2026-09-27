from __future__ import annotations

import re
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
PYTHON_RUNTIME = WEB_ROOT / "collector_runtime.py"
NODE_SNAPSHOT = WEB_ROOT / "api" / "_verifiedSnapshot.js"


def _string_constant(source: str, name: str) -> str:
    match = re.search(rf'^(?:const\s+)?{name}\s*=\s*["\']([^"\']+)["\']', source, flags=re.M)
    if not match:
        raise AssertionError(f"constant not found: {name}")
    return match.group(1)


class VercelServingSnapshotBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.python = PYTHON_RUNTIME.read_text(encoding="utf-8")
        cls.node = NODE_SNAPSHOT.read_text(encoding="utf-8")

    def test_collector_and_public_api_share_published_snapshot_key(self) -> None:
        python_key = _string_constant(self.python, "PUBLISHED_RUNTIME_SNAPSHOT_KEY")
        node_key = _string_constant(self.node, "PUBLISHED_RUNTIME_SNAPSHOT_KEY")
        self.assertEqual(python_key, node_key)
        self.assertEqual(python_key, "medicalchannelai:verified-snapshot:published:v2")

    def test_collector_never_writes_the_serving_key_directly(self) -> None:
        # The Node durable publish endpoint owns the serving key: it persists the
        # revision to Postgres and applies the monotonic (rollback-protected)
        # Runtime Cache publish. A direct Python cache.set would bypass that.
        body = self.python[self.python.index("def _run_publish"):]
        self.assertNotIn("cache.set(PUBLISHED_RUNTIME_SNAPSHOT_KEY", body)
        self.assertNotIn("SERVING_SNAPSHOT_READBACK_MISMATCH", body)
        self.assertIn("_persist_verified_snapshot_durably(snapshot)", body)
        self.assertIn('"durable_snapshot_persisted": True', body)
        publish_endpoint = (WEB_ROOT / "api" / "public-snapshot.js").read_text(encoding="utf-8")
        self.assertLess(
            publish_endpoint.index("await persistPublicVerifiedSnapshot(snapshot)"),
            publish_endpoint.index("await publishVerifiedSnapshotToRuntimeCache(snapshot)"),
        )

    def test_collector_publish_target_is_derived_from_the_deployment_environment(self) -> None:
        self.assertNotIn('DURABLE_PUBLISH_URL = "https://', self.python)
        self.assertIn('PRODUCTION_PUBLISH_HOST = "medicalchannelai.vercel.app"', self.python)
        self.assertIn('DURABLE_PUBLISH_PATH = "/api/public-snapshot"', self.python)
        self.assertIn('os.environ.get("VERIFIED_SNAPSHOT_PUBLISH_TOKEN")', self.python)
        base = self.python[self.python.index("def _publish_base_url"):self.python.index("def _durable_publish_url")]
        self.assertIn('os.environ.get("VERCEL_ENV")', base)
        self.assertIn('os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")', base)
        self.assertIn('os.environ.get("VERCEL_URL")', base)
        self.assertIn('x-vercel-protection-bypass', base)
        self.assertIn('COLLECTOR_ALLOW_NON_PRODUCTION_PUBLISH', base)
        self.assertIn('raise CollectorStageBlocked("DURABLE_SNAPSHOT_PUBLISH_TARGET_UNRESOLVED")', base)

    def test_collector_publish_runs_the_regression_gate_before_the_durable_publish(self) -> None:
        body = self.python[self.python.index("def _run_publish"):]
        gate = body.index("_publish_regression_gate(snapshot)")
        durable = body.index("_persist_verified_snapshot_durably(snapshot)")
        self.assertLess(gate, durable)
        self.assertIn("PUBLISH_REGRESSION_POOL_SHRUNK", self.python)
        self.assertIn("COLLECTOR_PUBLISH_MIN_POOL_RATIO", self.python)
        self.assertIn("PUBLISH_MIN_POOL_RATIO_DEFAULT = 0.7", self.python)

    def test_legacy_collector_key_remains_separate_from_serving_key(self) -> None:
        legacy = _string_constant(self.python, "LATEST_RUNTIME_SNAPSHOT_KEY")
        serving = _string_constant(self.python, "PUBLISHED_RUNTIME_SNAPSHOT_KEY")
        self.assertNotEqual(legacy, serving)


if __name__ == "__main__":
    unittest.main()
