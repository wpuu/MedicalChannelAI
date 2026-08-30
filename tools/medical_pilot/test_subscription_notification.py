from __future__ import annotations

import unittest

from tools.medical_pilot.subscription_engine import evaluate_subscription_event
from tools.medical_pilot.subscription_notification import route_subscription_notification
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


class SubscriptionNotificationTests(unittest.TestCase):
    def _high_priority_eval(self) -> dict:
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
            material_event_id="event-notify-001",
            event_type="LIFECYCLE_STATE_CHANGED",
            immediate_priority_score_threshold=80,
        )

    def test_immediate_event_routes_to_existing_owner(self) -> None:
        evaluation = self._high_priority_eval()
        followup = {
            "opportunity_id": evaluation["opportunity_id"],
            "status": "CONTACTED",
            "owner": "销售B",
        }
        route = route_subscription_notification(evaluation, latest_followup=followup)
        self.assertEqual(route["routing_status"], "SEND_IMMEDIATE")
        self.assertEqual(route["audience"], "OWNER")
        self.assertEqual(route["target_owner"], "销售B")
        self.assertTrue(route["should_notify"])

    def test_no_owner_uses_team_inbox(self) -> None:
        evaluation = self._high_priority_eval()
        route = route_subscription_notification(evaluation)
        self.assertEqual(route["audience"], "TEAM_INBOX")
        self.assertTrue(route["should_notify"])

    def test_terminal_followup_suppresses_same_opportunity_notifications(self) -> None:
        evaluation = self._high_priority_eval()
        for status in ("WON", "LOST", "NOT_FIT", "ARCHIVED"):
            with self.subTest(status=status):
                route = route_subscription_notification(
                    evaluation,
                    latest_followup={
                        "opportunity_id": evaluation["opportunity_id"],
                        "status": status,
                        "owner": "销售A",
                    },
                )
                self.assertEqual(route["routing_status"], "SUPPRESS_TERMINAL_FOLLOWUP")
                self.assertFalse(route["should_notify"])
                self.assertEqual(route["audience"], "NONE")

    def test_enrichment_only_never_notifies_even_with_owner(self) -> None:
        item = opportunity()
        item["product_labels"] = []
        evaluation = evaluate_subscription_event(
            profile=complete_profile(),
            opportunity=item,
            material_event_id="event-enrich-001",
            event_type="NEW_VERIFIED_OPPORTUNITY",
        )
        route = route_subscription_notification(
            evaluation,
            latest_followup={
                "opportunity_id": item["opportunity_id"],
                "status": "REVIEWING",
                "owner": "销售A",
            },
        )
        self.assertEqual(route["routing_status"], "ENRICHMENT_ONLY")
        self.assertFalse(route["should_notify"])

    def test_followup_for_other_opportunity_is_rejected(self) -> None:
        evaluation = self._high_priority_eval()
        with self.assertRaises(ValueError):
            route_subscription_notification(
                evaluation,
                latest_followup={
                    "opportunity_id": "opp_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "status": "CONTACTED",
                    "owner": "销售A",
                },
            )


if __name__ == "__main__":
    unittest.main()
