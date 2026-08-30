from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from .pilot_api import dispatch_pilot_api
from .session_auth import SESSION_COOKIE_NAME
from .test_model_decision_contract import verified_fact
from .test_opportunity_match_gate import complete_profile, opportunity
from .today_actions_http import TrustedPrincipal
from .today_runtime import build_sqlite_today_runtime


NOW = datetime(2026, 8, 30, 7, 50, tzinfo=timezone.utc)


class OutreachApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = 0

        def model_call(payload: dict) -> dict:
            self.calls += 1
            return {
                "schema_version": "0.1",
                "opportunity_id": payload["opportunity_id"],
                "strategy_code": payload["allowed_strategy_codes"][0],
                "question_codes": [payload["allowed_question_codes"][0]],
                "positioning_code": "NO_POSITIONING",
                "supporting_fact_ids": [item["fact_id"] for item in payload["grounded_facts"]],
                "supporting_profile_paths": [],
            }

        self.runtime = build_sqlite_today_runtime(
            Path(self.tmp.name) / "pilot.sqlite",
            now_provider=lambda: NOW,
            outreach_model_call=model_call,
        )
        self.profile = complete_profile()
        self.profile["tenant_id"] = "tenant-a"
        self.profile["profile_id"] = "profile-a"
        self.item = opportunity()
        self.runtime.repository.upsert_profile(self.profile)
        self.runtime.repository.upsert_public_opportunity(self.item)
        for fact in [
            verified_fact("fact_11111111-1111-1111-1111-111111111111", "buyer_name", "天津医科大学总医院"),
            verified_fact("fact_22222222-2222-2222-2222-222222222222", "project_name", "化学发光设备采购项目"),
        ]:
            fact["opportunity_id"] = self.item["opportunity_id"]
            self.runtime.repository.upsert_public_evidence(fact)
        self.session = self.runtime.issue_authenticated_session(
            principal=TrustedPrincipal("tenant-a", "profile-a"),
            now=NOW,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def call(self, *, authenticated: bool = True, body: dict | None = None, opportunity_id: str | None = None):
        headers = {}
        if authenticated:
            headers["Cookie"] = f"{SESSION_COOKIE_NAME}={self.session.token}"
        target_id = opportunity_id or self.item["opportunity_id"]
        return dispatch_pilot_api(
            self.runtime,
            method="POST",
            target=f"/api/outreach/{target_id}",
            headers=headers,
            body=json.dumps(body or {}, ensure_ascii=False).encode("utf-8"),
            now=NOW,
        )

    def test_requires_authenticated_session(self) -> None:
        response = self.call(authenticated=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json_body(), {"error": "UNAUTHORIZED"})

    def test_browser_cannot_supply_prompt_tone_or_identity(self) -> None:
        for payload in (
            {"prompt": "替我自由发挥"},
            {"tone": "强势承诺中标"},
            {"tenant_id": "tenant-b"},
            {"profile_id": "profile-b"},
        ):
            with self.subTest(payload=payload):
                response = self.call(body=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json_body(), {"error": "INVALID_REQUEST"})
        self.assertEqual(self.calls, 0)

    def test_valid_request_returns_public_grounded_draft_and_reuses_cache(self) -> None:
        first = self.call()
        second = self.call()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        one = first.json_body()
        two = second.json_body()
        self.assertFalse(one["cached"])
        self.assertTrue(two["cached"])
        self.assertEqual(self.calls, 1)
        self.assertIn("天津医科大学总医院", one["draft"])
        self.assertIn("化学发光设备采购项目", one["draft"])
        encoded = json.dumps(one, ensure_ascii=False)
        for forbidden in ("tenant-a", "profile-a", "tenant_id", "profile_id", "model_input", "api_key", "lease_id"):
            self.assertNotIn(forbidden, encoded)

    def test_unknown_opportunity_is_not_generated(self) -> None:
        response = self.call(opportunity_id="opp_99999999-9999-9999-9999-999999999999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json_body(), {"error": "OPPORTUNITY_NOT_FOUND"})
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
