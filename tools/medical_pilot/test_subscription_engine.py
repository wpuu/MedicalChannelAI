from __future__ import annotations

import copy
import unittest

from tools.medical_pilot.subscription_engine import evaluate_subscription_event
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


class SubscriptionEngineTests(unittest.TestCase):
    def _profile_with_strong_relationship(self, *, confirmed: bool = True) -> dict:
        profile = complete_profile(confirmed=confirmed)
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
        return profile

    def test_high_priority_personalized_match_can_alert_immediately(self) -> None:
        result = evaluate_subscription_event(
            profile=self._profile_with_strong_relationship(),
            opportunity=opportunity(),
            material_event_id="event-tender-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
            immediate_priority_score_threshold=80,
        )
        self.assertEqual(result["evaluation_status"], "MATCHED")
        self.assertEqual(result["delivery_class"], "IMMEDIATE_HIGH_PRIORITY")
        self.assertGreaterEqual(result["priority_score"], 80)
        self.assertIn("PRIORITY_THRESHOLD_MET", result["reasons"])

    def test_unconfirmed_profile_never_gets_immediate_alert_even_with_high_score(self) -> None:
        result = evaluate_subscription_event(
            profile=self._profile_with_strong_relationship(confirmed=False),
            opportunity=opportunity(),
            material_event_id="event-tender-002",
            event_type="NEW_VERIFIED_OPPORTUNITY",
            immediate_priority_score_threshold=80,
        )
        self.assertEqual(result["evaluation_status"], "MATCHED")
        self.assertEqual(result["delivery_class"], "DAILY_DIGEST")

    def test_missing_product_fact_goes_to_enrichment_without_customer_notification(self) -> None:
        item = opportunity()
        item["product_labels"] = []
        result = evaluate_subscription_event(
            profile=complete_profile(),
            opportunity=item,
            material_event_id="event-needs-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
        )
        self.assertEqual(result["evaluation_status"], "NEEDS_MORE_FACTS")
        self.assertEqual(result["delivery_class"], "ENRICHMENT_ONLY")
        self.assertFalse(result["model_explanation_allowed"])

    def test_outside_region_is_not_notified(self) -> None:
        item = opportunity()
        item["region"] = {"province": "河北省", "city": "唐山市", "district": "路北区"}
        result = evaluate_subscription_event(
            profile=complete_profile(),
            opportunity=item,
            material_event_id="event-reject-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
        )
        self.assertEqual(result["evaluation_status"], "REJECTED_OR_BLOCKED")
        self.assertEqual(result["delivery_class"], "NO_NOTIFY")

    def test_same_profile_opportunity_and_material_event_produce_stable_dedupe_key(self) -> None:
        kwargs = {
            "profile": complete_profile(),
            "opportunity": opportunity(),
            "material_event_id": "event-stable-001",
            "event_type": "LIFECYCLE_STATE_CHANGED",
        }
        first = evaluate_subscription_event(**kwargs)
        second = evaluate_subscription_event(**kwargs)
        self.assertEqual(first["dedupe_key"], second["dedupe_key"])

    def test_new_material_event_changes_dedupe_key(self) -> None:
        first = evaluate_subscription_event(
            profile=complete_profile(),
            opportunity=opportunity(),
            material_event_id="event-version-001",
            event_type="DEADLINE_CHANGED",
        )
        second = evaluate_subscription_event(
            profile=complete_profile(),
            opportunity=opportunity(),
            material_event_id="event-version-002",
            event_type="DEADLINE_CHANGED",
        )
        self.assertNotEqual(first["dedupe_key"], second["dedupe_key"])

    def test_unverified_opportunity_never_enters_customer_delivery(self) -> None:
        item = copy.deepcopy(opportunity())
        item["verification_status"] = "UNVERIFIED"
        result = evaluate_subscription_event(
            profile=complete_profile(),
            opportunity=item,
            material_event_id="event-unverified-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
        )
        self.assertEqual(result["delivery_class"], "NO_NOTIFY")
        self.assertFalse(result["model_explanation_allowed"])


if __name__ == "__main__":
    unittest.main()
