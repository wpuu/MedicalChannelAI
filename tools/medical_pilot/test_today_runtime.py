from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from .account_auth import ACCOUNT_ACTIVE, ACCOUNT_DISABLED
from .session_auth import SESSION_COOKIE_NAME, issue_session
from .test_opportunity_match_gate import complete_profile, opportunity
from .today_actions_http import TrustedPrincipal
from .today_runtime import build_sqlite_today_runtime


NOW = datetime(2026, 8, 30, 12, 50, tzinfo=ZoneInfo("Asia/Shanghai"))


def evidence_for(item: dict) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": "fact_runtime_demo",
        "opportunity_id": item["opportunity_id"],
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": item["project_name"],
        "source_url": "https://www.ccgp.gov.cn/example/runtime",
    }


class TodayRuntimeTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _request_today(self, token: str, *, target: str = "/today"):
        return self.runtime.transport.handle(
            method="GET",
            target=target,
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={token}"},
            now=NOW,
        )

    def test_authenticated_cookie_reaches_public_today_view_and_server_queue(self) -> None:
        principal = TrustedPrincipal(
            self.profile["tenant_id"],
            self.profile["profile_id"],
        )
        issued = self.runtime.issue_authenticated_session(principal=principal, now=NOW)

        response = self._request_today(
            issued.token,
            target="/today?tenant_id=attacker&profile_id=attacker",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json_body()
        self.assertEqual(body["mode"], "TODAY_ACTIONS")
        self.assertEqual(body["card_count"], 1)
        self.assertNotIn("model_requests", body)
        self.assertNotIn("task_payloads", body)
        self.assertNotIn("agnes_dispatch_plan", body)
        pending = self.runtime.dispatch_queue.list_pending(limit=10)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["profile_id"], self.profile["profile_id"])
        self.assertEqual(self.runtime.account_store.get(principal).status, ACCOUNT_ACTIVE)

    def test_one_time_invite_registers_account_and_exchanges_to_working_session(self) -> None:
        principal = TrustedPrincipal(
            self.profile["tenant_id"],
            self.profile["profile_id"],
        )
        invite = self.runtime.issue_profile_invite(principal=principal, now=NOW)

        invited = self.runtime.account_store.get(principal)
        self.assertIsNotNone(invited)
        self.assertEqual(invited.status, "INVITED")

        session = self.runtime.redeem_invite_to_session(code=invite.code, now=NOW)
        replay = self.runtime.redeem_invite_to_session(code=invite.code, now=NOW)

        self.assertIsNotNone(session)
        self.assertIsNone(replay)
        self.assertEqual(self.runtime.account_store.get(principal).status, ACCOUNT_ACTIVE)
        response = self._request_today(session.token)
        self.assertEqual(response.status_code, 200)

    def test_disabling_account_invalidates_existing_runtime_session(self) -> None:
        principal = TrustedPrincipal(self.profile["tenant_id"], self.profile["profile_id"])
        session = self.runtime.issue_authenticated_session(principal=principal, now=NOW)
        self.assertEqual(self._request_today(session.token).status_code, 200)

        self.assertTrue(self.runtime.account_store.set_disabled(principal, disabled=True, now=NOW))
        self.assertEqual(self.runtime.account_store.get(principal).status, ACCOUNT_DISABLED)
        self.assertEqual(self._request_today(session.token).status_code, 401)

    def test_missing_cookie_is_unauthorized(self) -> None:
        response = self.runtime.transport.handle(
            method="GET",
            target="/today",
            headers={},
            now=NOW,
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json_body(), {"error": "UNAUTHORIZED"})

    def test_active_account_for_other_tenant_still_cannot_load_existing_profile_id(self) -> None:
        # Defense in depth: activate a valid account/session identity whose tenant/profile
        # pair is deliberately absent from the customer-profile repository.
        principal = TrustedPrincipal("tenant-other", self.profile["profile_id"])
        self.runtime.account_store.ensure_invited(
            principal=principal,
            company_name="攻击测试账号",
            now=NOW,
        )
        self.runtime.account_store.activate_login(principal, now=NOW)
        issued = issue_session(self.runtime.session_store, principal=principal, now=NOW)

        response = self._request_today(issued.token)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json_body(), {"error": "PROFILE_NOT_FOUND"})

    def test_runtime_refuses_to_issue_invite_for_unknown_profile(self) -> None:
        with self.assertRaises(ValueError):
            self.runtime.issue_profile_invite(
                principal=TrustedPrincipal("tenant-other", "profile-missing"),
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
