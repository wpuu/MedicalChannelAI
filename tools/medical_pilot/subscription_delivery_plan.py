from __future__ import annotations

from datetime import datetime
from typing import Any

from .notification_time_policy import plan_notification_time
from .subscription_notification import route_subscription_notification


def build_subscription_delivery_plan(
    subscription_evaluation: dict[str, Any],
    *,
    material_event: dict[str, Any],
    now: datetime,
    latest_followup: dict[str, Any] | None = None,
    action_deadline: datetime | None = None,
    holiday_dates: set[str] | None = None,
    forced_workdays: set[str] | None = None,
) -> dict[str, Any]:
    """Create the service boundary between subscription routing and provider delivery.

    A SCHEDULED timing decision is intentionally *not* a provider queue record. The
    scheduler must wait until scheduled_for, revalidate the event/profile state, and
    only then create NotificationDelivery with QUEUED status.
    """

    opportunity_id = str(subscription_evaluation.get("opportunity_id") or "")
    if not opportunity_id:
        raise ValueError("subscription_evaluation requires opportunity_id")
    if material_event.get("opportunity_id") != opportunity_id:
        raise ValueError("material_event opportunity_id mismatch")
    if material_event.get("verification_status") != "VERIFIED" or material_event.get("model_generated") is not False:
        raise ValueError("delivery planning requires a VERIFIED non-model material event")

    route = route_subscription_notification(subscription_evaluation, latest_followup=latest_followup)
    timing = plan_notification_time(
        route,
        now=now,
        event_type=material_event.get("event_type"),
        change_fields=material_event.get("change_fields") or {},
        action_deadline=action_deadline,
        holiday_dates=holiday_dates,
        forced_workdays=forced_workdays,
    )

    provider_queue_allowed = timing.timing_status == "SEND_NOW" and route.get("should_notify") is True
    return {
        "schema_version": "0.1",
        "profile_id": subscription_evaluation.get("profile_id"),
        "opportunity_id": opportunity_id,
        "material_event_id": material_event.get("material_event_id"),
        "subscription_dedupe_key": route.get("subscription_dedupe_key"),
        "routing_status": route.get("routing_status"),
        "audience": route.get("audience"),
        "target_owner": route.get("target_owner"),
        "timing_status": timing.timing_status,
        "delivery_window": timing.delivery_window,
        "scheduled_for": timing.scheduled_for,
        "urgent_exception": timing.urgent_exception,
        "provider_queue_allowed": provider_queue_allowed,
        "reason": timing.reason,
    }
