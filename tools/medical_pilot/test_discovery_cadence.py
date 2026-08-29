from __future__ import annotations

import unittest
from datetime import datetime, timezone

from tools.medical_pilot.discovery_cadence import plan_discovery_cadence


class DiscoveryCadenceTests(unittest.TestCase):
    def test_weekday_business_intervals_are_source_aware(self) -> None:
        now = datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc)  # 10:00 Asia/Shanghai, Monday
        fast = plan_discovery_cadence("tj_government_procurement", now=now)
        early = plan_discovery_cadence("tjmugh_procurement", now=now)
        slow = plan_discovery_cadence("ccgp_procurement_intent", now=now)
        self.assertEqual(fast.interval_minutes, 10)
        self.assertEqual(early.interval_minutes, 15)
        self.assertEqual(slow.interval_minutes, 30)

    def test_evening_discovery_continues_but_at_lower_frequency(self) -> None:
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)  # 20:00 local
        fast = plan_discovery_cadence("ccgp_local_notices", now=now)
        early = plan_discovery_cadence("tj_first_central_hospital_procurement", now=now)
        self.assertEqual(fast.interval_minutes, 15)
        self.assertEqual(early.interval_minutes, 30)

    def test_weekend_is_reduced_not_disabled(self) -> None:
        now = datetime(2026, 8, 29, 2, 0, tzinfo=timezone.utc)  # 10:00 local, Saturday
        fast = plan_discovery_cadence("tj_government_procurement_center", now=now)
        slow = plan_discovery_cadence("tj_public_resource_exchange", now=now)
        self.assertTrue(fast.weekend)
        self.assertEqual(fast.interval_minutes, 30)
        self.assertEqual(slow.interval_minutes, 120)

    def test_failures_back_off_and_success_policy_can_reset_externally(self) -> None:
        now = datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc)
        decision = plan_discovery_cadence("tj_government_procurement", now=now, consecutive_failures=2)
        self.assertEqual(decision.base_interval_minutes, 10)
        self.assertEqual(decision.interval_minutes, 40)

    def test_unknown_source_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            plan_discovery_cadence("unknown_source", now=datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
