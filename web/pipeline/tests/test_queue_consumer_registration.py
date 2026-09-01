from __future__ import annotations

import ast
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
LEGACY_CONSUMER_PATH = WEB_ROOT / "api" / "collector-queue.py"
V2_CONSUMER_PATH = WEB_ROOT / "api" / "collector-queue-v2.py"
NAMESPACE_PATH = WEB_ROOT / "collector_namespace.py"
EXPECTED_LEGACY_CONSUMER_GROUP = "api/collector-queue.py"
EXPECTED_LEGACY_TOPIC = "medicalchannelai-refresh"
EXPECTED_V2_CONSUMER_GROUP = "api/collector-queue-v2.py"
EXPECTED_V2_TOPIC = "medicalchannelai-refresh-v2"


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


def _subscription(path: Path) -> tuple[str | None, str | None]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = _string_constants(tree)
    subscribe_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "subscribe"
    ]
    if len(subscribe_calls) != 1:
        raise AssertionError(f"EXPECTED_ONE_SUBSCRIPTION:{path.name}:{len(subscribe_calls)}")
    keywords = {item.arg: item.value for item in subscribe_calls[0].keywords if item.arg}
    consumer_group = _resolve_string(keywords.get("consumer_group"), constants)
    topic_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Subscript)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "Topic"
    ]
    if len(topic_calls) != 1 or not topic_calls[0].args:
        raise AssertionError(f"EXPECTED_ONE_TOPIC:{path.name}:{len(topic_calls)}")
    topic = _resolve_string(topic_calls[0].args[0], constants)
    return topic, consumer_group


class QueueConsumerRegistrationTests(unittest.TestCase):
    def test_legacy_subscriber_stays_on_v1_topic(self) -> None:
        topic, consumer_group = _subscription(LEGACY_CONSUMER_PATH)
        self.assertEqual(topic, EXPECTED_LEGACY_TOPIC)
        self.assertEqual(consumer_group, EXPECTED_LEGACY_CONSUMER_GROUP)

    def test_v2_subscriber_has_fresh_function_identity(self) -> None:
        topic, consumer_group = _subscription(V2_CONSUMER_PATH)
        self.assertEqual(topic, EXPECTED_V2_TOPIC)
        self.assertEqual(consumer_group, EXPECTED_V2_CONSUMER_GROUP)
        self.assertNotEqual(consumer_group, EXPECTED_LEGACY_CONSUMER_GROUP)

    def test_runtime_sender_topic_matches_v2_subscriber(self) -> None:
        namespace_source = NAMESPACE_PATH.read_text(encoding="utf-8")
        namespace_constants = _string_constants(ast.parse(namespace_source))
        self.assertEqual(namespace_constants.get("QUEUE_TOPIC_NAME"), EXPECTED_V2_TOPIC)
        topic, _ = _subscription(V2_CONSUMER_PATH)
        self.assertEqual(topic, namespace_constants.get("QUEUE_TOPIC_NAME"))


if __name__ == "__main__":
    unittest.main()
