from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.pilot_api import dispatch_pilot_api
from tools.medical_pilot.session_auth import SESSION_COOKIE_NAME
from tools.medical_pilot.test_model_decision_contract import verified_fact
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions_http import TrustedPrincipal
from tools.medical_pilot.today_runtime import build_sqlite_today_runtime


NOW = datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc)


class FollowedApiTests(unittest.TestCase):
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
        fact = verified_fact(
            "fact_11111111-1111-1111-1111-111111111111",
            "project_name",
            self.item["project_name"],
        )
        fact["opportunity_id"] = self.item["opportunity_id"]
        self.runtime.repository.upsert_public_evidence(fact)
        self.session = self.runtime.issue_authenticated_session(
            principal=TrustedPrincipal("tenant-a", "profile-a"),
            now=NOW,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def headers(self) -> dict[str, str]:
        return {"Cookie": f"{SESSION_COOKIE_NAME}={self.session.token}"}

    def dispatch(self, *, auth: bool = True):
        return dispatch_pilot_api(
            self.runtime,
            method="GET",
            target="/api/followed",
            headers=self.headers() if auth else {},
            body=b"",
            now=NOW,
        )

    def add_followup(self, status: str = "CONTACTED") -> None:
        response = dispatch_pilot_api(
            self.runtime,
            method="POST",
            target=f"/api/followup/{self.item['opportunity_id']}",
            headers=self.headers(),
            body=json.dumps(
                {
                    "status": status,
                    "note": "已电话沟通",
                    "mutation_id": f"followed_api_mutation_{status.lower()}_0001",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            now=NOW,
        )
        self.assertEqual(response.status_code, 200)

    def test_requires_session(self) -> None:
        response = self.dispatch(auth=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json_body(), {"error": "UNAUTHORIZED"})

    def test_current_followed_public_view_contains_shared_facts_and_verified_urls(self) -> None:
        self.add_followup()
        response = self.dispatch()
        self.assertEqual(response.status_code, 200)
        body = response.json_body()
        self.assertEqual(body["mode"], "FOLLOWED_OPPORTUNITIES")
        self.assertEqual(body["count"], 1)
        row = body["items"][0]
        self.assertEqual(row["opportunity_id"], self.item["opportunity_id"])
        self.assertEqual(row["followup_status"], "CONTACTED")
        self.assertEqual(row["facts"]["project_name"], self.item["project_name"])
        self.assertEqual(row["facts"]["budget_cny"], 5730000.0)
        self.assertEqual(len(row["evidence_source_urls"]), 1)
        encoded = json.dumps(body, ensure_ascii=False)
        for forbidden in ("tenant-a", "profile-a", "tenant_id", "profile_id", "followup_id"):
            self.assertNotIn(forbidden, encoded)

    def test_archived_is_not_in_default_followed_list(self) -> None:
        self.add_followup("ARCHIVED")
        response = self.dispatch()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json_body()["count"], 0)


if __name__ == "__main__":
    unittest.main()
