from __future__ import annotations

from typing import Any

from .collector_core import SCHEMA_VERSION


TERMINAL_FOLLOWUP_STATUSES = {"WON", "LOST", "NOT_FIT", "ARCHIVED"}
ACTIVE_FOLLOWUP_STATUSES = {"NEW", "REVIEWING", "CONTACTED", "RELATIONSHIP_VERIFIED", "PREPARING", "BID_SUBMITTED", "MONITOR"}
ALL_FOLLOWUP_STATUSES = TERMINAL_FOLLOWUP_STATUSES.union(ACTIVE_FOLLOWUP_STATUSES)


def route_subscription_notification(
    subscription_evaluation: dict[str, Any],
    *,
    latest_followup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply follow-up state to an already evidence-gated subscription evaluation.

    This layer never changes match/priority results. It only decides whether the
    current material event should be routed to a customer/owner, kept for the daily
    digest, sent to enrichment, or suppressed because the opportunity is terminal.
    """

    opportunity_id = str(subscription_evaluation.get("opportunity_id") or "")
    dedupe_key = str(subscription_evaluation.get("dedupe_key") or "")
    delivery_class = subscription_evaluation.get("delivery_class")
    if not opportunity_id or not dedupe_key:
        raise ValueError("subscription evaluation requires opportunity_id and dedupe_key")
    if delivery_class not in {"IMMEDIATE_HIGH_PRIORITY", "DAILY_DIGEST", "ENRICHMENT_ONLY", "NO_NOTIFY"}:
        raise ValueError(f"unsupported delivery class: {delivery_class}")

    followup_status = None
    owner = None
    if isinstance(latest_followup, dict):
        if latest_followup.get("opportunity_id") != opportunity_id:
            raise ValueError("latest_followup opportunity_id does not match subscription evaluation")
        followup_status = latest_followup.get("status")
        if followup_status not in ALL_FOLLOWUP_STATUSES:
            raise ValueError(f"unsupported followup status: {followup_status}")
        owner_value = latest_followup.get("owner")
        owner = owner_value.strip() if isinstance(owner_value, str) and owner_value.strip() else None

    if delivery_class == "ENRICHMENT_ONLY":
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": opportunity_id,
            "subscription_dedupe_key": dedupe_key,
            "source_delivery_class": delivery_class,
            "routing_status": "ENRICHMENT_ONLY",
            "audience": "NONE",
            "target_owner": None,
            "should_notify": False,
            "reason": "关键事实不足，先补证，不向客户推送。",
        }

    if delivery_class == "NO_NOTIFY":
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": opportunity_id,
            "subscription_dedupe_key": dedupe_key,
            "source_delivery_class": delivery_class,
            "routing_status": "NO_NOTIFY",
            "audience": "NONE",
            "target_owner": None,
            "should_notify": False,
            "reason": "该事件未通过订阅匹配/通知条件。",
        }

    if followup_status in TERMINAL_FOLLOWUP_STATUSES:
        return {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": opportunity_id,
            "subscription_dedupe_key": dedupe_key,
            "source_delivery_class": delivery_class,
            "routing_status": "SUPPRESS_TERMINAL_FOLLOWUP",
            "audience": "NONE",
            "target_owner": None,
            "should_notify": False,
            "reason": f"当前项目跟进状态为 {followup_status}，同一 opportunity 的后续通知默认抑制。",
        }

    audience = "OWNER" if owner else "TEAM_INBOX"
    if delivery_class == "IMMEDIATE_HIGH_PRIORITY":
        routing_status = "SEND_IMMEDIATE"
        reason = "高优先级且画像已确认；按当前负责人路由即时提醒。" if owner else "高优先级且画像已确认；进入团队即时提醒。"
    else:
        routing_status = "INCLUDE_DAILY_DIGEST"
        reason = "匹配项目进入每日摘要；已有负责人时优先归属负责人。" if owner else "匹配项目进入团队每日摘要。"

    return {
        "schema_version": SCHEMA_VERSION,
        "opportunity_id": opportunity_id,
        "subscription_dedupe_key": dedupe_key,
        "source_delivery_class": delivery_class,
        "routing_status": routing_status,
        "audience": audience,
        "target_owner": owner,
        "should_notify": True,
        "reason": reason,
    }
