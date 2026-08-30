from __future__ import annotations

import unittest
from datetime import datetime, timezone

from tools.medical_pilot.subscription_delivery_plan import build_subscription_delivery_plan
from tools.medical_pilot.subscription_engine import evaluate_subscription_event
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


def material_event(opportunity_id: str, *, event_type: str, change_fields: dict) -> dict:
    return {
        "schema_version": "0.1",
        "material_event_id": "mevt_" + "a" * 64,
        "opportunity_id": opportunity_id,
        "event_type": event_type,
        "verification_status": "VERIFIED",
        "model_generated": False,
        "change_fields": change_fields,
    }


class SubscriptionDeliveryPlanTests(unittest.TestCase):
    def _evaluation(self, event_type: str = "AWARD_PUBLISHED") -> dict:
        profile = complete_profile()
        profile["hospital_relationships"] = [
            {
                "hospital_name": "天津医科大学总医院",
                "department": "检验科",
                "relationship_strength": "STRONG",
                "owner": "销售A",
                "confirmed_by_customer": True,
                "last_confirmed_at": "2026-08-29T09:00:00+08:00",
            }
        ]
        return evaluate_subscription_event(
            profile=profile,
            opportunity=opportunity(),
            material_event_id="mevt_" + "a" * 64,
            event_type=event_type,
            immediate_priority_score_threshold=80,
        )

    def test_evening_nonurgent_high_priority_is_not_provider_queued_early(self) -> None:
        evaluation = self._evaluation("AWARD_PUBLISHED")
        event = material_event(evaluation["opportunity_id"], event_type="AWARD_PUBLISHED", change_fields={"award_status": "PUBLISHED"})
        plan = build_subscription_delivery_plan(
            evaluation,
            material_event=event,
            now=datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc),  # 20:00 local
        )
        self.assertEqual(plan["timing_status"], "SCHEDULED")
        self.assertEqual(plan["delivery_window"], "NEXT_BUSINESS_MORNING")
        self.assertFalse(plan["provider_queue_allowed"])
        self.assertIsNotNone(plan["scheduled_for"])

    def test_workday_immediate_can_enter_provider_queue(self) -> None:
        evaluation = self._evaluation("NEW_VERIFIED_OPPORTUNITY")
        event = material_event(evaluation["opportunity_id"], event_type="NEW_VERIFIED_OPPORTUNITY", change_fields={"verification_status": "VERIFIED"})
        plan = build_subscription_delivery_plan(
            evaluation,
            material_event=event,
            now=datetime(2026, 8, 31, 6, 0, tzinfo=timezone.utc),  # 14:00 local
        )
        self.assertEqual(plan["timing_status"], "SEND_NOW")
        self.assertTrue(plan["provider_queue_allowed"])

    def test_unverified_material_event_is_rejected_before_timing(self) -> None:
        evaluation = self._evaluation("NEW_VERIFIED_OPPORTUNITY")
        event = material_event(evaluation["opportunity_id"], event_type="NEW_VERIFIED_OPPORTUNITY", change_fields={"verification_status": "VERIFIED"})
        event["verification_status"] = "UNVERIFIED"
        with self.assertRaises(ValueError):
            build_subscription_delivery_plan(
                evaluation,
                material_event=event,
                now=datetime(2026, 8, 31, 6, 0, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
