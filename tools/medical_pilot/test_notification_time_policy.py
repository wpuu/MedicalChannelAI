from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from tools.medical_pilot.notification_time_policy import plan_notification_time


IMMEDIATE = {"should_notify": True, "routing_status": "SEND_IMMEDIATE"}
DIGEST = {"should_notify": True, "routing_status": "INCLUDE_DAILY_DIGEST"}
SUPPRESSED = {"should_notify": False, "routing_status": "NO_NOTIFY"}


class NotificationTimePolicyTests(unittest.TestCase):
    def test_early_digest_goes_to_same_day_morning(self) -> None:
        now = datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc)  # Mon 07:00 local
        result = plan_notification_time(DIGEST, now=now)
        self.assertEqual(result.delivery_window, "MORNING_DIGEST")
        self.assertTrue((result.scheduled_for or "").startswith("2026-08-31T08:10:00+08:00"))

    def test_morning_nonurgent_digest_gets_same_day_midday_delta(self) -> None:
        now = datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc)  # 10:00 local
        result = plan_notification_time(DIGEST, now=now)
        self.assertEqual(result.delivery_window, "MIDDAY_DELTA")
        self.assertTrue((result.scheduled_for or "").startswith("2026-08-31T13:15:00+08:00"))

    def test_afternoon_digest_waits_for_next_business_morning(self) -> None:
        now = datetime(2026, 8, 31, 7, 0, tzinfo=timezone.utc)  # 15:00 local
        result = plan_notification_time(DIGEST, now=now)
        self.assertEqual(result.delivery_window, "NEXT_BUSINESS_MORNING")
        self.assertTrue((result.scheduled_for or "").startswith("2026-09-01T08:10:00+08:00"))

    def test_high_priority_during_workday_sends_now(self) -> None:
        now = datetime(2026, 8, 31, 6, 0, tzinfo=timezone.utc)  # 14:00 local
        result = plan_notification_time(IMMEDIATE, now=now, event_type="NEW_VERIFIED_OPPORTUNITY")
        self.assertEqual(result.timing_status, "SEND_NOW")
        self.assertEqual(result.delivery_window, "WORKDAY_IMMEDIATE")

    def test_high_priority_before_workday_waits_until_0830_not_tomorrow(self) -> None:
        now = datetime(2026, 8, 31, 0, 15, tzinfo=timezone.utc)  # 08:15 local
        result = plan_notification_time(IMMEDIATE, now=now, event_type="NEW_VERIFIED_OPPORTUNITY")
        self.assertEqual(result.delivery_window, "WORKDAY_OPEN")
        self.assertTrue((result.scheduled_for or "").startswith("2026-08-31T08:30:00+08:00"))

    def test_evening_award_is_queued_for_next_morning(self) -> None:
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)  # 20:00 local
        result = plan_notification_time(IMMEDIATE, now=now, event_type="AWARD_PUBLISHED")
        self.assertFalse(result.urgent_exception)
        self.assertEqual(result.delivery_window, "NEXT_BUSINESS_MORNING")

    def test_evening_deadline_change_is_allowed_as_urgent_exception(self) -> None:
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        deadline = now + timedelta(hours=10)
        result = plan_notification_time(IMMEDIATE, now=now, event_type="DEADLINE_CHANGED", action_deadline=deadline)
        self.assertTrue(result.urgent_exception)
        self.assertEqual(result.delivery_window, "EVENING_URGENT_EXCEPTION")
        self.assertEqual(result.timing_status, "SEND_NOW")

    def test_evening_termination_state_change_is_urgent_but_awarded_state_is_not(self) -> None:
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        terminated = plan_notification_time(
            IMMEDIATE,
            now=now,
            event_type="LIFECYCLE_STATE_CHANGED",
            change_fields={"lifecycle_state": "TERMINATED"},
        )
        awarded = plan_notification_time(
            IMMEDIATE,
            now=now,
            event_type="LIFECYCLE_STATE_CHANGED",
            change_fields={"lifecycle_state": "AWARDED"},
        )
        self.assertEqual(terminated.delivery_window, "EVENING_URGENT_EXCEPTION")
        self.assertEqual(awarded.delivery_window, "NEXT_BUSINESS_MORNING")

    def test_weekend_normal_high_priority_waits_until_monday_but_urgent_can_interrupt_daytime(self) -> None:
        now = datetime(2026, 8, 29, 2, 0, tzinfo=timezone.utc)  # Sat 10:00 local
        normal = plan_notification_time(IMMEDIATE, now=now, event_type="NEW_VERIFIED_OPPORTUNITY")
        urgent = plan_notification_time(IMMEDIATE, now=now, event_type="DEADLINE_CHANGED")
        self.assertEqual(normal.delivery_window, "NEXT_BUSINESS_MORNING")
        self.assertTrue((normal.scheduled_for or "").startswith("2026-08-31T08:10:00+08:00"))
        self.assertEqual(urgent.delivery_window, "WEEKEND_URGENT_EXCEPTION")

    def test_china_holiday_override_skips_nominal_weekday(self) -> None:
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)  # Mon 20:00 local
        result = plan_notification_time(
            IMMEDIATE,
            now=now,
            event_type="AWARD_PUBLISHED",
            holiday_dates={"2026-09-01"},
        )
        self.assertTrue((result.scheduled_for or "").startswith("2026-09-02T08:10:00+08:00"))

    def test_routing_suppression_remains_no_notify(self) -> None:
        result = plan_notification_time(SUPPRESSED, now=datetime(2026, 8, 31, 6, 0, tzinfo=timezone.utc))
        self.assertEqual(result.timing_status, "NO_NOTIFY")
        self.assertIsNone(result.scheduled_for)


if __name__ == "__main__":
    unittest.main()
