from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from .pilot_api import dispatch_pilot_api
from .session_auth import SESSION_COOKIE_NAME
from .test_opportunity_match_gate import complete_profile, opportunity
from .today_actions_http import TrustedPrincipal
from .today_runtime import build_sqlite_today_runtime


NOW = datetime(2026, 8, 30, 5, 45, tzinfo=timezone.utc)


class FollowupApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = build_sqlite_today_runtime(
            Path(self.tmp.name) / "pilot.sqlite",
            now_provider=lambda: NOW,
        )
        self.profile_a = complete_profile()
        self.profile_a["tenant_id"] = "tenant-a"
        self.profile_a["profile_id"] = "profile-a"
        self.profile_b = copy.deepcopy(self.profile_a)
        self.profile_b["tenant_id"] = "tenant-b"
        self.profile_b["profile_id"] = "profile-b"
        self.item = opportunity()
        self.runtime.repository.upsert_profile(self.profile_a)
        self.runtime.repository.upsert_profile(self.profile_b)
        self.runtime.repository.upsert_public_opportunity(self.item)
        self.session_a = self.runtime.issue_authenticated_session(
            principal=TrustedPrincipal("tenant-a", "profile-a"),
            now=NOW,
        )
        self.session_b = self.runtime.issue_authenticated_session(
            principal=TrustedPrincipal("tenant-b", "profile-b"),
            now=NOW,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def headers(self, token: str) -> dict[str, str]:
        return {"Cookie": f"{SESSION_COOKIE_NAME}={token}"}

    def call(
        self,
        *,
        token: str | None,
        method: str = "GET",
        opportunity_id: str | None = None,
        payload: dict | None = None,
    ):
        target_id = opportunity_id or self.item["opportunity_id"]
        return dispatch_pilot_api(
            self.runtime,
            method=method,
            target=f"/api/followup/{target_id}",
            headers=self.headers(token) if token else {},
            body=json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method == "POST" else b"",
            now=NOW,
        )

    def test_followup_requires_authenticated_session(self) -> None:
        response = self.call(token=None)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json_body(), {"error": "UNAUTHORIZED"})

    def test_authenticated_default_state_contains_no_tenant_or_profile(self) -> None:
        response = self.call(token=self.session_a.token)
        self.assertEqual(response.status_code, 200)
        body = response.json_body()
        self.assertEqual(body["current_status"], "NEW")
        self.assertEqual(body["opportunity_id"], self.item["opportunity_id"])
        encoded = json.dumps(body, ensure_ascii=False)
        self.assertNotIn("tenant-a", encoded)
        self.assertNotIn("profile-a", encoded)
        self.assertNotIn("tenant_id", body)
        self.assertNotIn("profile_id", body)

    def test_post_writes_private_state_and_same_mutation_is_idempotent(self) -> None:
        payload = {
            "status": "CONTACTED",
            "note": "已电话联系",
            "mutation_id": "followup_api_mutation_0001",
        }
        first = self.call(token=self.session_a.token, method="POST", payload=payload)
        second = self.call(token=self.session_a.token, method="POST", payload=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json_body()["mutation_inserted"])
        self.assertFalse(second.json_body()["mutation_inserted"])
        self.assertEqual(second.json_body()["current_status"], "CONTACTED")
        self.assertEqual(len(second.json_body()["history"]), 1)

    def test_same_public_opportunity_has_isolated_followup_per_profile(self) -> None:
        self.call(
            token=self.session_a.token,
            method="POST",
            payload={
                "status": "CONTACTED",
                "mutation_id": "followup_api_mutation_0002",
            },
        )
        self.call(
            token=self.session_b.token,
            method="POST",
            payload={
                "status": "ARCHIVED",
                "mutation_id": "followup_api_mutation_0002",
            },
        )
        a = self.call(token=self.session_a.token).json_body()
        b = self.call(token=self.session_b.token).json_body()
        self.assertEqual(a["current_status"], "CONTACTED")
        self.assertEqual(b["current_status"], "ARCHIVED")
        self.assertEqual(len(a["history"]), 1)
        self.assertEqual(len(b["history"]), 1)

    def test_browser_cannot_supply_tenant_or_profile_in_mutation(self) -> None:
        response = self.call(
            token=self.session_a.token,
            method="POST",
            payload={
                "status": "CONTACTED",
                "mutation_id": "followup_api_mutation_0003",
                "tenant_id": "tenant-b",
                "profile_id": "profile-b",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body(), {"error": "INVALID_REQUEST"})
        self.assertEqual(self.call(token=self.session_a.token).json_body()["current_status"], "NEW")

    def test_unknown_public_opportunity_is_not_writable(self) -> None:
        response = self.call(
            token=self.session_a.token,
            opportunity_id="opp_99999999-9999-9999-9999-999999999999",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json_body(), {"error": "OPPORTUNITY_NOT_FOUND"})

    def test_same_mutation_with_different_payload_returns_conflict(self) -> None:
        self.call(
            token=self.session_a.token,
            method="POST",
            payload={
                "status": "REVIEWING",
                "mutation_id": "followup_api_mutation_0004",
            },
        )
        response = self.call(
            token=self.session_a.token,
            method="POST",
            payload={
                "status": "CONTACTED",
                "mutation_id": "followup_api_mutation_0004",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json_body(),
            {"error": "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"},
        )

    def test_not_fit_returns_non_auto_applied_profile_review_suggestion(self) -> None:
        response = self.call(
            token=self.session_a.token,
            method="POST",
            payload={
                "status": "NOT_FIT",
                "reason": "NO_PRODUCT_CAPABILITY",
                "mutation_id": "followup_api_mutation_0005",
            },
        )
        self.assertEqual(response.status_code, 200)
        learning = response.json_body()["profile_learning"]
        self.assertEqual(learning["learning_status"], "PROFILE_REVIEW_SUGGESTED")
        self.assertFalse(learning["suggestions"][0]["auto_apply_allowed"])


if __name__ == "__main__":
    unittest.main()
