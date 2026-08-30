from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.material_event import (
    MaterialEventError,
    build_material_event,
    validate_material_event_envelope,
)
from tools.medical_pilot.test_model_decision_contract import verified_fact
from tools.medical_pilot.test_opportunity_match_gate import opportunity


class MaterialEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = opportunity()
        self.lifecycle_fact = verified_fact(
            "fact_11111111-1111-1111-1111-111111111111",
            "lifecycle_state",
            "AWARDED",
        )
        self.amount_fact = verified_fact(
            "fact_22222222-2222-2222-2222-222222222222",
            "award_amount_cny",
            "8732700.00",
        )

    def test_award_event_is_built_only_from_grounded_verified_change(self) -> None:
        event = build_material_event(
            opportunity=self.item,
            event_type="AWARD_PUBLISHED",
            change_fields={"lifecycle_state": "AWARDED", "award_amount_cny": "8732700.00"},
            supporting_fact_ids=[self.lifecycle_fact["fact_id"], self.amount_fact["fact_id"]],
            available_facts=[self.lifecycle_fact, self.amount_fact],
            source_event_ids=["event_ccgp_award_001"],
            detected_at="2026-08-29T10:30:00+08:00",
            official_effective_at="2026-08-29T09:15:00+08:00",
            official_effective_at_precision="MINUTE",
        )
        self.assertEqual(event["verification_status"], "VERIFIED")
        self.assertFalse(event["model_generated"])
        self.assertEqual(event["change_fields"]["lifecycle_state"], "AWARDED")
        self.assertTrue(event["material_event_id"].startswith("mevt_"))
        self.assertTrue(event["idempotency_key"].startswith("mat_"))

    def test_mirror_evidence_and_clock_precision_do_not_change_semantic_identity(self) -> None:
        mirror_fact = verified_fact(
            "fact_33333333-3333-3333-3333-333333333333",
            "lifecycle_state",
            "AWARDED",
        )
        first = build_material_event(
            opportunity=self.item,
            event_type="AWARD_PUBLISHED",
            change_fields={"lifecycle_state": "AWARDED"},
            supporting_fact_ids=[self.lifecycle_fact["fact_id"]],
            available_facts=[self.lifecycle_fact],
            source_event_ids=["event_primary_001"],
            detected_at="2026-08-29T10:30:00+08:00",
            official_effective_at="2026-08-29T09:15:00+08:00",
            official_effective_at_precision="MINUTE",
        )
        second = build_material_event(
            opportunity=self.item,
            event_type="AWARD_PUBLISHED",
            change_fields={"lifecycle_state": "AWARDED"},
            supporting_fact_ids=[mirror_fact["fact_id"]],
            available_facts=[mirror_fact],
            source_event_ids=["event_mirror_999"],
            detected_at="2026-08-29T10:35:00+08:00",
            official_effective_at="2026-08-29T00:00:00+08:00",
            official_effective_at_precision="DAY",
        )
        self.assertEqual(first["material_event_id"], second["material_event_id"])
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertNotEqual(first["official_effective_at_precision"], second["official_effective_at_precision"])

    def test_persisted_event_hash_tampering_is_rejected(self) -> None:
        event = build_material_event(
            opportunity=self.item,
            event_type="AWARD_PUBLISHED",
            change_fields={"lifecycle_state": "AWARDED"},
            supporting_fact_ids=[self.lifecycle_fact["fact_id"]],
            available_facts=[self.lifecycle_fact],
            source_event_ids=[],
            detected_at="2026-08-29T10:30:00+08:00",
            official_effective_at=None,
            official_effective_at_precision="UNKNOWN",
        )
        event["change_fields"] = {"lifecycle_state": "TERMINATED"}
        with self.assertRaises(MaterialEventError) as context:
            validate_material_event_envelope(event)
        self.assertEqual(context.exception.code, "MATERIAL_EVENT_ID_MISMATCH")

    def test_unverified_supporting_fact_is_rejected(self) -> None:
        bad = copy.deepcopy(self.lifecycle_fact)
        bad["verification_status"] = "UNVERIFIED"
        with self.assertRaises(MaterialEventError) as context:
            build_material_event(
                opportunity=self.item,
                event_type="LIFECYCLE_STATE_CHANGED",
                change_fields={"lifecycle_state": "AWARDED"},
                supporting_fact_ids=[bad["fact_id"]],
                available_facts=[bad],
                source_event_ids=[],
                detected_at="2026-08-29T10:30:00+08:00",
                official_effective_at="2026-08-29T09:15:00+08:00",
                official_effective_at_precision="MINUTE",
            )
        self.assertEqual(context.exception.code, "SUPPORTING_FACT_NOT_VERIFIED")

    def test_change_value_not_present_in_fact_is_rejected(self) -> None:
        with self.assertRaises(MaterialEventError) as context:
            build_material_event(
                opportunity=self.item,
                event_type="LIFECYCLE_STATE_CHANGED",
                change_fields={"lifecycle_state": "TERMINATED"},
                supporting_fact_ids=[self.lifecycle_fact["fact_id"]],
                available_facts=[self.lifecycle_fact],
                source_event_ids=[],
                detected_at="2026-08-29T10:30:00+08:00",
                official_effective_at="2026-08-29T09:15:00+08:00",
                official_effective_at_precision="MINUTE",
            )
        self.assertEqual(context.exception.code, "CHANGE_NOT_GROUNDED")

    def test_unverified_opportunity_cannot_emit_material_event(self) -> None:
        item = copy.deepcopy(self.item)
        item["verification_status"] = "UNVERIFIED"
        with self.assertRaises(MaterialEventError) as context:
            build_material_event(
                opportunity=item,
                event_type="LIFECYCLE_STATE_CHANGED",
                change_fields={"lifecycle_state": "AWARDED"},
                supporting_fact_ids=[self.lifecycle_fact["fact_id"]],
                available_facts=[self.lifecycle_fact],
                source_event_ids=[],
                detected_at="2026-08-29T10:30:00+08:00",
                official_effective_at="2026-08-29T09:15:00+08:00",
                official_effective_at_precision="MINUTE",
            )
        self.assertEqual(context.exception.code, "OPPORTUNITY_NOT_VERIFIED")

    def test_deadline_event_requires_deadline_named_change_field(self) -> None:
        project_fact = verified_fact(
            "fact_44444444-4444-4444-4444-444444444444",
            "project_name",
            "化学发光设备采购项目",
        )
        with self.assertRaises(MaterialEventError) as context:
            build_material_event(
                opportunity=self.item,
                event_type="DEADLINE_CHANGED",
                change_fields={"project_name": "化学发光设备采购项目"},
                supporting_fact_ids=[project_fact["fact_id"]],
                available_facts=[project_fact],
                source_event_ids=[],
                detected_at="2026-08-29T10:30:00+08:00",
                official_effective_at="2026-08-29T09:15:00+08:00",
                official_effective_at_precision="MINUTE",
            )
        self.assertEqual(context.exception.code, "DEADLINE_FIELD_REQUIRED")


if __name__ == "__main__":
    unittest.main()
