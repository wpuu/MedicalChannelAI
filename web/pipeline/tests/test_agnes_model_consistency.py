from __future__ import annotations

import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MODEL = "agnes-3.0-flash"
MODEL_PATTERN = re.compile(r"MODEL_ID\s*=\s*['\"]([^'\"]+)['\"]")


class AgnesModelConsistencyTests(unittest.TestCase):
    def test_benchmark_root_and_continuation_use_the_same_expected_model(self):
        paths = [
            WEB_ROOT / "pipeline" / "scripts" / "run_agnes_discovery_benchmark.py",
            WEB_ROOT / "api" / "ai" / "discover.js",
            WEB_ROOT / "api" / "ai" / "_discoverContinuation.js",
        ]

        models: dict[str, str] = {}
        for path in paths:
            text = path.read_text(encoding="utf-8")
            match = MODEL_PATTERN.search(text)
            self.assertIsNotNone(match, f"MODEL_ID missing from {path.relative_to(WEB_ROOT)}")
            models[str(path.relative_to(WEB_ROOT))] = match.group(1)
            self.assertNotIn("agnes-2.5-flash", text)

        self.assertEqual(set(models.values()), {EXPECTED_MODEL}, models)


if __name__ == "__main__":
    unittest.main()
