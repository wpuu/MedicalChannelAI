from pathlib import Path
from urllib.error import HTTPError, URLError
import unittest

from medical_channel_pipeline.ccgp_discovery import classify_search_failure


class CcgpSearchFaultDiagnosticsTests(unittest.TestCase):
    def test_bounded_error_codes_do_not_include_upstream_text(self):
        cases = [
            (RuntimeError("CCGP_RATE_LIMITED"), "fetch", "SOURCE_RATE_LIMIT"),
            (HTTPError("https://example.invalid/?secret=testraw", 403, "testraw", None, None), "fetch", "HTTP_403"),
            (HTTPError("https://example.invalid", 429, "", None, None), "fetch", "HTTP_429"),
            (URLError(TimeoutError("testraw")), "fetch", "FETCH_TIMEOUT"),
            (URLError("testraw"), "fetch", "FETCH_NETWORK_ERROR"),
            (ValueError("testraw"), "parse", "PARSE_ERROR"),
            (ValueError("testraw"), "fetch", "FETCH_ERROR"),
        ]
        for error, phase, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_search_failure(error, phase=phase), expected)

    def test_status_diagnostic_uses_codes_not_discovery_messages(self):
        path = Path(__file__).resolve().parents[2] / "collector_runtime.py"
        source = path.read_text(encoding="utf-8")
        block = source.split('if reason == "ALL_DISCOVERY_QUERIES_FAILED":', 1)[1].split("raise CollectorStageBlocked", 1)[0]
        self.assertIn('item.get("diagnostic_code")', block)
        self.assertNotIn("message", block)

    def test_daily_discovery_distinguishes_verified_empty_markup_from_error_html(self):
        from medical_channel_pipeline.ccgp_discovery import parse_search_html

        self.assertEqual(
            parse_search_html('<ul class="vT-srch-result-list-bid"></ul>',
                              keyword="医院", require_result_list=True),
            [],
        )
        with self.assertRaisesRegex(ValueError, "CCGP_RESULT_LIST_MISSING"):
            parse_search_html("<html><h1>Upstream temporarily unavailable</h1></html>",
                              keyword="医院", require_result_list=True)

    def test_daily_discovery_stops_after_first_upstream_restriction(self):
        from unittest.mock import patch
        from sync_ccgp_query import discover_candidates

        for error in (RuntimeError("CCGP_RATE_LIMITED"),
                      HTTPError("https://example.invalid/", 429, "", None, None)):
            with self.subTest(error=error), patch(
                "sync_ccgp_query.fetch_search_page", side_effect=error
            ) as fetch:
                failures = []
                self.assertEqual(
                    discover_candidates(keyword="医院", region="天津",
                                        notice_types=["公开招标", "竞争性磋商"],
                                        start_date="2026-11-19", end_date="2026-11-21",
                                        delay_seconds=0, failures=failures, daily_refresh=True),
                    [],
                )
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(fetch.call_args.kwargs["timeout_seconds"], 8)
                self.assertEqual(len(failures), 1)
