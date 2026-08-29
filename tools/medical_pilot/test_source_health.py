from __future__ import annotations

import unittest
from datetime import datetime, timezone

from tools.medical_pilot.source_health import SourceObservation, build_coverage_report


NOW = datetime(2026, 8, 28, 3, 30, tzinfo=timezone.utc)
IMPLEMENTED = (
    "ccgp_local_notices",
    "ccgp_procurement_intent",
    "tjmugh_procurement",
    "tj_first_central_hospital_procurement",
)


def healthy(source_id: str, minutes_ago: int = 5) -> SourceObservation:
    timestamp = datetime(2026, 8, 28, 3, 30 - minutes_ago, tzinfo=timezone.utc)
    iso = timestamp.isoformat().replace("+00:00", "Z")
    return SourceObservation(
        source_id=source_id,
        checked_at=iso,
        success=True,
        full_refresh_complete=True,
        last_success_at=iso,
    )


class SourceHealthTests(unittest.TestCase):
    def test_healthy_implemented_sources_still_report_partial_while_p0_sources_are_partial(self) -> None:
        observations = [healthy(source_id) for source_id in IMPLEMENTED]
        report = build_coverage_report(observations, now=NOW)
        self.assertEqual(report.coverage_status, "PARTIAL")
        self.assertEqual(report.exhaustiveness_claim, "NOT_EXHAUSTIVE")
        for source_id in (
            "tj_public_resource_exchange",
            "tj_government_procurement",
            "tj_government_procurement_center",
        ):
            with self.subTest(source_id=source_id):
                self.assertIn(source_id, report.missing_implementation_source_ids)
        self.assertNotIn("tj_first_central_hospital_procurement", report.missing_implementation_source_ids)

    def test_failed_required_source_degrades_coverage(self) -> None:
        failed = SourceObservation(
            source_id="ccgp_local_notices",
            checked_at="2026-08-28T03:25:00Z",
            success=False,
            full_refresh_complete=False,
            last_success_at="2026-08-28T02:00:00Z",
            error_code="HTTP_503",
        )
        report = build_coverage_report(
            [failed] + [healthy(source_id) for source_id in IMPLEMENTED if source_id != "ccgp_local_notices"],
            now=NOW,
        )
        self.assertEqual(report.coverage_status, "DEGRADED")
        self.assertIn("ccgp_local_notices", report.failed_source_ids)

    def test_missing_observation_is_reported_not_silently_healthy(self) -> None:
        report = build_coverage_report([healthy("ccgp_local_notices")], now=NOW)
        self.assertEqual(report.coverage_status, "PARTIAL")
        self.assertIn("ccgp_procurement_intent", report.unknown_source_ids)
        self.assertIn("tjmugh_procurement", report.unknown_source_ids)
        self.assertIn("tj_first_central_hospital_procurement", report.unknown_source_ids)

    def test_stale_success_is_degraded(self) -> None:
        stale = SourceObservation(
            source_id="ccgp_local_notices",
            checked_at="2026-08-28T02:00:00Z",
            success=True,
            full_refresh_complete=True,
            last_success_at="2026-08-28T02:00:00Z",
        )
        report = build_coverage_report(
            [stale] + [healthy(source_id) for source_id in IMPLEMENTED if source_id != "ccgp_local_notices"],
            now=NOW,
        )
        self.assertEqual(report.coverage_status, "DEGRADED")
        self.assertIn("ccgp_local_notices", report.failed_source_ids)


if __name__ == "__main__":
    unittest.main()
