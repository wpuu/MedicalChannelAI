from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.pilot_api import dispatch_pilot_api
from tools.medical_pilot.session_auth import SESSION_COOKIE_NAME
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions_http import TrustedPrincipal
from tools.medical_pilot.today_runtime import build_sqlite_today_runtime


NOW = datetime(2026, 8, 30, 8, 30, tzinfo=timezone.utc)


class ReminderApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = build_sqlite_today_runtime(
            Path(self.tmp.name) / "pilot.sqlite",
            now_provider=lambda: NOW,
        )
        self.profile = complete_profile()
        self.profile["tenant_id"] = "tenant-a"
        self.profile["profile_id"] = "profile-a"
        self.item = opportunity()
        self.runtime.repository.upsert_profile(self.profile)
        self.runtime.repository.upsert_public_opportunity(self.item)
        self.session = self.runtime.issue_authenticated_session(
            principal=TrustedPrincipal("tenant-a", "profile-a"),
            now=NOW,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def headers(self) -> dict[str, str]:
        return {"Cookie": f"{SESSION_COOKIE_NAME}={self.session.token}"}

    def dispatch(self, *, method: str, target: str, body: dict | None = None, auth: bool = True):
        return dispatch_pilot_api(
            self.runtime,
            method=method,
            target=target,
            headers=self.headers() if auth else {},
            body=json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else b"",
            now=NOW,
        )

    def add_due_followup(self) -> None:
        response = self.dispatch(
            method="POST",
            target=f"/api/followup/{self.item['opportunity_id']}",
            body={
                "status": "MONITOR",
                "note": "稍后提醒",
                "remind_at": (NOW - timedelta(minutes=1)).isoformat(),
                "mutation_id": "reminder_api_mutation_0001",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_reminder_inbox_requires_session(self) -> None:
        response = self.dispatch(method="GET", target="/api/reminders", auth=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json_body(), {"error": "UNAUTHORIZED"})

    def test_due_reminder_is_public_safe_and_acknowledge_removes_it(self) -> None:
        self.add_due_followup()
        inbox = self.dispatch(method="GET", target="/api/reminders")
        self.assertEqual(inbox.status_code, 200)
        body = inbox.json_body()
        self.assertEqual(body["mode"], "FOLLOWUP_REMINDER_INBOX")
        self.assertEqual(body["count"], 1)
        reminder = body["reminders"][0]
        self.assertEqual(reminder["facts"]["project_name"], self.item["project_name"])
        encoded = json.dumps(body, ensure_ascii=False)
        self.assertNotIn("tenant-a", encoded)
        self.assertNotIn("profile-a", encoded)
        self.assertNotIn("tenant_id", encoded)
        self.assertNotIn("profile_id", encoded)

        ack = self.dispatch(
            method="POST",
            target=f"/api/reminders/{reminder['reminder_id']}/ack",
            body={},
        )
        self.assertEqual(ack.status_code, 200)
        self.assertTrue(ack.json_body()["acknowledged"])
        self.assertFalse(ack.json_body()["already_acknowledged"])
        self.assertEqual(self.dispatch(method="GET", target="/api/reminders").json_body()["count"], 0)

        repeated = self.dispatch(
            method="POST",
            target=f"/api/reminders/{reminder['reminder_id']}/ack",
            body={},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertTrue(repeated.json_body()["already_acknowledged"])

    def test_future_reminder_is_not_exposed_early(self) -> None:
        response = self.dispatch(
            method="POST",
            target=f"/api/followup/{self.item['opportunity_id']}",
            body={
                "status": "MONITOR",
                "note": "明天提醒",
                "remind_at": (NOW + timedelta(days=1)).isoformat(),
                "mutation_id": "reminder_api_mutation_0002",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.dispatch(method="GET", target="/api/reminders").json_body()["count"], 0)


if __name__ == "__main__":
    unittest.main()
