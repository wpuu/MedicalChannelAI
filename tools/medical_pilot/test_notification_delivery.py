from __future__ import annotations

import unittest

from tools.medical_pilot.notification_delivery import (
    NotificationDeliveryError,
    create_delivery_record,
    mark_delivered,
    mark_failed,
    mark_sent,
)
from tools.medical_pilot.subscription_engine import evaluate_subscription_event
from tools.medical_pilot.subscription_notification import route_subscription_notification
from tools.medical_pilot.test_opportunity_match_gate import complete_profile, opportunity


class NotificationDeliveryTests(unittest.TestCase):
    def _route(self, *, notify: bool = True) -> tuple[dict, dict]:
        profile = complete_profile()
        item = opportunity()
        if notify:
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
        else:
            item["region"] = {"province": "河北省", "city": "唐山市", "district": "路北区"}
        evaluation = evaluate_subscription_event(
            profile=profile,
            opportunity=item,
            material_event_id="mevt_" + "1" * 64,
            event_type="NEW_VERIFIED_OPPORTUNITY",
            immediate_priority_score_threshold=80,
        )
        return item, route_subscription_notification(evaluation)

    def test_same_subscription_event_and_channel_have_stable_notification_identity(self) -> None:
        item, route = self._route()
        kwargs = {
            "profile_id": complete_profile()["profile_id"],
            "opportunity_id": item["opportunity_id"],
            "material_event_id": "mevt_" + "1" * 64,
            "notification_route": route,
            "channel": "WECHAT_MINI_PROGRAM",
            "queued_at": "2026-08-29T10:40:00+08:00",
        }
        first = create_delivery_record(**kwargs)
        second = create_delivery_record(**kwargs)
        self.assertEqual(first["notification_id"], second["notification_id"])
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertEqual(first["status"], "QUEUED")

    def test_suppressed_route_is_recorded_truthfully_without_queue(self) -> None:
        item, route = self._route(notify=False)
        record = create_delivery_record(
            profile_id=complete_profile()["profile_id"],
            opportunity_id=item["opportunity_id"],
            material_event_id="mevt_" + "2" * 64,
            notification_route=route,
            channel="WEB_INBOX",
            queued_at=None,
        )
        self.assertEqual(record["status"], "SUPPRESSED")
        self.assertEqual(record["audience"], "NONE")
        self.assertIsNone(record["queued_at"])

    def test_delivery_state_machine_preserves_chronology(self) -> None:
        item, route = self._route()
        queued = create_delivery_record(
            profile_id=complete_profile()["profile_id"],
            opportunity_id=item["opportunity_id"],
            material_event_id="mevt_" + "3" * 64,
            notification_route=route,
            channel="WECHAT_MINI_PROGRAM",
            queued_at="2026-08-29T10:40:00+08:00",
        )
        sent = mark_sent(queued, sent_at="2026-08-29T10:40:05+08:00", provider_message_id="wxmsg-1")
        delivered = mark_delivered(sent, delivered_at="2026-08-29T10:40:08+08:00")
        self.assertEqual(sent["attempt_count"], 1)
        self.assertEqual(delivered["status"], "DELIVERED")
        self.assertEqual(delivered["provider_message_id"], "wxmsg-1")

    def test_failed_send_reuses_same_notification_identity_for_retry(self) -> None:
        item, route = self._route()
        queued = create_delivery_record(
            profile_id=complete_profile()["profile_id"],
            opportunity_id=item["opportunity_id"],
            material_event_id="mevt_" + "4" * 64,
            notification_route=route,
            channel="WECHAT_MINI_PROGRAM",
            queued_at="2026-08-29T10:40:00+08:00",
            max_attempts=2,
        )
        first_sent = mark_sent(queued, sent_at="2026-08-29T10:40:05+08:00")
        failed = mark_failed(first_sent, failed_at="2026-08-29T10:40:06+08:00", error_code="PROVIDER_TIMEOUT")
        retried = mark_sent(failed, sent_at="2026-08-29T10:40:10+08:00")
        self.assertEqual(retried["notification_id"], queued["notification_id"])
        self.assertEqual(retried["idempotency_key"], queued["idempotency_key"])
        self.assertEqual(retried["attempt_count"], 2)
        failed_again = mark_failed(retried, failed_at="2026-08-29T10:40:11+08:00", error_code="PROVIDER_TIMEOUT")
        with self.assertRaises(NotificationDeliveryError) as context:
            mark_sent(failed_again, sent_at="2026-08-29T10:40:15+08:00")
        self.assertEqual(context.exception.code, "RETRY_LIMIT_REACHED")

    def test_sent_before_queue_is_rejected(self) -> None:
        item, route = self._route()
        queued = create_delivery_record(
            profile_id=complete_profile()["profile_id"],
            opportunity_id=item["opportunity_id"],
            material_event_id="mevt_" + "5" * 64,
            notification_route=route,
            channel="WEB_INBOX",
            queued_at="2026-08-29T10:40:00+08:00",
        )
        with self.assertRaises(NotificationDeliveryError) as context:
            mark_sent(queued, sent_at="2026-08-29T10:39:59+08:00")
        self.assertEqual(context.exception.code, "TIMESTAMP_ORDER_INVALID")

    def test_delivered_before_sent_is_rejected(self) -> None:
        item, route = self._route()
        queued = create_delivery_record(
            profile_id=complete_profile()["profile_id"],
            opportunity_id=item["opportunity_id"],
            material_event_id="mevt_" + "6" * 64,
            notification_route=route,
            channel="WEB_INBOX",
            queued_at="2026-08-29T10:40:00+08:00",
        )
        sent = mark_sent(queued, sent_at="2026-08-29T10:40:05+08:00")
        with self.assertRaises(NotificationDeliveryError) as context:
            mark_delivered(sent, delivered_at="2026-08-29T10:40:04+08:00")
        self.assertEqual(context.exception.code, "TIMESTAMP_ORDER_INVALID")


if __name__ == "__main__":
    unittest.main()
