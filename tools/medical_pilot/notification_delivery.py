from __future__ import annotations

import copy
import hashlib
from datetime import datetime
from typing import Any

from .collector_core import SCHEMA_VERSION


CHANNELS = {"WEB_INBOX", "WECHAT_MINI_PROGRAM", "MOBILE_PUSH"}
DELIVERY_STATUSES = {"QUEUED", "SENT", "DELIVERED", "FAILED", "SUPPRESSED"}


class NotificationDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_aware(value: str | None, field_name: str) -> None:
    if value is None:
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise NotificationDeliveryError("TIMESTAMP_INVALID", f"invalid {field_name}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NotificationDeliveryError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field_name} must include timezone")


def _identity(subscription_dedupe_key: str, channel: str) -> str:
    return hashlib.sha256(f"{subscription_dedupe_key}|{channel}".encode("utf-8")).hexdigest()


def create_delivery_record(
    *,
    profile_id: str,
    opportunity_id: str,
    material_event_id: str,
    notification_route: dict[str, Any],
    channel: str,
    queued_at: str | None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Create an idempotent delivery record from the deterministic notification route.

    This function does not call any notification provider. A suppressed route creates a
    SUPPRESSED audit record; a routable notification creates QUEUED. Provider retry
    logic must reuse the same idempotency key instead of creating another notification.
    """

    if channel not in CHANNELS:
        raise NotificationDeliveryError("CHANNEL_INVALID", channel)
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
        raise NotificationDeliveryError("MAX_ATTEMPTS_INVALID", "max_attempts must be 1..10")
    dedupe_key = notification_route.get("subscription_dedupe_key")
    if not isinstance(dedupe_key, str) or not dedupe_key.startswith("subeval_"):
        raise NotificationDeliveryError("SUBSCRIPTION_DEDUPE_KEY_INVALID", "valid subscription dedupe key required")
    if notification_route.get("opportunity_id") != opportunity_id:
        raise NotificationDeliveryError("OPPORTUNITY_MISMATCH", "notification route opportunity_id mismatch")

    should_notify = notification_route.get("should_notify") is True
    audience = notification_route.get("audience")
    target_owner = notification_route.get("target_owner")
    if should_notify:
        if audience not in {"OWNER", "TEAM_INBOX"}:
            raise NotificationDeliveryError("AUDIENCE_INVALID", "routable notification needs OWNER or TEAM_INBOX")
        if not isinstance(queued_at, str) or not queued_at:
            raise NotificationDeliveryError("QUEUED_AT_REQUIRED", "queued_at is required when should_notify=true")
        _require_aware(queued_at, "queued_at")
        status = "QUEUED"
    else:
        if audience != "NONE":
            raise NotificationDeliveryError("SUPPRESSED_AUDIENCE_INVALID", "suppressed route must use audience NONE")
        if queued_at is not None:
            raise NotificationDeliveryError("SUPPRESSED_MUST_NOT_QUEUE", "suppressed notification cannot have queued_at")
        status = "SUPPRESSED"
        audience = "TEAM_INBOX"  # schema excludes NONE because no delivery target exists; retained only as audit placeholder.
        target_owner = None

    digest = _identity(dedupe_key, channel)
    return {
        "schema_version": SCHEMA_VERSION,
        "notification_id": "notify_" + digest,
        "idempotency_key": "ndel_" + digest,
        "subscription_dedupe_key": dedupe_key,
        "profile_id": profile_id,
        "opportunity_id": opportunity_id,
        "material_event_id": material_event_id,
        "channel": channel,
        "audience": audience,
        "target_owner": target_owner,
        "status": status,
        "attempt_count": 0,
        "max_attempts": max_attempts,
        "queued_at": queued_at,
        "sent_at": None,
        "delivered_at": None,
        "failed_at": None,
        "provider_message_id": None,
        "last_error_code": None,
    }


def mark_sent(record: dict[str, Any], *, sent_at: str, provider_message_id: str | None = None) -> dict[str, Any]:
    if record.get("status") not in {"QUEUED", "FAILED"}:
        raise NotificationDeliveryError("SEND_TRANSITION_INVALID", f"cannot send from {record.get('status')}")
    if record.get("status") == "FAILED" and int(record.get("attempt_count") or 0) >= int(record.get("max_attempts") or 0):
        raise NotificationDeliveryError("RETRY_LIMIT_REACHED", "notification retry limit reached")
    _require_aware(sent_at, "sent_at")
    result = copy.deepcopy(record)
    result["status"] = "SENT"
    result["attempt_count"] = int(result.get("attempt_count") or 0) + 1
    result["sent_at"] = sent_at
    result["delivered_at"] = None
    result["failed_at"] = None
    result["provider_message_id"] = provider_message_id
    result["last_error_code"] = None
    return result


def mark_delivered(record: dict[str, Any], *, delivered_at: str) -> dict[str, Any]:
    if record.get("status") != "SENT":
        raise NotificationDeliveryError("DELIVERY_TRANSITION_INVALID", "DELIVERED requires SENT")
    _require_aware(delivered_at, "delivered_at")
    sent = datetime.fromisoformat(str(record["sent_at"]).replace("Z", "+00:00"))
    delivered = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
    if delivered < sent:
        raise NotificationDeliveryError("TIMESTAMP_ORDER_INVALID", "delivered_at precedes sent_at")
    result = copy.deepcopy(record)
    result["status"] = "DELIVERED"
    result["delivered_at"] = delivered_at
    return result


def mark_failed(record: dict[str, Any], *, failed_at: str, error_code: str) -> dict[str, Any]:
    if record.get("status") not in {"QUEUED", "SENT"}:
        raise NotificationDeliveryError("FAIL_TRANSITION_INVALID", f"cannot fail from {record.get('status')}")
    if not isinstance(error_code, str) or not error_code:
        raise NotificationDeliveryError("ERROR_CODE_REQUIRED", "error_code is required")
    _require_aware(failed_at, "failed_at")
    result = copy.deepcopy(record)
    result["status"] = "FAILED"
    result["failed_at"] = failed_at
    result["last_error_code"] = error_code
    return result
