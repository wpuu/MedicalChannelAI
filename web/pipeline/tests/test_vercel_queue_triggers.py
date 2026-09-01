from __future__ import annotations

import json
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
VERCEL_CONFIG = WEB_ROOT / "vercel.json"


class VercelQueueTriggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))
        cls.functions = cls.config.get("functions") or {}

    def _queue_trigger(self, path: str) -> dict:
        function = self.functions.get(path)
        self.assertIsInstance(function, dict)
        triggers = function.get("experimentalTriggers")
        self.assertIsInstance(triggers, list)
        self.assertEqual(len(triggers), 1)
        trigger = triggers[0]
        self.assertEqual(trigger.get("type"), "queue/v2beta")
        return trigger

    def test_legacy_v1_trigger_stays_isolated(self) -> None:
        trigger = self._queue_trigger("api/collector-queue.py")
        self.assertEqual(trigger.get("topic"), "medicalchannelai-refresh")

    def test_v2_trigger_targets_fresh_function_identity(self) -> None:
        trigger = self._queue_trigger("api/collector-queue-v2.py")
        self.assertEqual(trigger.get("topic"), "medicalchannelai-refresh-v2")
        self.assertEqual(self.functions["api/collector-queue-v2.py"].get("maxDuration"), 300)

    def test_v1_and_v2_triggers_cannot_share_function_path(self) -> None:
        legacy = self._queue_trigger("api/collector-queue.py")
        v2 = self._queue_trigger("api/collector-queue-v2.py")
        self.assertNotEqual(legacy.get("topic"), v2.get("topic"))


if __name__ == "__main__":
    unittest.main()
