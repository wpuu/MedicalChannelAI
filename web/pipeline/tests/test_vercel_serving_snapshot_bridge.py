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

    def test_collector_publish_writes_serving_key_without_ttl(self) -> None:
        body = self.python[self.python.index("def _run_publish"):]
        self.assertIn("cache.set(PUBLISHED_RUNTIME_SNAPSHOT_KEY, snapshot, {})", body)
        self.assertNotIn("_cache_set(\n        cache,\n        PUBLISHED_RUNTIME_SNAPSHOT_KEY", body)
        self.assertIn("SERVING_SNAPSHOT_READBACK_MISMATCH", body)

    def test_legacy_collector_key_remains_separate_from_serving_key(self) -> None:
        legacy = _string_constant(self.python, "LATEST_RUNTIME_SNAPSHOT_KEY")
        serving = _string_constant(self.python, "PUBLISHED_RUNTIME_SNAPSHOT_KEY")
        self.assertNotEqual(legacy, serving)


if __name__ == "__main__":
    unittest.main()
