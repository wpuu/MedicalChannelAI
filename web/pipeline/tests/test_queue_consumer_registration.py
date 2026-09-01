from __future__ import annotations

import ast
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
CONSUMER_PATH = WEB_ROOT / "api" / "collector-queue.py"
EXPECTED_CONSUMER_GROUP = "api/collector-queue.py"
EXPECTED_TOPIC = "medicalchannelai-refresh"


def _string_constants(tree: ast.AST) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                values[target.id] = value.value
    return values


def _resolve_string(node: ast.AST | None, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


class QueueConsumerRegistrationTests(unittest.TestCase):
    def test_private_queue_consumer_group_matches_vercel_function_path(self) -> None:
        source = CONSUMER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        constants = _string_constants(tree)
        subscribe_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "subscribe"
        ]
        self.assertEqual(len(subscribe_calls), 1)
        keywords = {item.arg: item.value for item in subscribe_calls[0].keywords if item.arg}
        self.assertEqual(
            _resolve_string(keywords.get("consumer_group"), constants),
            EXPECTED_CONSUMER_GROUP,
        )

    def test_queue_topic_is_explicit_and_stable(self) -> None:
        source = CONSUMER_PATH.read_text(encoding="utf-8")
        self.assertIn(f'"{EXPECTED_TOPIC}"', source)


if __name__ == "__main__":
    unittest.main()
