from __future__ import annotations

import ast
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = WEB_ROOT / "collector_runtime.py"
NAMESPACE_PATH = WEB_ROOT / "collector_namespace.py"


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = source.splitlines()
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"function not found: {name}")


def _tuple_assignment(source: str, name: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, tuple):
            raise AssertionError(f"{name} must be a tuple")
        return value
    raise AssertionError(f"assignment not found: {name}")


class VercelTedaRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = RUNTIME_PATH.read_text(encoding="utf-8")
        cls.namespace = NAMESPACE_PATH.read_text(encoding="utf-8")

    def test_teda_is_a_first_class_runtime_stage_before_downstream_publish(self) -> None:
        order = _tuple_assignment(self.runtime, "STAGE_ORDER")
        self.assertIn("teda", order)
        self.assertIn("tjfch", order)
        self.assertIn("publish", order)
        self.assertLess(order.index("teda"), order.index("tjfch"))
        self.assertLess(order.index("tjfch"), order.index("publish"))
        dispatch = _function_source(self.runtime, "run_stage")
        self.assertIn('elif stage == "teda":', dispatch)
        self.assertIn("result = _run_teda(cache, state)", dispatch)

    def test_teda_reuses_verified_sync_fetch_and_parser_contract(self) -> None:
        self.assertIn("discover_candidates as discover_teda_candidates", self.runtime)
        self.assertIn("fetch_page_with_retry as fetch_teda_page_with_retry", self.runtime)
        self.assertIn("parse_teda_market_research", self.runtime)
        self.assertIn("TEDA_REQUEST_DELAY_SECONDS = 3.0", self.runtime)
        self.assertIn("TEDA_INDEX_PAGES = 4", self.runtime)
        self.assertIn("TEDA_MAX_CANDIDATES = 20", self.runtime)
        self.assertIn("TEDA_LOOKBACK_DAYS = 90", self.runtime)

    def test_teda_index_failure_keeps_bounded_page_level_diagnostics(self) -> None:
        body = _function_source(self.runtime, "_run_teda")
        self.assertIn('message = str(exc)[:180]', body)
        self.assertIn(
            'f"TEDA_INDEX_DISCOVERY_FAILED:{type(exc).__name__}:{message}"',
            body,
        )
        self.assertIn("discover_teda_candidates", body)

    def test_teda_failure_blocks_before_canonical_cache_write(self) -> None:
        body = _function_source(self.runtime, "_run_teda")
        failure_gate = body.index("if failures:")
        blocked = body.index("TEDA_CANDIDATE_VERIFICATION_INCOMPLETE")
        cache_write = body.index("_cache_set(cache, TEDA_RECORDS_KEY")
        self.assertLess(failure_gate, blocked)
        self.assertLess(blocked, cache_write)
        self.assertIn("TEDA_UNSUPPORTED_DETAIL_CODES", body)

    def test_publish_requires_teda_and_uses_authoritative_cycle_clock(self) -> None:
        body = _function_source(self.runtime, "_run_publish")
        self.assertIn("teda_records = cache.get(TEDA_RECORDS_KEY)", body)
        self.assertIn("teda_records)", body)
        self.assertIn("+ list(teda_records)", body)
        self.assertIn("as_of = _cycle_as_of(state)", body)
        self.assertNotIn("as_of = _now_utc()", body)
        self.assertLess(
            body.index("teda_records = cache.get(TEDA_RECORDS_KEY)"),
            body.index("LATEST_RUNTIME_SNAPSHOT_KEY"),
        )

    def test_teda_cache_is_namespaced_v2(self) -> None:
        self.assertIn('TEDA_RECORDS_KEY = "medicalchannelai:collector-teda-records:v2"', self.namespace)
        self.assertIn('"TEDA_RECORDS_KEY": TEDA_RECORDS_KEY', self.namespace)


if __name__ == "__main__":
    unittest.main()
