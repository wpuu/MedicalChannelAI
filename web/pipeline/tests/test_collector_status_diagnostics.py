from __future__ import annotations

import copy
import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_incremental import (
    candidate_observation,
    empty_ledger,
    ledger_key,
    record_verification_failure,
    record_verification_success,
)


class ReadOnlyMemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return copy.deepcopy(self.values.get(key))

    def set(self, *args, **kwargs):
        raise AssertionError("status must not write")


class CollectorStatusDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.cache = ReadOnlyMemoryCache()
        functions = types.ModuleType("vercel.functions")
        functions.RuntimeCache = lambda: self.cache
        runtime = types.ModuleType("collector_runtime")
        runtime.STAGE_ORDER = ("publish",)
        runtime.load_status = lambda cache: {"stages": {}}
        runtime.snapshot_source_health = lambda cache: {"status": "UNKNOWN", "sources": {}}
        self.stubs = patch.dict(sys.modules, {
            "vercel.functions": functions,
            "collector_runtime": runtime,
        })
        self.stubs.start()
        self.addCleanup(self.stubs.stop)
        spec = importlib.util.spec_from_file_location(
            "collector_status_diagnostics_under_test", WEB_ROOT / "api" / "collector-status.py"
        )
        self.status = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.status)
        self.now = datetime(2026, 11, 6, tzinfo=timezone.utc)

    def observation(self, index, source="tjzyefy"):
        return candidate_observation(source, {
            "detail_url": f"https://official.example/private-candidate-{index}?credential=sensitive",
            "title": f"private-project-{index}",
            "published_at": "2026-11-05",
        })

    def fail(self, ledger, index, error, source="tjzyefy"):
        observation = self.observation(index, source)
        return record_verification_failure(ledger, observation, error, failed_at=self.now)

    def store(self, ledger, source="tjzyefy"):
        self.cache.values[self.status._incremental_ledger_key(source)] = ledger

    def read_source(self, source="tjzyefy"):
        return self.status._incremental_status(self.cache)["sources"][source]

    def test_actual_eight_candidate_shape_exposes_only_safe_failure_references(self):
        ledger = empty_ledger()
        for index in range(6):
            ledger = record_verification_success(ledger, self.observation(index), verified_at=self.now)
        ledger = self.fail(ledger, 6, "TjzyefyParseError:TJZYEFY_REGISTRATION_WINDOW_NOT_FOUND:secret-error-suffix")
        ledger = self.fail(ledger, 7, "URLError:secret-url-and-credential")
        self.store(ledger)
        self.cache.values[self.status._incremental_pending_key("tjzyefy")] = [{} for _ in range(6)]
        self.cache.values[self.status._incremental_pending_barrier_key("tjzyefy")] = ["private-a", "private-b"]

        request = self.status.handler.__new__(self.status.handler)
        request._send_json = Mock()
        request.do_GET()
        code, payload = request._send_json.call_args.args
        self.assertEqual(code, 200)
        result = payload["collector"]["incremental"]["sources"]["tjzyefy"]
        self.assertEqual(result["ledger"]["candidate_count"], 8)
        self.assertEqual(result["ledger"]["verified_count"], 6)
        self.assertEqual(result["ledger"]["failed_count"], 2)
        self.assertEqual(result["staging"], {"record_count": 6, "barrier_count": 2})
        self.assertEqual(result["ledger"]["failed_reason_counts"], {
            "NETWORK_ERROR": 1, "TJZYEFY_REGISTRATION_WINDOW_NOT_FOUND": 1,
        })
        expected = {
            ledger_key(self.observation(6)).split(":")[1]: "TJZYEFY_REGISTRATION_WINDOW_NOT_FOUND",
            ledger_key(self.observation(7)).split(":")[1]: "NETWORK_ERROR",
        }
        self.assertEqual({row["candidate_ref"]: row["reason"]
                          for row in result["ledger"]["failed_candidates"]}, expected)
        serialized = json.dumps(payload)
        for private in ("secret-error-suffix", "secret-url-and-credential", "official.example",
                        "private-project", "private-a", "private-b", "detail_url", "title"):
            self.assertNotIn(private, serialized)

    def test_unknown_uppercase_and_sensitive_suffixes_never_become_codes(self):
        cases = {
            "RuntimeError:API_KEY_SECRET_TOKEN": "DETAIL_VERIFICATION_FAILED",
            "RuntimeError:prefix:TJZYEFY_PRODUCT_ITEMS_NOT_FOUND": "DETAIL_VERIFICATION_FAILED",
            "TjzyefyParseError:TJZYEFY_PRODUCT_ITEMS_NOT_FOUND_SECRET": "DETAIL_PARSE_FAILED",
            "TjzyefyParseError:TJZYEFY_PRODUCT_ITEMS_NOT_FOUND credential=secret": "DETAIL_PARSE_FAILED",
            "TjzyefyParseError:TJZYEFY_PRODUCT_ITEMS_NOT_FOUND:credential=secret": "TJZYEFY_PRODUCT_ITEMS_NOT_FOUND",
            "TJZYEFY_PRODUCT_ITEMS_NOT_FOUND": "TJZYEFY_PRODUCT_ITEMS_NOT_FOUND",
            "ValidationError:credential=secret": "DETAIL_VALIDATION_FAILED",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.status._safe_failure_reason(raw), expected)
        for raw in (None, {}, 123):
            self.assertEqual(self.status._safe_failure_reason(raw), "DETAIL_VERIFICATION_FAILED")

    def test_network_and_http_wrappers_use_fixed_categories(self):
        for raw, expected in (
            ("HTTPError:HTTP Error 403: secret-credential", "HTTP_ERROR"),
            ("RuntimeError:TJZYEFY_HTTP_503:secret-credential", "HTTP_ERROR"),
            ("RuntimeError:TJZXFC_NETWORK_ERROR:secret-credential", "NETWORK_ERROR"),
            ("TimeoutError:secret-credential", "NETWORK_TIMEOUT"),
            ("UnicodeDecodeError:secret-response-body", "RESPONSE_ENCODING_ERROR"),
            ("RuntimeError:OTHER_HTTP_503:secret-credential", "DETAIL_VERIFICATION_FAILED"),
            ("RuntimeError:TJZYEFY_HTTP_503_SECRET", "DETAIL_VERIFICATION_FAILED"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.status._safe_failure_reason(raw), expected)

    def test_bounded_deterministic_samples_do_not_echo_invalid_ledger_keys(self):
        ledger = empty_ledger()
        for index in range(7):
            ledger = self.fail(ledger, index, "TimeoutError:sensitive")
        row = copy.deepcopy(next(iter(ledger["entries"].values())))
        for key in ("tjzyefy:secret-key", "other:" + "a" * 64, "tjzyefy:" + "A" * 64):
            ledger["entries"][key] = copy.deepcopy(row)
        self.store(ledger)
        first = self.read_source()["ledger"]
        self.assertEqual(first["failed_count"], 10)
        self.assertEqual(first["failed_reason_counts"], {"NETWORK_TIMEOUT": 10})
        valid_refs = sorted(ledger_key(self.observation(index)).split(":")[1] for index in range(7))
        self.assertEqual(first["failed_candidates"], [
            {"candidate_ref": value, "reason": "NETWORK_TIMEOUT"} for value in valid_refs[:5]
        ])
        ledger["entries"] = dict(reversed(list(ledger["entries"].items())))
        self.store(ledger)
        self.assertEqual(self.read_source()["ledger"], first)

    def test_nonfailed_and_empty_ledgers_have_no_failure_diagnostics(self):
        ledger = record_verification_success(empty_ledger(), self.observation(1), verified_at=self.now)
        next(iter(ledger["entries"].values()))["last_error"] = "RuntimeError:secret-old-error"
        self.store(ledger)
        result = self.read_source()["ledger"]
        self.assertEqual(result["failed_reason_counts"], {})
        self.assertEqual(result["failed_candidates"], [])
        for source in self.status.INCREMENTAL_SOURCE_IDS:
            result = self.read_source(source)["ledger"]
            self.assertEqual(result["failed_reason_counts"], {})
            self.assertEqual(result["failed_candidates"], [])

    def test_all_exposed_reason_values_are_fixed_uppercase_codes(self):
        reasons = set(self.status._SAFE_DETAIL_REASON_CODES) | set(self.status._FAILURE_CLASS_REASONS.values())
        reasons.add("DETAIL_VERIFICATION_FAILED")
        for reason in reasons:
            self.assertRegex(reason, r"^[A-Z][A-Z0-9_]*$")
        for source, code in (
            ("tjzyefy", "TJZYEFY_REGISTRATION_WINDOW_NOT_FOUND"),
            ("tjzyefy_intent", "TJZYEFY_INTENT_SUPPLIER_CONSULTATION_NOT_FOUND"),
            ("tjzxfc", "TJZXFC_RESEARCH_CONTENT_INVALID"),
        ):
            ledger = self.fail(empty_ledger(), 1, f"ValueError:{code}:secret", source)
            self.store(ledger, source)
            self.assertEqual(self.read_source(source)["ledger"]["failed_reason_counts"], {code: 1})


if __name__ == "__main__":
    unittest.main()
