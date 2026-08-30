from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from .pilot_api import dispatch_pilot_api
from .test_opportunity_match_gate import complete_profile, opportunity
from .today_actions_http import TrustedPrincipal
from .today_runtime import build_sqlite_today_runtime


NOW = datetime(2026, 8, 30, 13, 15, tzinfo=ZoneInfo("Asia/Shanghai"))


def evidence_for(item: dict) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": "fact_api_adapter",
        "opportunity_id": item["opportunity_id"],
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": item["project_name"],
        "source_url": "https://www.ccgp.gov.cn/example/pilot-api",
    }


class PilotApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = build_sqlite_today_runtime(
            Path(self.tmp.name) / "pilot.sqlite",
            now_provider=lambda: NOW,
        )
        self.profile = complete_profile()
        self.item = opportunity()
        self.runtime.repository.upsert_profile(self.profile)
        self.runtime.repository.upsert_public_opportunity(self.item)
        self.runtime.repository.upsert_public_evidence(evidence_for(self.item))
        self.principal = TrustedPrincipal(
            self.profile["tenant_id"],
            self.profile["profile_id"],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_api_prefix_routes_invite_then_authenticated_today(self) -> None:
        invite = self.runtime.issue_profile_invite(principal=self.principal, now=NOW)
        login = dispatch_pilot_api(
            self.runtime,
            method="POST",
            target="/api/auth/redeem",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"code": invite.code}).encode("utf-8"),
            now=NOW,
        )
        cookie = login.headers["Set-Cookie"].split(";", 1)[0]

        today = dispatch_pilot_api(
            self.runtime,
            method="GET",
            target="/api/today?tenant_id=attacker",
            headers={"Cookie": cookie},
            body=b"",
            now=NOW,
        )

        self.assertEqual(login.status_code, 200)
        self.assertEqual(today.status_code, 200)
        body = today.json_body()
        self.assertEqual(body["card_count"], 1)
        self.assertNotIn("model_requests", body)
        self.assertNotIn("task_payloads", body)

    def test_non_api_path_is_not_served_by_backend_adapter(self) -> None:
        response = dispatch_pilot_api(
            self.runtime,
            method="GET",
            target="/today",
            headers={},
            body=b"",
            now=NOW,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json_body(), {"error": "NOT_FOUND"})

    def test_api_auth_does_not_enable_permissive_cors(self) -> None:
        invite = self.runtime.issue_profile_invite(principal=self.principal, now=NOW)
        response = dispatch_pilot_api(
            self.runtime,
            method="POST",
            target="/api/auth/redeem",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"code": invite.code}).encode("utf-8"),
            now=NOW,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)


if __name__ == "__main__":
    unittest.main()
