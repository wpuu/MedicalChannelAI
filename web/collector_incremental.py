from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


LEDGER_SCHEMA_VERSION = "0.1"

# Shared intraday planner defaults. The daily deep collector remains the
# authoritative bootstrap/reconciliation path, while higher-frequency scans keep
# discovery cheap: detail verification is only triggered by a new/changed
# candidate or by a bounded periodic recheck.
SOURCE_POLICIES: dict[str, dict[str, int]] = {
    "ccgp": {"scan_interval_minutes": 180, "reverify_after_hours": 24, "max_details_per_scan": 12},
    "tjmugh": {"scan_interval_minutes": 60, "reverify_after_hours": 24, "max_details_per_scan": 12},
    "tjnothop": {"scan_interval_minutes": 60, "reverify_after_hours": 24, "max_details_per_scan": 12},
    "teda": {"scan_interval_minutes": 120, "reverify_after_hours": 24, "max_details_per_scan": 12},
    "tjfch": {"scan_interval_minutes": 60, "reverify_after_hours": 24, "max_details_per_scan": 12},
    "tjfch_test": {"scan_interval_minutes": 60, "reverify_after_hours": 12, "max_details_per_scan": 12},
}


@dataclass(frozen=True)
class CandidateObservation:
    source_id: str
    detail_url: str
    title: str | None
    published_at: str | None
    index_url: str | None
    notice_type: str | None
    fingerprint: str


@dataclass(frozen=True)
class VerificationDecision:
    candidate: CandidateObservation
    reason: str
    priority: int


@dataclass(frozen=True)
class VerificationPlan:
    source_id: str
    observed_at: str
    selected: tuple[VerificationDecision, ...]
    deferred: tuple[VerificationDecision, ...]
    skipped_unchanged: tuple[CandidateObservation, ...]
    next_ledger: dict[str, dict[str, Any]]


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("INCREMENTAL_COLLECTOR_TIMEZONE_REQUIRED")
    return current.astimezone(timezone.utc)


def _text(value: Any, *, max_length: int = 1000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


def _candidate_value(candidate: Any, key: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key)
    return getattr(candidate, key, None)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def candidate_observation(source_id: str, candidate: Any) -> CandidateObservation:
    source = _text(source_id, max_length=80)
    detail_url = _text(_candidate_value(candidate, "detail_url"), max_length=2000)
    if not source or not detail_url or not detail_url.startswith("https://"):
        raise ValueError("INCREMENTAL_CANDIDATE_IDENTITY_INVALID")
    title = _text(_candidate_value(candidate, "title"), max_length=1000)
    published_at = _text(_candidate_value(candidate, "published_at"), max_length=100)
    index_url = _text(_candidate_value(candidate, "index_url"), max_length=2000)
    notice_type = _text(_candidate_value(candidate, "notice_type"), max_length=120)
    payload = {
        "source_id": source,
        "detail_url": detail_url,
        "title": title,
        "published_at": published_at,
        "index_url": index_url,
        "notice_type": notice_type,
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return CandidateObservation(
        source_id=source,
        detail_url=detail_url,
        title=title,
        published_at=published_at,
        index_url=index_url,
        notice_type=notice_type,
        fingerprint=digest,
    )


def ledger_key(observation: CandidateObservation) -> str:
    digest = hashlib.sha256(
        f"{observation.source_id}\n{observation.detail_url}".encode("utf-8")
    ).hexdigest()
    return f"{observation.source_id}:{digest}"


def empty_ledger() -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entries": {},
        "updated_at": None,
    }


def normalize_ledger(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != LEDGER_SCHEMA_VERSION:
        return empty_ledger()
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, dict):
        return empty_ledger()
    entries: dict[str, dict[str, Any]] = {}
    for key, row in raw_entries.items():
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        source_id = _text(row.get("source_id"), max_length=80)
        detail_url = _text(row.get("detail_url"), max_length=2000)
        fingerprint = _text(row.get("fingerprint"), max_length=64)
        if not source_id or not detail_url or not fingerprint:
            continue
        entries[key] = {
            "source_id": source_id,
            "detail_url": detail_url,
            "fingerprint": fingerprint,
            "title": _text(row.get("title"), max_length=1000),
            "published_at": _text(row.get("published_at"), max_length=100),
            "index_url": _text(row.get("index_url"), max_length=2000),
            "notice_type": _text(row.get("notice_type"), max_length=120),
            "first_seen_at": _text(row.get("first_seen_at"), max_length=100),
            "last_seen_at": _text(row.get("last_seen_at"), max_length=100),
            "last_verified_at": _text(row.get("last_verified_at"), max_length=100),
            "last_verification_fingerprint": _text(
                row.get("last_verification_fingerprint"), max_length=64
            ),
            "verification_status": _text(row.get("verification_status"), max_length=40),
            "verification_failure_count": max(0, int(row.get("verification_failure_count") or 0)),
            "last_error": _text(row.get("last_error"), max_length=300),
        }
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entries": entries,
        "updated_at": _text(value.get("updated_at"), max_length=100),
    }


def _parsed_at(value: Any) -> datetime | None:
    text = _text(value, max_length=100)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _verification_reason(
    entry: dict[str, Any] | None,
    observation: CandidateObservation,
    *,
    now: datetime,
    reverify_after: timedelta,
) -> tuple[str | None, int]:
    if entry is None:
        return "NEW_CANDIDATE", 0
    if entry.get("fingerprint") != observation.fingerprint:
        return "DISCOVERY_METADATA_CHANGED", 1
    if entry.get("verification_status") != "VERIFIED":
        return "NOT_CURRENTLY_VERIFIED", 2
    if entry.get("last_verification_fingerprint") != observation.fingerprint:
        return "DISCOVERY_NOT_VERIFIED", 2
    last_verified = _parsed_at(entry.get("last_verified_at"))
    if last_verified is None or now - last_verified >= reverify_after:
        return "PERIODIC_REVERIFY_DUE", 3
    return None, 99


def _observed_entry(
    existing: dict[str, Any] | None,
    observation: CandidateObservation,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "source_id": observation.source_id,
        "detail_url": observation.detail_url,
        "fingerprint": observation.fingerprint,
        "title": observation.title,
        "published_at": observation.published_at,
        "index_url": observation.index_url,
        "notice_type": observation.notice_type,
        "first_seen_at": existing.get("first_seen_at") if existing else observed_at,
        "last_seen_at": observed_at,
        "last_verified_at": existing.get("last_verified_at") if existing else None,
        "last_verification_fingerprint": (
            existing.get("last_verification_fingerprint") if existing else None
        ),
        "verification_status": existing.get("verification_status") if existing else "UNVERIFIED",
        "verification_failure_count": (
            max(0, int(existing.get("verification_failure_count") or 0)) if existing else 0
        ),
        "last_error": existing.get("last_error") if existing else None,
    }


def plan_detail_verification(
    source_id: str,
    candidates: Iterable[Any],
    ledger: Any,
    *,
    now: datetime | None = None,
    reverify_after_hours: int | None = None,
    max_details: int | None = None,
) -> VerificationPlan:
    observed = _utc(now)
    observed_at = observed.isoformat()
    policy = SOURCE_POLICIES.get(source_id, {})
    reverify_hours = int(
        reverify_after_hours
        if reverify_after_hours is not None
        else policy.get("reverify_after_hours", 24)
    )
    detail_cap = int(
        max_details if max_details is not None else policy.get("max_details_per_scan", 12)
    )
    if reverify_hours < 1 or detail_cap < 1:
        raise ValueError("INCREMENTAL_COLLECTOR_POLICY_INVALID")

    normalized = normalize_ledger(ledger)
    entries = dict(normalized["entries"])
    seen_urls: set[str] = set()
    decisions: list[VerificationDecision] = []
    skipped: list[CandidateObservation] = []

    for candidate in candidates:
        observation = candidate_observation(source_id, candidate)
        if observation.detail_url in seen_urls:
            continue
        seen_urls.add(observation.detail_url)
        key = ledger_key(observation)
        previous = entries.get(key)
        reason, priority = _verification_reason(
            previous,
            observation,
            now=observed,
            reverify_after=timedelta(hours=reverify_hours),
        )
        entries[key] = _observed_entry(previous, observation, observed_at)
        if reason is None:
            skipped.append(observation)
        else:
            decisions.append(VerificationDecision(observation, reason, priority))

    # Priority class remains authoritative, but within the same class verify the
    # newest official notices first. Source adapters normalize published_at to an
    # ISO-like value, so descending lexical order preserves recency; blank dates
    # stay behind dated candidates. Stable passes keep URL tie-breaking
    # deterministic without weakening the priority ordering.
    decisions.sort(key=lambda item: item.candidate.detail_url)
    decisions.sort(key=lambda item: item.candidate.published_at or "", reverse=True)
    decisions.sort(key=lambda item: item.priority)
    selected = tuple(decisions[:detail_cap])
    deferred = tuple(decisions[detail_cap:])
    return VerificationPlan(
        source_id=source_id,
        observed_at=observed_at,
        selected=selected,
        deferred=deferred,
        skipped_unchanged=tuple(skipped),
        next_ledger={
            "schema_version": LEDGER_SCHEMA_VERSION,
            "entries": entries,
            "updated_at": observed_at,
        },
    )


def record_verification_success(
    ledger: Any,
    observation: CandidateObservation,
    *,
    verified_at: datetime | None = None,
) -> dict[str, Any]:
    current = normalize_ledger(ledger)
    when = _utc(verified_at).isoformat()
    key = ledger_key(observation)
    entry = current["entries"].get(key)
    if entry is None:
        entry = _observed_entry(None, observation, when)
    entry = dict(entry)
    entry.update(
        {
            "fingerprint": observation.fingerprint,
            "last_seen_at": max(entry.get("last_seen_at") or when, when),
            "last_verified_at": when,
            "last_verification_fingerprint": observation.fingerprint,
            "verification_status": "VERIFIED",
            "verification_failure_count": 0,
            "last_error": None,
        }
    )
    entries = dict(current["entries"])
    entries[key] = entry
    return {"schema_version": LEDGER_SCHEMA_VERSION, "entries": entries, "updated_at": when}


def record_verification_failure(
    ledger: Any,
    observation: CandidateObservation,
    error: str,
    *,
    failed_at: datetime | None = None,
) -> dict[str, Any]:
    current = normalize_ledger(ledger)
    when = _utc(failed_at).isoformat()
    key = ledger_key(observation)
    entry = current["entries"].get(key)
    if entry is None:
        entry = _observed_entry(None, observation, when)
    entry = dict(entry)
    entry.update(
        {
            "fingerprint": observation.fingerprint,
            "last_seen_at": max(entry.get("last_seen_at") or when, when),
            "verification_status": "FAILED",
            "verification_failure_count": max(
                0, int(entry.get("verification_failure_count") or 0)
            ) + 1,
            "last_error": _text(error, max_length=300),
        }
    )
    entries = dict(current["entries"])
    entries[key] = entry
    return {"schema_version": LEDGER_SCHEMA_VERSION, "entries": entries, "updated_at": when}


def scan_bucket_id(
    source_id: str,
    *,
    now: datetime | None = None,
    interval_minutes: int | None = None,
) -> str:
    current = _utc(now)
    policy = SOURCE_POLICIES.get(source_id, {})
    interval = int(
        interval_minutes
        if interval_minutes is not None
        else policy.get("scan_interval_minutes", 60)
    )
    if interval < 1 or interval > 24 * 60:
        raise ValueError("INCREMENTAL_COLLECTOR_INTERVAL_INVALID")
    minute_of_day = current.hour * 60 + current.minute
    bucket_minute = (minute_of_day // interval) * interval
    bucket_hour, minute = divmod(bucket_minute, 60)
    day = current.date().isoformat().replace("-", "")
    return f"scan:{source_id}:{day}T{bucket_hour:02d}{minute:02d}Z:{interval}m"
