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


class VercelTjfchRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = RUNTIME_PATH.read_text(encoding="utf-8")
        cls.namespace = NAMESPACE_PATH.read_text(encoding="utf-8")

    def test_tjfch_is_a_first_class_runtime_stage_between_teda_and_publish(self) -> None:
        order = _tuple_assignment(self.runtime, "STAGE_ORDER")
        self.assertIn("tjfch", order)
        self.assertLess(order.index("teda"), order.index("tjfch"))
        self.assertLess(order.index("tjfch"), order.index("regional_bj"))
        self.assertLess(order.index("regional_hl"), order.index("publish"))
        dispatch = _function_source(self.runtime, "run_stage")
        self.assertIn('elif stage == "tjfch":', dispatch)
        self.assertIn("result = _run_tjfch(cache, state)", dispatch)

    def test_tjfch_reuses_verified_procurement_and_early_signal_parsers(self) -> None:
        self.assertIn("INDEX_URL as TJFCH_INDEX_URL", self.runtime)
        self.assertIn("fetch_tjfch_page", self.runtime)
        self.assertIn("parse_tjfch_index_html", self.runtime)
        self.assertIn("select_candidates_since as select_tjfch_candidates", self.runtime)
        self.assertIn("parse_tjfch_procurement_notice", self.runtime)
        self.assertIn("INDEX_URL as TJFCH_TEST_INDEX_URL", self.runtime)
        self.assertIn("parse_tjfch_test_index_html", self.runtime)
        self.assertIn("parse_tjfch_test_recruitment", self.runtime)
        self.assertIn("TJFCH_REQUEST_DELAY_SECONDS = 3.0", self.runtime)
        self.assertIn("TJFCH_MAX_CANDIDATES = 20", self.runtime)
        self.assertIn("TJFCH_TEST_MAX_CANDIDATES = 30", self.runtime)
        self.assertIn("TJFCH_TEST_LOOKBACK_DAYS = 14", self.runtime)
        self.assertIn("TJFCH_LOOKBACK_DAYS = 45", self.runtime)

    def test_tjfch_true_failure_from_either_feed_blocks_before_cache_write(self) -> None:
        body = _function_source(self.runtime, "_run_tjfch")
        failure_gate = body.index("if failures:")
        blocked = body.index("TJFCH_CANDIDATE_VERIFICATION_INCOMPLETE")
        cache_write = body.index("_cache_set(cache, TJFCH_RECORDS_KEY")
        self.assertLess(failure_gate, blocked)
        self.assertLess(blocked, cache_write)
        self.assertIn('"TJFCH_BID_DEADLINE_NOT_EXACT"', body)
        self.assertIn('"TJFCH_NOTICE_TYPE_UNSUPPORTED"', body)
        self.assertIn('str(exc) == "TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED"', body)
        self.assertIn("early_discovered", body)
        self.assertIn("early_new_verified_record_count", body)
        self.assertIn("unsupported.append", body)

    def test_tjfch_has_no_special_case_retry_bypass_in_stage_preparation(self) -> None:
        body = _function_source(self.runtime, "_prepare_stage")
        # Retry accounting is generic: a stage gets MAX_STAGE_ATTEMPTS_PER_DAY
        # per cycle, recovery cycles reset the counter, and there is no
        # error-message-specific bypass for any single source.
        self.assertNotIn('stage == "tjfch"', body)
        self.assertNotIn("TJFCH_NOTICE_TYPE_UNSUPPORTED", body)
        self.assertNotIn("tjfch_policy_recovery_retry", body)
        self.assertIn("if attempts >= MAX_STAGE_ATTEMPTS_PER_DAY:", body)

    def test_tjfch_detail_loops_use_bounded_request_timeouts_and_the_stage_budget(self) -> None:
        body = _function_source(self.runtime, "_run_tjfch")
        self.assertIn("fetch_tjfch_page(TJFCH_INDEX_URL, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)", body)
        self.assertIn("fetch_tjfch_page(candidate.detail_url, timeout_seconds=SOURCE_REQUEST_TIMEOUT_SECONDS)", body)
        self.assertIn("deferred_candidate_count = len(selected) - position", body)
        self.assertIn("early_deferred_candidate_count = len(early_discovered) - position", body)
        self.assertNotIn("time.sleep(", body)

    def test_publish_requires_tjfch_and_uses_authoritative_cycle_clock(self) -> None:
        body = _function_source(self.runtime, "_run_publish")
        self.assertIn("tjfch_records = cache.get(TJFCH_RECORDS_KEY)", body)
        self.assertIn("tjfch_records)", body)
        self.assertIn("+ list(tjfch_records)", body)
        self.assertIn("as_of = _cycle_as_of(state)", body)
        self.assertNotIn("as_of = _now_utc()", body)
        self.assertLess(
            body.index("tjfch_records = cache.get(TJFCH_RECORDS_KEY)"),
            body.index("LATEST_RUNTIME_SNAPSHOT_KEY"),
        )

    def test_tjfch_cache_is_namespaced_v2(self) -> None:
        self.assertIn('TJFCH_RECORDS_KEY = "medicalchannelai:collector-tjfch-records:v2"', self.namespace)
        self.assertIn('"TJFCH_RECORDS_KEY": TJFCH_RECORDS_KEY', self.namespace)


if __name__ == "__main__":
    unittest.main()
