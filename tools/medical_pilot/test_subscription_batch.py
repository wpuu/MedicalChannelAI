from __future__ import annotations

import unittest

from tools.medical_pilot.subscription_batch import process_subscription_event_batch
from tools.medical_pilot.test_opportunity_match_gate import opportunity
from tools.medical_pilot.test_subscription_prefilter import DR, profile_variant


class SubscriptionBatchTests(unittest.TestCase):
    def test_event_processing_is_bounded_and_resumable(self) -> None:
        profiles = [profile_variant(index + 1) for index in range(7)]
        first = process_subscription_event_batch(
            profiles=profiles,
            opportunity=opportunity(),
            material_event_id="event-batch-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
            batch_limit=3,
        )
        self.assertEqual(first["candidate_profile_count"], 7)
        self.assertEqual(first["processed_profile_count"], 3)
        self.assertEqual(first["next_offset"], 3)

        second = process_subscription_event_batch(
            profiles=profiles,
            opportunity=opportunity(),
            material_event_id="event-batch-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
            batch_offset=3,
            batch_limit=3,
        )
        self.assertEqual(second["processed_profile_count"], 3)
        self.assertEqual(second["next_offset"], 6)

        third = process_subscription_event_batch(
            profiles=profiles,
            opportunity=opportunity(),
            material_event_id="event-batch-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
            batch_offset=6,
            batch_limit=3,
        )
        self.assertEqual(third["processed_profile_count"], 1)
        self.assertIsNone(third["next_offset"])

    def test_irrelevant_profile_is_removed_by_prefilter_before_full_match(self) -> None:
        relevant = profile_variant(1)
        irrelevant = profile_variant(2, taxonomy=DR)
        result = process_subscription_event_batch(
            profiles=[relevant, irrelevant],
            opportunity=opportunity(),
            material_event_id="event-batch-002",
            event_type="NEW_VERIFIED_OPPORTUNITY",
        )
        self.assertEqual(result["candidate_profile_count"], 1)
        self.assertEqual(result["dispatches"][0]["profile_id"], relevant["profile_id"])

    def test_terminal_followup_suppresses_delivery_inside_batch(self) -> None:
        profile = profile_variant(1)
        result = process_subscription_event_batch(
            profiles=[profile],
            opportunity=opportunity(),
            material_event_id="event-batch-003",
            event_type="LIFECYCLE_STATE_CHANGED",
            latest_followups_by_profile={
                profile["profile_id"]: {
                    "opportunity_id": opportunity()["opportunity_id"],
                    "status": "ARCHIVED",
                    "owner": "销售A",
                }
            },
        )
        self.assertEqual(result["dispatches"][0]["routing_status"], "SUPPRESS_TERMINAL_FOLLOWUP")
        self.assertFalse(result["dispatches"][0]["should_notify"])

    def test_missing_opportunity_taxonomy_stops_before_profile_batch_scan(self) -> None:
        item = opportunity()
        item["product_labels"] = []
        result = process_subscription_event_batch(
            profiles=[profile_variant(1), profile_variant(2)],
            opportunity=item,
            material_event_id="event-batch-004",
            event_type="NEW_VERIFIED_OPPORTUNITY",
        )
        self.assertEqual(result["status"], "NEEDS_MORE_FACTS")
        self.assertEqual(result["processed_profile_count"], 0)
        self.assertIn("opportunity.product_labels", result["required_next_facts"])

    def test_batch_limit_has_hard_safety_cap(self) -> None:
        with self.assertRaises(ValueError):
            process_subscription_event_batch(
                profiles=[profile_variant(1)],
                opportunity=opportunity(),
                material_event_id="event-batch-005",
                event_type="NEW_VERIFIED_OPPORTUNITY",
                batch_limit=1001,
            )


if __name__ == "__main__":
    unittest.main()
