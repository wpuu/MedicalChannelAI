from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.medical_pilot.profile_http import ProfileHttpTransport
from tools.medical_pilot.test_opportunity_match_gate import complete_profile
from tools.medical_pilot.today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 30, 23, 50, tzinfo=ZoneInfo("Asia/Shanghai"))


class Resolver:
    def __init__(self, principal: TrustedPrincipal | None) -> None:
        self.principal = principal

    def resolve(self, headers):
        return self.principal


class Repository:
    def __init__(self, profile: dict) -> None:
        self.profile = copy.deepcopy(profile)
        self.upserts: list[dict] = []

    def load_profile(self, tenant_id: str, profile_id: str):
        if tenant_id != self.profile.get("tenant_id") or profile_id != self.profile.get("profile_id"):
            return None
        return copy.deepcopy(self.profile)

    def upsert_profile(self, profile: dict) -> None:
        self.profile = copy.deepcopy(profile)
        self.upserts.append(copy.deepcopy(profile))


def editable_payload(profile: dict) -> dict:
    keys = {
        "company_name",
        "business_role",
        "operating_regions",
        "customer_types",
        "product_capabilities",
        "partnering_policy",
        "opportunity_thresholds",
        "exclusion_rules",
        "hospital_relationships",
        "confirmation_flags",
    }
    return {key: copy.deepcopy(profile[key]) for key in keys}


class ProfileHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        profile = complete_profile()
        self.repo = Repository(profile)
        self.principal = TrustedPrincipal(profile["tenant_id"], profile["profile_id"])
        self.transport = ProfileHttpTransport(
            principal_resolver=Resolver(self.principal),
            repository=self.repo,
        )

    def test_get_returns_only_signed_in_customer_profile_view(self) -> None:
        response = self.transport.handle(
            method="GET",
            target="/profile",
            headers={},
            body=b"",
            now=NOW,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json_body()
        self.assertIn("profile", body)
        self.assertIn("readiness", body)
        self.assertNotIn("tenant_id", body["profile"])
        self.assertNotIn("profile_id", body["profile"])
        self.assertTrue(body["readiness"]["personalized_recommendation_allowed"])

    def test_put_recomputes_readiness_and_persists_session_bound_identity(self) -> None:
        payload = editable_payload(self.repo.profile)
        payload["company_name"] = "天津真实渠道客户"
        payload["hospital_relationships"] = [
            {
                "hospital_name": "天津某医院",
                "department": "检验科",
                "relationship_strength": "STRONG",
                "owner": "客户本人",
                "confirmed_by_customer": True,
                "last_confirmed_at": NOW.isoformat(),
            }
        ]
        response = self.transport.handle(
            method="PUT",
            target="/profile",
            headers={},
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            now=NOW,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.repo.upserts), 1)
        saved = self.repo.upserts[0]
        self.assertEqual(saved["tenant_id"], self.principal.tenant_id)
        self.assertEqual(saved["profile_id"], self.principal.profile_id)
        self.assertEqual(saved["company_name"], "天津真实渠道客户")
        self.assertEqual(saved["profile_status"], "SUFFICIENT_FOR_PERSONALIZED_RECOMMENDATION")
        self.assertGreaterEqual(saved["profile_completeness"], 80)
        self.assertEqual(saved["missing_required_conditions"], [])

    def test_valid_profile_save_requests_immediate_today_refresh(self) -> None:
        calls: list[tuple[TrustedPrincipal, datetime]] = []
        transport = ProfileHttpTransport(
            principal_resolver=Resolver(self.principal),
            repository=self.repo,
            after_save=lambda principal, now: calls.append((principal, now)),
        )
        payload = editable_payload(self.repo.profile)
        response = transport.handle(
            method="PUT",
            target="/profile",
            headers={},
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            now=NOW,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [(self.principal, NOW)])

    def test_browser_cannot_override_tenant_or_profile_identity(self) -> None:
        payload = editable_payload(self.repo.profile)
        payload["tenant_id"] = "other-tenant"
        payload["profile_id"] = "mprof_99999999-9999-9999-9999-999999999999"
        response = self.transport.handle(
            method="PUT",
            target="/profile",
            headers={},
            body=json.dumps(payload).encode("utf-8"),
            now=NOW,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body(), {"error": "INVALID_REQUEST"})
        self.assertEqual(self.repo.upserts, [])

    def test_unauthenticated_profile_access_is_rejected(self) -> None:
        transport = ProfileHttpTransport(
            principal_resolver=Resolver(None),
            repository=self.repo,
        )
        response = transport.handle(
            method="GET",
            target="/profile",
            headers={},
            body=b"",
            now=NOW,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json_body(), {"error": "UNAUTHORIZED"})


if __name__ == "__main__":
    unittest.main()
