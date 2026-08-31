from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from tools.medical_pilot.agnes_global_lease import SQLiteAgnesLeaseStore
from tools.medical_pilot.agnes_provider_smoke import run_provider_smoke
from tools.medical_pilot.model_decision_contract import ModelDecisionError


NOW = datetime(2026, 8, 31, 0, 30, tzinfo=timezone.utc)


class AgnesProviderSmokeTests(unittest.TestCase):
    def test_valid_provider_output_passes_contract_and_releases_lease(self) -> None:
        calls = []

        def fake_model(model_input):
            calls.append(model_input)
            return {
                "schema_version": "0.1",
                "opportunity_id": model_input["opportunity_id"],
                "action_type": "PREPARE_BID",
                "reason_codes": ["FORMAL_TENDER"],
                "risk_codes": ["COVERAGE_PARTIAL"],
                "supporting_fact_ids": [model_input["grounded_facts"][0]["fact_id"]],
                "supporting_profile_paths": ["business_role"],
                "requires_human_confirmation": True,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "lease.sqlite"
            result = run_provider_smoke(
                api_key="test-only-key",
                lease_db_path=db,
                now_provider=lambda: NOW,
                model_call=fake_model,
            )
            state = SQLiteAgnesLeaseStore(db, now=NOW).load()

        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["provider_call_executed"])
        self.assertTrue(result["contract_validation_passed"])
        self.assertEqual(result["action_type"], "PREPARE_BID")
        self.assertEqual(len(calls), 1)
        self.assertEqual(state["active_leases"], [])
        self.assertNotIn("test-only-key", str(result))

    def test_ungrounded_provider_output_is_rejected_and_lease_is_released(self) -> None:
        def fake_model(model_input):
            return {
                "schema_version": "0.1",
                "opportunity_id": model_input["opportunity_id"],
                "action_type": "PREPARE_BID",
                "reason_codes": ["FORMAL_TENDER"],
                "risk_codes": [],
                "supporting_fact_ids": ["fact_not_in_input"],
                "supporting_profile_paths": [],
                "requires_human_confirmation": True,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "lease.sqlite"
            with self.assertRaises(ModelDecisionError) as context:
                run_provider_smoke(
                    api_key="test-only-key",
                    lease_db_path=db,
                    now_provider=lambda: NOW,
                    model_call=fake_model,
                )
            state = SQLiteAgnesLeaseStore(db, now=NOW).load()

        self.assertEqual(context.exception.code, "UNGROUNDED_FACT_REFERENCE")
        self.assertEqual(state["active_leases"], [])

    def test_key_is_required_even_for_isolated_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "MCAI_AGNES_API_KEY"):
                run_provider_smoke(
                    api_key="",
                    lease_db_path=Path(temp_dir) / "lease.sqlite",
                    now_provider=lambda: NOW,
                    model_call=lambda _: {},
                )


if __name__ == "__main__":
    unittest.main()
