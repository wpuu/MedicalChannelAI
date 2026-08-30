from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.followup_store import SQLiteFollowupStore
from tools.medical_pilot.reminder_store import SQLiteReminderInboxStore
from tools.medical_pilot.today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 30, 8, 20, tzinfo=timezone.utc)
OPP = "opp_11111111-1111-1111-1111-111111111111"


class ReminderStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pilot.sqlite"
        self.followups = SQLiteFollowupStore(self.path)
        self.reminders = SQLiteReminderInboxStore(self.path)
        self.a = TrustedPrincipal("tenant-a", "profile-a")
        self.b = TrustedPrincipal("tenant-b", "profile-b")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def append(self, principal, *, mutation: str, remind_at: datetime | None, status: str = "MONITOR"):
        return self.followups.append(
            principal=principal,
            opportunity_id=OPP,
            request={
                "status": status,
                "note": "稍后提醒",
                "remind_at": remind_at.isoformat() if remind_at else None,
                "mutation_id": mutation,
            },
            now=NOW,
        )

    def test_only_current_due_followup_becomes_inbox_reminder(self) -> None:
        first = self.append(
            self.a,
            mutation="reminder_store_mutation_0001",
            remind_at=NOW - timedelta(minutes=5),
        )
        due = self.reminders.list_due(principal=self.a, now=NOW)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].followup_id, first.event["followup_id"])

        self.append(
            self.a,
            mutation="reminder_store_mutation_0002",
            remind_at=NOW + timedelta(days=1),
        )
        self.assertEqual(self.reminders.list_due(principal=self.a, now=NOW), [])

    def test_acknowledgement_is_idempotent_and_private(self) -> None:
        self.append(
            self.a,
            mutation="reminder_store_mutation_0003",
            remind_at=NOW - timedelta(minutes=1),
        )
        self.append(
            self.b,
            mutation="reminder_store_mutation_0003",
            remind_at=NOW - timedelta(minutes=1),
        )
        due_a = self.reminders.list_due(principal=self.a, now=NOW)
        due_b = self.reminders.list_due(principal=self.b, now=NOW)
        self.assertEqual(len(due_a), 1)
        self.assertEqual(len(due_b), 1)
        self.assertNotEqual(due_a[0].reminder_id, due_b[0].reminder_id)

        first = self.reminders.acknowledge(
            principal=self.a,
            reminder_id=due_a[0].reminder_id,
            now=NOW,
        )
        second = self.reminders.acknowledge(
            principal=self.a,
            reminder_id=due_a[0].reminder_id,
            now=NOW,
        )
        self.assertTrue(first["inserted"])
        self.assertFalse(second["inserted"])
        self.assertEqual(self.reminders.list_due(principal=self.a, now=NOW), [])
        self.assertEqual(len(self.reminders.list_due(principal=self.b, now=NOW)), 1)


if __name__ == "__main__":
    unittest.main()
