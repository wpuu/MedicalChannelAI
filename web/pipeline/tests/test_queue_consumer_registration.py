from __future__ import annotations

import ast
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
CONSUMER_PATH = WEB_ROOT / "api" / "collector-queue.py"
EXPECTED_CONSUMER_GROUP = "api/collector-queue.py"
EXPECTED_TOPIC = "medicalchannelai-refresh"


class QueueConsumerRegistrationTests(unittest.TestCase):
    def test_private_queue_consumer_group_matches_vercel_function_path(self) -> None:
        source = CONSUMER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        subscribe_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "subscribe"
        ]
        self.assertEqual(len(subscribe_calls), 1)
        keywords = {item.arg: item.value for item in subscribe_calls[0].keywords if item.arg}
        consumer_group = keywords.get("consumer_group")
        self.assertIsInstance(consumer_group, ast.Constant)
        self.assertEqual(consumer_group.value, EXPECTED_CONSUMER_GROUP)

    def test_queue_topic_is_explicit_and_stable(self) -> None:
        source = CONSUMER_PATH.read_text(encoding="utf-8")
        self.assertIn(f'"{EXPECTED_TOPIC}"', source)


if __name__ == "__main__":
    unittest.main()
