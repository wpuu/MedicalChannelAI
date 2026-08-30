from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.agnes_global_lease import SQLiteAgnesLeaseStore
from tools.medical_pilot.outreach_service import GroundedOutreachService, OutreachServiceError, SQLiteOutreachResultStore
from tools.medical_pilot.test_model_decision_contract import verified_fact
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity
from tools.medical_pilot.today_actions_http import TrustedPrincipal


NOW = datetime(2026, 8, 30, 7, 40, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self, profile: dict, item: dict, facts: list[dict]) -> None:
        self.profile = profile
        self.item = item
        self.facts = facts

    def load_profile(self, tenant_id: str, profile_id: str):
        if self.profile.get("tenant_id") == tenant_id and self.profile.get("profile_id") == profile_id:
            return self.profile
        return None

    def load_public_opportunity(self, opportunity_id: str):
        return self.item if self.item.get("opportunity_id") == opportunity_id else None

    def load_evidence(self, tenant_id: str, opportunity_ids: list[str]):
        return {item_id: list(self.facts) if item_id == self.item["opportunity_id"] else [] for item_id in opportunity_ids}


class OutreachServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pilot.sqlite"
        self.profile = complete_profile()
        self.profile["tenant_id"] = "tenant-a"
        self.profile["profile_id"] = "profile-a"
        self.item = opportunity()
        self.facts = [
            verified_fact("fact_11111111-1111-1111-1111-111111111111", "buyer_name", "天津医科大学总医院"),
            verified_fact("fact_22222222-2222-2222-2222-222222222222", "project_name", "化学发光设备采购项目"),
        ]
        self.repository = FakeRepository(self.profile, self.item, self.facts)
        self.principal = TrustedPrincipal("tenant-a", "profile-a")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def service(self, model_call):
        return GroundedOutreachService(
            repository=self.repository,
            result_store=SQLiteOutreachResultStore(self.path),
            lease_store=SQLiteAgnesLeaseStore(self.path, now=NOW),
            model_call=model_call,
            clock=lambda: NOW + timedelta(seconds=1),
        )

    def test_same_locked_input_reuses_cache_without_second_model_call(self) -> None:
        calls: list[dict] = []

        def model_call(payload: dict) -> dict:
            calls.append(payload)
            return {
                "schema_version": "0.1",
                "opportunity_id": payload["opportunity_id"],
                "strategy_code": payload["allowed_strategy_codes"][0],
                "question_codes": [payload["allowed_question_codes"][0]],
                "positioning_code": "NO_POSITIONING",
                "supporting_fact_ids": [item["fact_id"] for item in payload["grounded_facts"]],
                "supporting_profile_paths": [],
            }

        service = self.service(model_call)
        first = service.generate(principal=self.principal, opportunity_id=self.item["opportunity_id"], now=NOW)
        second = service.generate(principal=self.principal, opportunity_id=self.item["opportunity_id"], now=NOW)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.public_result["draft"], second.public_result["draft"])

    def test_provider_is_not_called_when_not_configured(self) -> None:
        service = self.service(None)
        with self.assertRaises(OutreachServiceError) as context:
            service.generate(principal=self.principal, opportunity_id=self.item["opportunity_id"], now=NOW)
        self.assertEqual(context.exception.code, "OUTREACH_PROVIDER_NOT_CONFIGURED")

    def test_ungrounded_model_output_is_rejected_and_not_cached(self) -> None:
        calls = 0

        def bad_model(payload: dict) -> dict:
            nonlocal calls
            calls += 1
            return {
                "schema_version": "0.1",
                "opportunity_id": payload["opportunity_id"],
                "strategy_code": payload["allowed_strategy_codes"][0],
                "question_codes": [payload["allowed_question_codes"][0]],
                "positioning_code": "NO_POSITIONING",
                "supporting_fact_ids": ["fact_ffffffff-ffff-ffff-ffff-ffffffffffff"],
                "supporting_profile_paths": [],
            }

        service = self.service(bad_model)
        with self.assertRaises(OutreachServiceError) as context:
            service.generate(principal=self.principal, opportunity_id=self.item["opportunity_id"], now=NOW)
        self.assertEqual(context.exception.code, "OUTREACH_UNGROUNDED_FACT_REFERENCE")
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
