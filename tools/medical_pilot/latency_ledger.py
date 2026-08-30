from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from .collector_core import SCHEMA_VERSION


class LatencyLedgerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _parse_aware(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LatencyLedgerError("TIMESTAMP_INVALID", f"{field_name} must be an ISO datetime or null")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LatencyLedgerError("TIMESTAMP_INVALID", f"invalid {field_name}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LatencyLedgerError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field_name} must include a timezone offset")
    return parsed


def _seconds(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    value = int((end - start).total_seconds())
    if value < 0:
        raise LatencyLedgerError("TIMESTAMP_ORDER_INVALID", "latency stage timestamps are not monotonic")
    return value


def _ledger_id(source_id: str, opportunity_id: str, material_event_id: str) -> str:
    payload = "|".join((source_id, opportunity_id, material_event_id)).encode("utf-8")
    return "lat_" + hashlib.sha256(payload).hexdigest()


def _status(
    fetched_at: datetime | None,
    verified_at: datetime | None,
    matched_at: datetime | None,
    queued_at: datetime | None,
    delivered_at: datetime | None,
) -> str:
    if fetched_at is None:
        return "DISCOVERED_ONLY"
    if verified_at is None:
        return "FETCHED_NOT_VERIFIED"
    if matched_at is None:
        return "VERIFIED_NOT_MATCHED"
    if queued_at is None:
        return "MATCHED_NOT_QUEUED"
    if delivered_at is None:
        return "QUEUED_NOT_DELIVERED"
    return "FULL_NOTIFICATION_PATH"


def build_latency_ledger(
    *,
    source_id: str,
    opportunity_id: str,
    material_event_id: str,
    official_published_at: str | None,
    official_published_at_precision: str,
    discovered_at: str,
    fetched_at: str | None = None,
    verified_at: str | None = None,
    matched_at: str | None = None,
    notification_queued_at: str | None = None,
    delivered_at: str | None = None,
) -> dict[str, Any]:
    """Build one immutable latency snapshot without inventing publication precision.

    DAY/UNKNOWN publication timestamps never produce a publication-to-discovery
    latency. Operational stages must be monotonic and timezone-aware. A later stage
    cannot exist when its required earlier stage is absent.
    """

    if official_published_at_precision not in {"DAY", "MINUTE", "SECOND", "UNKNOWN"}:
        raise LatencyLedgerError("PUBLICATION_PRECISION_INVALID", official_published_at_precision)
    if not source_id or not opportunity_id or not material_event_id:
        raise LatencyLedgerError("IDENTITY_REQUIRED", "source_id, opportunity_id and material_event_id are required")

    published = _parse_aware(official_published_at, "official_published_at")
    discovered = _parse_aware(discovered_at, "discovered_at")
    fetched = _parse_aware(fetched_at, "fetched_at")
    verified = _parse_aware(verified_at, "verified_at")
    matched = _parse_aware(matched_at, "matched_at")
    queued = _parse_aware(notification_queued_at, "notification_queued_at")
    delivered = _parse_aware(delivered_at, "delivered_at")
    assert discovered is not None

    if verified is not None and fetched is None:
        raise LatencyLedgerError("FETCH_REQUIRED_BEFORE_VERIFY", "verified_at requires fetched_at")
    if matched is not None and verified is None:
        raise LatencyLedgerError("VERIFY_REQUIRED_BEFORE_MATCH", "matched_at requires verified_at")
    if queued is not None and matched is None:
        raise LatencyLedgerError("MATCH_REQUIRED_BEFORE_QUEUE", "notification_queued_at requires matched_at")
    if delivered is not None and queued is None:
        raise LatencyLedgerError("QUEUE_REQUIRED_BEFORE_DELIVERY", "delivered_at requires notification_queued_at")

    discovery_to_fetch = _seconds(discovered, fetched)
    fetch_to_verified = _seconds(fetched, verified)
    verified_to_match = _seconds(verified, matched)
    match_to_queue = _seconds(matched, queued)
    queue_to_delivery = _seconds(queued, delivered)
    discovery_to_delivery = _seconds(discovered, delivered)

    warnings: list[str] = []
    publication_to_discovery: int | None = None
    publication_latency_precision = "UNAVAILABLE"
    if published is None or official_published_at_precision in {"DAY", "UNKNOWN"}:
        warnings.append("OFFICIAL_PUBLICATION_TIME_PRECISION_INSUFFICIENT")
    else:
        delta = int((discovered - published).total_seconds())
        if delta < 0:
            warnings.append("DISCOVERY_PRECEDES_REPORTED_PUBLICATION_TIME")
        else:
            publication_to_discovery = delta
        publication_latency_precision = official_published_at_precision

    return {
        "schema_version": SCHEMA_VERSION,
        "ledger_id": _ledger_id(source_id, opportunity_id, material_event_id),
        "source_id": source_id,
        "opportunity_id": opportunity_id,
        "material_event_id": material_event_id,
        "official_published_at": official_published_at,
        "official_published_at_precision": official_published_at_precision,
        "discovered_at": discovered_at,
        "fetched_at": fetched_at,
        "verified_at": verified_at,
        "matched_at": matched_at,
        "notification_queued_at": notification_queued_at,
        "delivered_at": delivered_at,
        "latency_status": _status(fetched, verified, matched, queued, delivered),
        "latencies_seconds": {
            "publication_to_discovery": publication_to_discovery,
            "discovery_to_fetch": discovery_to_fetch,
            "fetch_to_verified": fetch_to_verified,
            "verified_to_match": verified_to_match,
            "match_to_queue": match_to_queue,
            "queue_to_delivery": queue_to_delivery,
            "discovery_to_delivery": discovery_to_delivery,
        },
        "publication_latency_precision": publication_latency_precision,
        "warnings": warnings,
    }
