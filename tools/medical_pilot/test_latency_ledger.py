from __future__ import annotations

import unittest

from tools.medical_pilot.latency_ledger import LatencyLedgerError, build_latency_ledger


BASE = {
    "source_id": "ccgp_local_notices",
    "opportunity_id": "opp_22222222-2222-2222-2222-222222222222",
    "material_event_id": "event-001",
    "official_published_at": "2026-08-29T09:00:00+08:00",
    "official_published_at_precision": "MINUTE",
    "discovered_at": "2026-08-29T09:02:00+08:00",
}


class LatencyLedgerTests(unittest.TestCase):
    def test_full_notification_path_calculates_operational_latencies(self) -> None:
        result = build_latency_ledger(
            **BASE,
            fetched_at="2026-08-29T09:03:00+08:00",
            verified_at="2026-08-29T09:05:00+08:00",
            matched_at="2026-08-29T09:06:00+08:00",
            notification_queued_at="2026-08-29T09:07:00+08:00",
            delivered_at="2026-08-29T09:07:30+08:00",
        )
        self.assertEqual(result["latency_status"], "FULL_NOTIFICATION_PATH")
        self.assertEqual(result["latencies_seconds"]["publication_to_discovery"], 120)
        self.assertEqual(result["latencies_seconds"]["discovery_to_fetch"], 60)
        self.assertEqual(result["latencies_seconds"]["fetch_to_verified"], 120)
        self.assertEqual(result["latencies_seconds"]["verified_to_match"], 60)
        self.assertEqual(result["latencies_seconds"]["match_to_queue"], 60)
        self.assertEqual(result["latencies_seconds"]["queue_to_delivery"], 30)
        self.assertEqual(result["latencies_seconds"]["discovery_to_delivery"], 330)
        self.assertEqual(result["publication_latency_precision"], "MINUTE")

    def test_day_precision_never_fakes_publication_to_discovery_minutes(self) -> None:
        result = build_latency_ledger(
            **{**BASE, "official_published_at": "2026-08-29T00:00:00+08:00", "official_published_at_precision": "DAY"}
        )
        self.assertIsNone(result["latencies_seconds"]["publication_to_discovery"])
        self.assertEqual(result["publication_latency_precision"], "UNAVAILABLE")
        self.assertIn("OFFICIAL_PUBLICATION_TIME_PRECISION_INSUFFICIENT", result["warnings"])

    def test_unknown_publication_time_is_allowed_but_latency_is_unavailable(self) -> None:
        result = build_latency_ledger(
            **{**BASE, "official_published_at": None, "official_published_at_precision": "UNKNOWN"}
        )
        self.assertIsNone(result["latencies_seconds"]["publication_to_discovery"])
        self.assertEqual(result["latency_status"], "DISCOVERED_ONLY")

    def test_verified_timestamp_requires_fetch_timestamp(self) -> None:
        with self.assertRaises(LatencyLedgerError) as context:
            build_latency_ledger(**BASE, verified_at="2026-08-29T09:05:00+08:00")
        self.assertEqual(context.exception.code, "FETCH_REQUIRED_BEFORE_VERIFY")

    def test_non_monotonic_operational_timestamps_fail_closed(self) -> None:
        with self.assertRaises(LatencyLedgerError) as context:
            build_latency_ledger(
                **BASE,
                fetched_at="2026-08-29T09:01:00+08:00",
            )
        self.assertEqual(context.exception.code, "TIMESTAMP_ORDER_INVALID")

    def test_naive_timestamp_is_rejected(self) -> None:
        with self.assertRaises(LatencyLedgerError) as context:
            build_latency_ledger(**{**BASE, "discovered_at": "2026-08-29T09:02:00"})
        self.assertEqual(context.exception.code, "TIMESTAMP_TIMEZONE_REQUIRED")

    def test_delivery_requires_queue_and_match_chain(self) -> None:
        with self.assertRaises(LatencyLedgerError) as context:
            build_latency_ledger(
                **BASE,
                fetched_at="2026-08-29T09:03:00+08:00",
                verified_at="2026-08-29T09:05:00+08:00",
                delivered_at="2026-08-29T09:07:30+08:00",
            )
        self.assertEqual(context.exception.code, "QUEUE_REQUIRED_BEFORE_DELIVERY")

    def test_source_clock_anomaly_is_recorded_without_negative_latency(self) -> None:
        result = build_latency_ledger(
            **{**BASE, "official_published_at": "2026-08-29T09:10:00+08:00"}
        )
        self.assertIsNone(result["latencies_seconds"]["publication_to_discovery"])
        self.assertIn("DISCOVERY_PRECEDES_REPORTED_PUBLICATION_TIME", result["warnings"])

    def test_timezone_offsets_are_compared_by_real_instant(self) -> None:
        result = build_latency_ledger(
            **{
                **BASE,
                "official_published_at": "2026-08-29T01:00:00Z",
                "discovered_at": "2026-08-29T09:02:00+08:00",
            }
        )
        self.assertEqual(result["latencies_seconds"]["publication_to_discovery"], 120)


if __name__ == "__main__":
    unittest.main()
