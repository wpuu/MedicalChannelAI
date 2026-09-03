from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


LEDGER_SCHEMA_VERSION = "0.1"
LEDGER_ENTRY_RETENTION_DAYS = 45
PENDING_CARRYOVER_MAX_AGE_HOURS = 48

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


def _prune_entries(entries: dict[str, dict[str, Any]], *, now: datetime) -> dict[str, dict[str, Any]]:
    cutoff = now - timedelta(days=LEDGER_ENTRY_RETENTION_DAYS)
    retained: dict[str, dict[str, Any]] = {}
    for key, entry in entries.items():
        last_seen = _parsed_at(entry.get("last_seen_at"))
        if last_seen is None or last_seen < cutoff or last_seen > now:
            continue
        retained[key] = entry
    return retained


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


def _carryover_observation(source_id: str, entry: dict[str, Any]) -> CandidateObservation | None:
    try:
        observation = candidate_observation(source_id, entry)
    except ValueError:
        return None
    if observation.fingerprint != entry.get("fingerprint"):
        return None
    return observation


def _sort_decisions(decisions: list[VerificationDecision]) -> None:
    # Priority class remains authoritative, but within the same class verify the
    # newest official notices first. Source adapters normalize published_at to an
    # ISO-like value, so descending lexical order preserves recency; blank dates
    # stay behind dated candidates. Stable passes keep URL tie-breaking
    # deterministic without weakening the priority ordering.
    decisions.sort(key=lambda item: item.candidate.detail_url)
    decisions.sort(key=lambda item: item.candidate.published_at or "", reverse=True)
    decisions.sort(key=lambda item: item.priority)


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
    entries = _prune_entries(dict(normalized["entries"]), now=observed)
    seen_urls: set[str] = set()
    decisions: list[VerificationDecision] = []
    carryover: list[VerificationDecision] = []
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

    # Discovery adapters intentionally cap each index scan. A newly observed URL
    # may therefore be deferred by the detail budget and disappear from the next
    # capped index window before it is verified. Carry unresolved, recently seen
    # ledger rows across that truncation boundary. This is bounded to 48 hours;
    # the daily deep collector remains the long-tail reconciliation authority.
    carryover_cutoff = observed - timedelta(hours=PENDING_CARRYOVER_MAX_AGE_HOURS)
    for entry in entries.values():
        detail_url = _text(entry.get("detail_url"), max_length=2000)
        if not detail_url or detail_url in seen_urls:
            continue
        if entry.get("verification_status") == "VERIFIED" and (
            entry.get("last_verification_fingerprint") == entry.get("fingerprint")
        ):
            continue
        last_seen = _parsed_at(entry.get("last_seen_at"))
        if last_seen is None or last_seen < carryover_cutoff or last_seen > observed:
            continue
        observation = _carryover_observation(source_id, entry)
        if observation is None:
            continue
        carryover.append(VerificationDecision(observation, "PENDING_CARRYOVER", 2))

    _sort_decisions(decisions)
    _sort_decisions(carryover)

    # Preserve freshness while guaranteeing bounded backlog progress. With the
    # default 12-detail budget, at most 3 slots are reserved for carryover. If
    # current discovery needs fewer slots, unused capacity is immediately given
    # back to carryover so an idle source drains its backlog as quickly as safe.
    reserved_carryover = min(len(carryover), max(1, detail_cap // 4)) if carryover else 0
    current_budget = max(0, detail_cap - reserved_carryover)
    selected_current = decisions[:current_budget]
    selected_carryover = carryover[:reserved_carryover]
    remaining_capacity = detail_cap - len(selected_current) - len(selected_carryover)
    if remaining_capacity > 0:
        selected_carryover.extend(carryover[reserved_carryover:reserved_carryover + remaining_capacity])
    selected_carryover_count = len(selected_carryover)
    remaining_capacity = detail_cap - len(selected_current) - selected_carryover_count
    if remaining_capacity > 0:
        selected_current.extend(decisions[current_budget:current_budget + remaining_capacity])

    selected = tuple([*selected_current, *selected_carryover])
    selected_urls = {item.candidate.detail_url for item in selected}
    deferred = tuple(
        item
        for item in [*decisions, *carryover]
        if item.candidate.detail_url not in selected_urls
    )
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
    current_time = _utc(verified_at)
    when = current_time.isoformat()
    entries = _prune_entries(dict(current["entries"]), now=current_time)
    key = ledger_key(observation)
    entry = entries.get(key)
    if entry is None:
        entry = _observed_entry(None, observation, when)
    entry = dict(entry)
    entry.update(
        {
            "fingerprint": observation.fingerprint,
            "last_verified_at": when,
            "last_verification_fingerprint": observation.fingerprint,
            "verification_status": "VERIFIED",
            "verification_failure_count": 0,
            "last_error": None,
        }
    )
    entries[key] = entry
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entries": entries,
        "updated_at": when,
    }


def record_verification_failure(
    ledger: Any,
    observation: CandidateObservation,
    error: str,
    *,
    failed_at: datetime | None = None,
) -> dict[str, Any]:
    current = normalize_ledger(ledger)
    current_time = _utc(failed_at)
    when = current_time.isoformat()
    entries = _prune_entries(dict(current["entries"]), now=current_time)
    key = ledger_key(observation)
    entry = entries.get(key)
    if entry is None:
        entry = _observed_entry(None, observation, when)
    entry = dict(entry)
    entry.update(
        {
            "fingerprint": observation.fingerprint,
            "verification_status": "FAILED",
            "verification_failure_count": max(
                0, int(entry.get("verification_failure_count") or 0)
            ) + 1,
            "last_error": _text(error, max_length=300),
        }
    )
    entries[key] = entry
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entries": entries,
        "updated_at": when,
    }


def scan_bucket_id(
    source_id: str,
    *,
    now: datetime | None = None,
    interval_minutes: int | None = None,
) -> str:
    current = _utc(now)
    policy = SOURCE_POLICIES.get(source_id, {})
    minutes = int(
        interval_minutes if interval_minutes is not None else policy.get("scan_interval_minutes", 60)
    )
    if minutes < 1:
        raise ValueError("INCREMENTAL_SCAN_INTERVAL_INVALID")
    epoch_minutes = int(current.timestamp() // 60)
    bucket = epoch_minutes // minutes
    return f"{source_id}:{minutes}m:{bucket}"
