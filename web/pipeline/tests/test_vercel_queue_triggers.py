from __future__ import annotations

import json
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
VERCEL_CONFIG = WEB_ROOT / "vercel.json"
EXPECTED_PATH = "api/collector-queue.py"
EXPECTED_TOPIC = "medicalchannelai-refresh-v2"


class VercelQueueTriggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))
        cls.functions = cls.config.get("functions") or {}

    def test_queue_trigger_is_bound_to_v2_topic(self) -> None:
        function = self.functions.get(EXPECTED_PATH)
        self.assertIsInstance(function, dict)
        self.assertEqual(function.get("maxDuration"), 300)
        triggers = function.get("experimentalTriggers")
        self.assertIsInstance(triggers, list)
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].get("type"), "queue/v2beta")
        self.assertEqual(triggers[0].get("topic"), EXPECTED_TOPIC)

    def test_no_duplicate_v2_queue_function_is_configured(self) -> None:
        self.assertNotIn("api/collector-queue-v2.py", self.functions)


if __name__ == "__main__":
    unittest.main()
