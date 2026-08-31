from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import unittest

from tools.medical_pilot.pilot_full_chain_smoke import (
    SYNTHETIC_FACT_ID,
    SYNTHETIC_PROFILE_ID,
    SYNTHETIC_TENANT_ID,
    PilotFullChainSmokeError,
    _safe_failure,
    run_full_chain_smoke,
)


NOW = datetime(2026, 8, 31, 1, 40, tzinfo=timezone.utc)


def valid_output(model_input: dict) -> dict:
    return {
        "schema_version": "0.1",
        "opportunity_id": model_input["opportunity_id"],
        "action_type": "PREPARE_BID",
        "reason_codes": ["FORMAL_TENDER"],
        "risk_codes": ["COVERAGE_PARTIAL"],
        "supporting_fact_ids": [model_input["grounded_facts"][0]["fact_id"]],
        "supporting_profile_paths": [],
        "requires_human_confirmation": True,
    }


class PilotFullChainSmokeTests(unittest.TestCase):
    def test_full_chain_reaches_ready_through_real_runtime_queue_and_worker(self) -> None:
        calls: list[dict] = []
        sleeps: list[float] = []

        def model_call(model_input: dict) -> dict:
            calls.append(model_input)
            return valid_output(model_input)

        result = run_full_chain_smoke(
            model_call=model_call,
            now_provider=lambda: NOW,
            sleeper=lambda seconds: sleeps.append(seconds),
            completion_clock=lambda: NOW + timedelta(seconds=20),
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["database_scope"], "TEMPORARY_ONLY")
        self.assertTrue(result["invite_redeemed"])
        self.assertTrue(result["invite_replay_rejected"])
        self.assertEqual(result["account_transition"], "INVITED_TO_ACTIVE")
        self.assertTrue(result["profile_saved"])
        self.assertTrue(result["profile_personalized_ready"])
        self.assertEqual(result["initial_today_model_status"], "AWAITING_MODEL")
        self.assertEqual(result["queued_task_count"], 1)
        self.assertTrue(result["global_lease_required"])
        self.assertEqual(result["worker_status"], "READY")
        self.assertTrue(result["queue_drained"])
        self.assertEqual(result["final_today_model_status"], "READY")
        self.assertTrue(result["decision_rendered"])
        self.assertFalse(result["production_data_touched"])
        self.assertFalse(result["customer_data_used"])
        self.assertEqual(len(calls), 1)
        self.assertGreaterEqual(len(sleeps), 0)
        self.assertEqual(calls[0]["grounded_facts"][0]["fact_id"], SYNTHETIC_FACT_ID)

    def test_public_result_does_not_expose_session_invite_identity_or_model_input(self) -> None:
        result = run_full_chain_smoke(
            model_call=valid_output,
            now_provider=lambda: NOW,
            sleeper=lambda _: None,
            completion_clock=lambda: NOW + timedelta(seconds=20),
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(SYNTHETIC_TENANT_ID, serialized)
        self.assertNotIn(SYNTHETIC_PROFILE_ID, serialized)
        self.assertNotIn(SYNTHETIC_FACT_ID, serialized)
        self.assertNotIn("model_input", serialized)
        self.assertNotIn("task_id", serialized)
        self.assertNotIn("lease_id", serialized)
        self.assertNotIn("session", serialized.lower())
        self.assertNotIn("invite_code", serialized)

    def test_invalid_model_output_fails_before_ready_public_view(self) -> None:
        def invalid_output(model_input: dict) -> dict:
            output = valid_output(model_input)
            output["supporting_fact_ids"] = ["fact_not_grounded"]
            return output

        with self.assertRaises(PilotFullChainSmokeError) as context:
            run_full_chain_smoke(
                model_call=invalid_output,
                now_provider=lambda: NOW,
                sleeper=lambda _: None,
                completion_clock=lambda: NOW + timedelta(seconds=20),
            )
        self.assertEqual(context.exception.code, "WORKER_MODEL_OUTPUT_REJECTED")

    def test_provider_exception_is_reduced_to_safe_error_class_by_cli_boundary(self) -> None:
        error = RuntimeError("secret-provider-body api-key-123")
        result = _safe_failure(error)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["error_class"], "RuntimeError")
        self.assertNotIn("secret-provider-body", serialized)
        self.assertNotIn("api-key-123", serialized)
        self.assertFalse(result["production_data_touched"])


if __name__ == "__main__":
    unittest.main()
