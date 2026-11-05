from __future__ import annotations

import ast
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

    def test_manual_push_delivery_limit_is_explicit_and_matches_subscriber(self) -> None:
        # The manual accept_and_handle route does not compile @subscribe
        # delivery metadata into a trigger. Omitting this field means unlimited
        # failed deliveries, even when the decorator declares max_attempts.
        trigger = self.functions[EXPECTED_PATH]["experimentalTriggers"][0]
        self.assertEqual(trigger.get("maxDeliveries"), 3)
        consumer = ast.parse((WEB_ROOT / EXPECTED_PATH).read_text(encoding="utf-8"))
        decorators = [
            node for node in ast.walk(consumer)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "subscribe"
        ]
        self.assertEqual(len(decorators), 1)
        options = {item.arg: ast.literal_eval(item.value)
                   for item in decorators[0].keywords if item.arg == "max_attempts"}
        self.assertEqual(trigger["maxDeliveries"], options.get("max_attempts"))


if __name__ == "__main__":
    unittest.main()
