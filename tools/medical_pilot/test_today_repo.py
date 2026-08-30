from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from .test_opportunity_match_gate import complete_profile, opportunity
from .today_repo import SQLiteTodayActionsRepository


def profile_for(tenant_id: str, profile_id: str) -> dict:
    profile = complete_profile()
    profile["tenant_id"] = tenant_id
    profile["profile_id"] = profile_id
    return profile


def evidence_for(opportunity_id: str) -> dict:
    return {
        "schema_version": "0.1",
        "fact_id": f"fact_{opportunity_id}",
        "opportunity_id": opportunity_id,
        "fact_type": "OFFICIAL_PUBLIC_FACT",
        "verification_status": "VERIFIED",
        "model_generated": False,
        "field_name": "project_name",
        "field_value": "化学发光设备采购项目",
        "source_url": "https://www.ccgp.gov.cn/example/repo",
    }


class TodayRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = SQLiteTodayActionsRepository(Path(self.tmp.name) / "pilot.sqlite")
        self.profile_a = profile_for("tenant-a", "profile-a")
        self.profile_b = profile_for("tenant-b", "profile-b")
        self.item = opportunity()
        self.item["published_at"] = "2026-08-30T04:00:00+00:00"
        self.repo.upsert_profile(self.profile_a)
        self.repo.upsert_profile(self.profile_b)
        self.repo.upsert_public_opportunity(self.item)
        self.repo.upsert_public_evidence(evidence_for(self.item["opportunity_id"]))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_customer_profiles_are_tenant_isolated(self) -> None:
        self.assertEqual(
            self.repo.load_profile("tenant-a", "profile-a")["company_name"],
            self.profile_a["company_name"],
        )
        self.assertIsNone(self.repo.load_profile("tenant-b", "profile-a"))
        self.assertIsNone(self.repo.load_profile("tenant-a", "profile-b"))

    def test_public_opportunity_is_shared_without_customer_private_copy(self) -> None:
        rows_a = self.repo.list_opportunities("tenant-a", self.profile_a, limit=10)
        rows_b = self.repo.list_opportunities("tenant-b", self.profile_b, limit=10)

        self.assertEqual(rows_a, rows_b)
        self.assertEqual(rows_a[0]["opportunity_id"], self.item["opportunity_id"])
        self.assertNotIn("tenant_id", rows_a[0])
        self.assertNotIn("customer_context", rows_a[0])

    def test_public_evidence_is_shared_and_bounded_to_requested_opportunity(self) -> None:
        opportunity_id = self.item["opportunity_id"]
        evidence_a = self.repo.load_evidence("tenant-a", [opportunity_id])
        evidence_b = self.repo.load_evidence("tenant-b", [opportunity_id])

        self.assertEqual(evidence_a, evidence_b)
        self.assertEqual(evidence_a[opportunity_id][0]["verification_status"], "VERIFIED")
        self.assertEqual(self.repo.load_evidence("tenant-a", []), {})

    def test_wrong_tenant_profile_cannot_be_used_to_list_candidates(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.list_opportunities("tenant-b", self.profile_a, limit=10)

    def test_public_opportunity_rejects_customer_private_fields(self) -> None:
        leaked = copy.deepcopy(self.item)
        leaked["opportunity_id"] = "opp_private_leak"
        leaked["tenant_id"] = "tenant-a"
        leaked["customer_context"] = {"secret": True}

        with self.assertRaises(ValueError):
            self.repo.upsert_public_opportunity(leaked)

    def test_evidence_requires_known_public_opportunity(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.upsert_public_evidence(evidence_for("opp_missing"))

    def test_candidate_limit_is_hard_bounded(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.list_opportunities("tenant-a", self.profile_a, limit=501)


if __name__ == "__main__":
    unittest.main()
