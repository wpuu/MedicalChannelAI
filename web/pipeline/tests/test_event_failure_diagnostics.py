from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from collector_diagnostics import failure_summary, reported_event_failure_row


class EventFailureDiagnosticsTests(unittest.TestCase):
    def report(self, error="RuntimeError", message="CCGP_RATE_LIMITED:private-secret", **fields):
        return {"stage": "event_search", "project_number": "private-project", "notice_type": "更正公告",
                "error": error, "message": message, **fields}

    def test_fixed_network_http_and_event_parser_reasons(self):
        for error, message, expected in [
            ("RuntimeError", "CCGP_RATE_LIMITED:private-secret", "RATE_LIMITED"),
            ("HTTPError", "HTTP Error 403: private-secret", "HTTP_403"),
            ("RuntimeError", "CCGP_DETAIL_HTTP_503:private-secret", "CCGP_DETAIL_HTTP_503"),
            ("RuntimeError", "CCGP_DETAIL_NETWORK_ERROR:private-secret", "NETWORK_ERROR"),
            ("TimeoutError", "private-secret", "NETWORK_TIMEOUT"),
            ("URLError", "private-secret", "NETWORK_ERROR"),
            ("CcgpEventParseError", "CCGP_EVENT_PROJECT_NUMBER_NOT_FOUND:private-secret", "CCGP_EVENT_PROJECT_NUMBER_NOT_FOUND"),
            ("CcgpEventParseError", "unknown-private-secret", "EVENT_PARSE_FAILED"),
        ]:
            with self.subTest(error=error, message=message):
                row=reported_event_failure_row(self.report(error,message))
                self.assertEqual(row["reason"], expected)
                self.assertNotIn("private",json.dumps(row))

    def test_unknown_codes_and_embedded_wrappers_cannot_echo_into_reason(self):
        for raw in ["CCGP_EVENT_PROJECT_NUMBER_NOT_FOUND_SECRET", "RuntimeError:CCGP_RATE_LIMITED",
                    "CCGP_RATE_LIMITED private-secret", "SECRET_TOKEN", "CCGP_DETAIL_HTTP_503_SECRET"]:
            row=reported_event_failure_row(self.report(message=raw))
            self.assertEqual(row["reason"], "SOURCE_VERIFICATION_FAILED")

    def test_detail_reference_is_only_full_sha256(self):
        url="https://official.example/private-detail?token=secret"
        row=reported_event_failure_row(self.report(stage="event_detail",url=url))
        self.assertEqual(row["candidate_ref"],hashlib.sha256(url.encode()).hexdigest())
        self.assertEqual(set(row),{"phase","reason","candidate_ref"})
        self.assertNotIn("official.example",json.dumps(row))

    def test_counts_are_complete_but_samples_bounded_and_deterministic(self):
        rows=[reported_event_failure_row(self.report(project_number=f"private-{i}")) for i in range(12)]
        summary=failure_summary(rows)
        self.assertEqual(summary["failure_count"],12)
        self.assertEqual(summary["reason_counts"],{"RATE_LIMITED":12})
        self.assertEqual(summary["phase_counts"],{"event_search":12})
        self.assertEqual(len(summary["samples"]),5)
        self.assertEqual(summary,failure_summary(list(reversed(rows))))
        ties=[reported_event_failure_row(self.report()),reported_event_failure_row(self.report("TimeoutError","secret"))]
        self.assertEqual(failure_summary(ties),failure_summary(list(reversed(ties))))

    def test_invalid_report_fields_reduce_to_fixed_unknown_category(self):
        row=reported_event_failure_row({"stage":[],"error":{},"message":None})
        self.assertEqual(row["phase"],"event_scan")
        self.assertEqual(row["reason"],"SOURCE_VERIFICATION_FAILED")
