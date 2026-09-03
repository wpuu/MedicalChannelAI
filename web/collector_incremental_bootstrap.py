from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import collector_incremental_runtime as incremental_runtime
from collector_incremental import (
    SOURCE_POLICIES,
    candidate_observation,
    normalize_ledger,
    plan_detail_verification,
    record_verification_success,
)


RECENT_DEEP_VERIFICATION_MAX_AGE = timedelta(hours=6)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("INCREMENTAL_BOOTSTRAP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _parsed_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _record_source_url(record: Any) -> str | None:
    if not isinstance(record, dict):
        return None
    source = record.get("source")
    if not isinstance(source, dict):
        return None
    url = source.get("url")
    return str(url).strip() if isinstance(url, str) and url.strip() else None


def _record_observed_at(record: Any) -> datetime | None:
    if not isinstance(record, dict):
        return None
    source = record.get("source")
    return _parsed_at(source.get("observed_at")) if isinstance(source, dict) else None


def _candidate_value(candidate: Any, key: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key)
    return getattr(candidate, key, None)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonical_matches_discovery(source_id: str, candidate: Any, record: dict[str, Any]) -> bool:
    # Never infer a current fingerprint merely from URL equality. We only bridge
    # a recent deep verification when the index metadata we fingerprint now still
    # agrees with the verified canonical facts. TJFCH procurement intentionally
    # stays out because its index titles may be officially truncated while detail
    # verification recovers a fuller title.
    if source_id == "tjfch":
        return False
    facts = record.get("facts")
    if not isinstance(facts, dict):
        return False
    candidate_title = _clean(_candidate_value(candidate, "title"))
    canonical_title = _clean(facts.get("project_name"))
    if candidate_title and canonical_title and candidate_title != canonical_title:
        return False
    candidate_published = _clean(_candidate_value(candidate, "published_at"))
    canonical_published = _clean(facts.get("published_at"))
    if candidate_published and canonical_published and candidate_published != canonical_published:
        return False
    return True


def bootstrap_incremental_ledger_from_canonical(
    source_id: str,
    *,
    now: datetime,
    cache: Any,
) -> dict[str, Any]:
    source = str(source_id or "").strip().lower()
    if source not in incremental_runtime.SUPPORTED_INCREMENTAL_SOURCES:
        return {"action": "UNSUPPORTED_SOURCE", "source_id": source}

    current = _utc(now)
    existing_ledger = incremental_runtime._load_ledger(cache, source)
    if normalize_ledger(existing_ledger)["entries"]:
        return {"action": "LEDGER_ALREADY_INITIALIZED", "source_id": source}

    try:
        discovered = incremental_runtime._DISCOVERY[source](current)
    except Exception:
        # This helper is only an optimization. The authoritative incremental run
        # that follows still owns discovery errors/retries and must not be masked.
        return {"action": "BOOTSTRAP_DISCOVERY_UNAVAILABLE", "source_id": source}

    policy = SOURCE_POLICIES[source]
    plan = plan_detail_verification(
        source,
        discovered,
        existing_ledger,
        now=current,
        reverify_after_hours=policy["reverify_after_hours"],
        max_details=policy["max_details_per_scan"],
    )
    ledger = plan.next_ledger
    canonical_records, _ = incremental_runtime._existing_records(cache, source)
    canonical_by_url = {
        url: record
        for record in canonical_records
        if (url := _record_source_url(record)) is not None
    }

    seeded = 0
    stale = 0
    metadata_mismatch = 0
    for candidate in discovered:
        observation = candidate_observation(source, candidate)
        record = canonical_by_url.get(observation.detail_url)
        if not isinstance(record, dict):
            continue
        verified_at = _record_observed_at(record)
        if verified_at is None or verified_at > current:
            continue
        if current - verified_at > RECENT_DEEP_VERIFICATION_MAX_AGE:
            stale += 1
            continue
        if not _canonical_matches_discovery(source, candidate, record):
            metadata_mismatch += 1
            continue
        ledger = record_verification_success(
            ledger,
            observation,
            verified_at=verified_at,
        )
        seeded += 1

    incremental_runtime._save_ledger(cache, source, ledger)
    return {
        "action": "BOOTSTRAPPED",
        "source_id": source,
        "discovered_candidate_count": len(discovered),
        "seeded_verified_count": seeded,
        "stale_canonical_count": stale,
        "metadata_mismatch_count": metadata_mismatch,
    }
