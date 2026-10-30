"""Non-authoritative collector execution evidence (isolated C04 candidate).

Vercel RuntimeCache is a bounded, region-scoped *cache*, not an immutable
database. A missing/expired proof means UNKNOWN, never success or failure.
The application canonical-state, Queue lease and durable publisher stay the
authoritative mutation gates; evidence writes NEVER grant permission to publish.

Each stage/event has its own key: no shared read/modify/write status blob,
so Queue redelivery cannot overwrite a previous success with a later failure.
The 21-day TTL supports seven-day local audit readback when cache survives,
but does not guarantee a durable multi-day history: the final successful
snapshot can independently carry a bounded source witness into durable JSONB.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

from collector_schedule import valid_cycle, scheduled_cycle

PROOF_SCHEMA = "0.1"
PROOF_PREFIX = "medicalchannelai:collector-execution-proof:v1"
PROOF_TTL_SECONDS = 21 * 24 * 3600

EVENTS = frozenset({
    "TRIGGER_ACCEPTED",
    "STAGE_ENQUEUED",
    "STAGE_DELIVERED",
    "STAGE_COMPLETED",
    "STAGE_RETRY_ERROR",
    "STAGE_TERMINAL_FAILURE",
    "SNAPSHOT_CONFIRMED",
})
_STAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_ERROR_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_TAG = "medicalchannelai-collector-proof"


def _utc(when: datetime) -> datetime:
    if not isinstance(when, datetime) or when.tzinfo is None:
        raise ValueError("PROOF_TIME_INVALID")
    return when.astimezone(timezone.utc)


def _bounded_stage(stage: str) -> str:
    if not isinstance(stage, str) or not _STAGE_RE.fullmatch(stage):
        raise ValueError("PROOF_STAGE_INVALID")
    return stage


def _valid_context(cycle_id: str, anchor: datetime, stage: str, event: str) -> None:
    if not isinstance(cycle_id, str) or len(cycle_id) > 85 or not valid_cycle(cycle_id, _utc(anchor)):
        raise ValueError("PROOF_CYCLE_INVALID")
    _bounded_stage(stage)
    if event not in EVENTS:
        raise ValueError("PROOF_EVENT_INVALID")
    if event == "TRIGGER_ACCEPTED" and stage != "ccgp":
        raise ValueError("PROOF_TRIGGER_NOT_INITIAL_STAGE")
    if event == "SNAPSHOT_CONFIRMED" and stage != "publish":
        raise ValueError("PROOF_SNAPSHOT_NOT_PUBLISH")


def event_cache_key(cycle_id: str, stage: str, event: str) -> str:
    # A cycle token is not an API token; however don't expose untrusted parts
    # as a Cache key or namespace. Avoid secrets, credentials, URLs and query.
    raw = json.dumps([cycle_id, stage, event], ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{PROOF_PREFIX}:{digest}"


def _sanitize_fields(stage: str, event: str, fields: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(fields, dict):
        raise ValueError("PROOF_FIELDS_INVALID")
    if event == "SNAPSHOT_CONFIRMED":
        digest = fields.get("snapshot_sha256")
        raw_as_of = fields.get("snapshot_as_of")
        if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
            raise ValueError("PROOF_SNAPSHOT_HASH_INVALID")
        if not isinstance(raw_as_of, str) or len(raw_as_of) > 45:
            raise ValueError("PROOF_SNAPSHOT_AS_OF_INVALID")
        try:
            _utc(datetime.fromisoformat(raw_as_of.replace("Z", "+00:00")))
        except (ValueError, TypeError) as exc:
            raise ValueError("PROOF_SNAPSHOT_AS_OF_INVALID") from exc
        if fields.get("durable_snapshot_persisted") is not True:
            raise ValueError("PROOF_DURABLE_RECEIPT_REQUIRED")
        return {"snapshot_sha256": digest, "snapshot_as_of": raw_as_of}

    if event in {"STAGE_RETRY_ERROR", "STAGE_TERMINAL_FAILURE"}:
        code = fields.get("error_code")
        return {"error_code": code if isinstance(code, str) and _ERROR_RE.fullmatch(code) else "ERROR_CODE_UNAVAILABLE"}

    if event == "STAGE_COMPLETED":
        result = {}
        count = fields.get("failure_count")
        if type(count) is int and 0 <= count <= 1000000:
            result["failure_count"] = count
        verified = fields.get("verified_count")
        if type(verified) is int and 0 <= verified <= 1000000:
            result["verified_count"] = verified
        # A COMPLETED stage may report partial detail failures; it is not
        # evidence of full source coverage. Stage is not a source if "publish".
        result["source_quality"] = "NO_FAILURES_REPORTED" if count == 0 else "PARTIAL_OR_UNREPORTED"
        return result

    return {}


def record_event(
    cache: Any,
    *,
    cycle_id: str,
    cycle_as_of: datetime,
    stage: str,
    event: str,
    when: datetime,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a readback-checked witness for an action already taken.

    No retries, no write-ahead claims. Duplicate delivery is idempotent: the
    first well-formed stamp wins; an existing stamp is not modified.
    """
    _valid_context(cycle_id, cycle_as_of, stage, event)
    utc_when = _utc(when)
    payload = {
        "schema_version": PROOF_SCHEMA,
        "cycle_id": cycle_id,
        "cycle_as_of": _utc(cycle_as_of).isoformat(),
        "stage": stage,
        "event": event,
        "recorded_at": utc_when.isoformat(),
        **_sanitize_fields(stage, event, fields or {}),
    }
    key = event_cache_key(cycle_id, stage, event)
    previous = cache.get(key)
    if previous is not None:
        if (
            isinstance(previous, dict)
            and previous.get("schema_version") == PROOF_SCHEMA
            and previous.get("cycle_id") == cycle_id
            and previous.get("stage") == stage
            and previous.get("event") == event
            and previous.get("cycle_as_of") == payload["cycle_as_of"]
        ):
            return previous
        raise ValueError("PROOF_KEY_CONFLICT")

    cache.set(key, payload, {"ttl": PROOF_TTL_SECONDS, "tags": [_TAG]})
    readback = cache.get(key)
    if readback != payload:
        raise ValueError("PROOF_CACHE_READBACK_FAILED")
    return payload


def try_record(cache: Any, **kwargs: Any) -> bool:
    """Evidence is read-only diagnostic sidecar: failure never changes lease or publish."""
    try:
        record_event(cache, **kwargs)
        return True
    except Exception:
        return False


def read_event(cache: Any, cycle_id: str, stage: str, event: str) -> dict[str, Any] | None:
    if event not in EVENTS or not _STAGE_RE.fullmatch(str(stage or "")):
        return None
    try:
        value = cache.get(event_cache_key(cycle_id, stage, event))
    except Exception:
        return None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != PROOF_SCHEMA
        or value.get("cycle_id") != cycle_id
        or value.get("stage") != stage
        or value.get("event") != event
    ):
        return None
    return value


def audit_cycle(cache: Any, cycle_id: str, required_stages: Iterable[str], *, period: str, anchor: datetime) -> dict[str, Any]:
    """Small bounded proof summary, never a readiness or permission token."""
    if period not in {"morning", "noon"} or not valid_cycle(cycle_id, _utc(anchor)):
        raise ValueError("PROOF_CYCLE_INVALID")
    stages = list(dict.fromkeys(required_stages))
    if not stages or len(stages) > 40 or any(not _STAGE_RE.fullmatch(s) for s in stages):
        raise ValueError("PROOF_REQUIRED_STAGES_INVALID")
    accepted = read_event(cache, cycle_id, "ccgp", "TRIGGER_ACCEPTED")
    complete: dict[str, str] = {}
    failed = []
    unproven = []
    for stage in stages:
        end = read_event(cache, cycle_id, stage, "STAGE_COMPLETED")
        terminated = read_event(cache, cycle_id, stage, "STAGE_TERMINAL_FAILURE")
        delivered = read_event(cache, cycle_id, stage, "STAGE_DELIVERED")
        if terminated is not None:
            complete[stage] = "FAILED"
            failed.append(stage)
        elif end and delivered:
            complete[stage] = "COMPLETED"
        else:
            complete[stage] = "NO_EVIDENCE"
            unproven.append(stage)
    snapshot = read_event(cache, cycle_id, "publish", "SNAPSHOT_CONFIRMED")
    published = snapshot is not None and complete.get("publish") == "COMPLETED"
    passed = bool(accepted) and not failed and not unproven and published
    return {
        "schema_version": PROOF_SCHEMA,
        "cycle_id": cycle_id,
        "period": period,
        "state": (
            "PROOF_AVAILABLE" if passed else
            "RECORDED_FAILURE" if failed else
            "INCOMPLETE_OR_EXPIRED"
        ),
        "trigger_recorded": bool(accepted),
        "stage_status": complete,
        "missing_stages": unproven,
        "failed_stages": failed,
        "snapshot_readback_recorded": published,
        "snapshot_as_of": snapshot.get("snapshot_as_of") if snapshot else None,
        "snapshot_sha256": snapshot.get("snapshot_sha256") if snapshot else None,
        "storage": "RUNTIME_CACHE_21D_BEST_EFFORT_NOT_DURABLE_DB",
    }



def snapshot_source_witness(
    cache: Any,
    *,
    cycle_id: str,
    cycle_as_of: datetime,
    completed_stages: Iterable[str],
) -> dict[str, Any] | None:
    """Bounded pre-publish evidence that may be carried inside durable snapshot.

    The database receipt still determines publication success. This witness
    attests to an accepted trigger and observed delivery/completion of all
    the stages supplied by the authoritative runtime state, not to 100%
    market coverage or source-page completeness. A missing cache event
    means no witness (not automatic proof repair).
    """
    if not valid_cycle(cycle_id, _utc(cycle_as_of)):
        return None
    stages = list(dict.fromkeys(completed_stages))
    if not stages or len(stages) > 40 or "publish" in stages:
        return None
    if any(not _STAGE_RE.fullmatch(str(x or "")) for x in stages):
        return None
    trigger = read_event(cache, cycle_id, "ccgp", "TRIGGER_ACCEPTED")
    if trigger is None:
        return None
    proofs = []
    partial = False
    for stage in stages:
        delivered = read_event(cache, cycle_id, stage, "STAGE_DELIVERED")
        completed = read_event(cache, cycle_id, stage, "STAGE_COMPLETED")
        failed = read_event(cache, cycle_id, stage, "STAGE_TERMINAL_FAILURE")
        if not delivered or not completed or failed:
            return None
        if completed.get("source_quality") != "NO_FAILURES_REPORTED":
            partial = True
        proofs.append([stage, delivered["recorded_at"], completed["recorded_at"], completed.get("source_quality")])
    stable = json.dumps(
        [cycle_id, trigger["recorded_at"], proofs],
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return {
        "schema_version": PROOF_SCHEMA,
        "cycle_id": cycle_id,
        "trigger_accepted_at": trigger["recorded_at"],
        "witnessed_stage_count": len(proofs),
        "witness_sha256": hashlib.sha256(stable.encode("utf-8")).hexdigest(),
        "source_quality": "PARTIAL_OR_UNREPORTED" if partial else "NO_STAGE_FAILURES_REPORTED",
        "attestation_level": "CACHE_EVENTS_OBSERVED_BEFORE_DURABLE_PUBLISH",
    }


def recent_cycle_ids(now: datetime, lookback_days: int = 7) -> list[tuple[str, str, datetime]]:
    """Read-only calendar of expected cycles. Missing rows are UNKNOWN."""
    if not 1 <= lookback_days <= 7:
        raise ValueError("PROOF_LOOKBACK_OUT_OF_RANGE")
    from zoneinfo import ZoneInfo
    local = _utc(now).astimezone(ZoneInfo("Asia/Shanghai"))
    out = []
    for days_ago in range(lookback_days):
        day = local.date() - timedelta(days=days_ago)
        for period, hour in (("morning", 8), ("noon", 12)):
            candidate = datetime(day.year, day.month, day.day, hour, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
            if candidate > local:
                continue
            cycle_id, anchor = scheduled_cycle(candidate, period)
            out.append((cycle_id, period, anchor))
    return out
