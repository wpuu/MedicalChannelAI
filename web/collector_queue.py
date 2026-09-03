from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from vercel.functions import RuntimeCache
from vercel.queue import send

import collector_incremental_runtime as incremental_runtime
import collector_runtime as runtime
from collector_incremental_bootstrap import bootstrap_incremental_ledger_from_canonical
from collector_namespace import (
    ACTIVE_CYCLE_KEY,
    INCREMENTAL_ACTIVE_KEY,
    INCREMENTAL_ACTIVE_TTL_SECONDS,
    QUEUE_TOPIC_NAME,
    active_cycle_id,
    active_incremental_id,
    apply_runtime_namespace,
)

apply_runtime_namespace(runtime)
STAGE_ORDER = runtime.STAGE_ORDER

MESSAGE_RETENTION = timedelta(hours=24)
NEXT_STAGE_DELAY_SECONDS = 2


def _parse_cycle_as_of(payload: dict[str, Any]) -> datetime | None:
    raw = str(payload.get("cycle_as_of") or payload.get("observed_at") or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None else None


def _next_stage(stage: str) -> str | None:
    try:
        index = STAGE_ORDER.index(stage)
    except ValueError:
        return None
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None


def _active_cycle_matches(cycle_id: str) -> bool:
    value = RuntimeCache().get(ACTIVE_CYCLE_KEY)
    current = active_cycle_id(value)
    if current is None:
        raise RuntimeError("COLLECTOR_ACTIVE_CYCLE_MISSING")
    return current == cycle_id


def _release_active_cycle_if_owned(cycle_id: str) -> None:
    cache = RuntimeCache()
    if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) == cycle_id:
        cache.delete(ACTIVE_CYCLE_KEY)


async def _enqueue_stage(*, stage: str, cycle_as_of: datetime, cycle_id: str) -> str:
    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "stage": stage,
            "cycle_as_of": cycle_as_of.isoformat(),
            "cycle_id": cycle_id,
        },
        retention=MESSAGE_RETENTION,
        delay=NEXT_STAGE_DELAY_SECONDS if stage != "ccgp" else 0,
        idempotency_key=f"{QUEUE_TOPIC_NAME}:{cycle_id}:{stage}",
    )
    return str(message_id)


def _is_incremental_payload(payload: dict[str, Any]) -> bool:
    return str(payload.get("mode") or "").strip().lower() == "incremental"


def _acquire_incremental_lease(
    cache: RuntimeCache,
    *,
    source_id: str,
    bucket_id: str,
    observed_at: datetime,
) -> str:
    if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) is not None:
        raise RuntimeError("INCREMENTAL_BLOCKED_BY_DEEP_CYCLE")
    if active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY)) is not None:
        raise RuntimeError("INCREMENTAL_SCAN_ALREADY_RUNNING")

    scan_id = f"{bucket_id}:{observed_at.isoformat()}"
    cache.set(
        INCREMENTAL_ACTIVE_KEY,
        {
            "schema_version": "0.1",
            "scan_id": scan_id,
            "source_id": source_id,
            "bucket_id": bucket_id,
            "observed_at": observed_at.isoformat(),
        },
        {
            "ttl": INCREMENTAL_ACTIVE_TTL_SECONDS,
            "tags": ["medicalchannelai-collector-incremental-active"],
        },
    )
    if active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY)) != scan_id:
        raise RuntimeError("INCREMENTAL_LEASE_READBACK_FAILED")

    # Deep collection has priority. Recheck after acquiring our lease so a deep
    # cycle that started in the small gap above forces this scan to back out.
    if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) is not None:
        if active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY)) == scan_id:
            cache.delete(INCREMENTAL_ACTIVE_KEY)
        raise RuntimeError("INCREMENTAL_BLOCKED_BY_DEEP_CYCLE")
    return scan_id


def _release_incremental_lease(cache: RuntimeCache, scan_id: str) -> None:
    if active_incremental_id(cache.get(INCREMENTAL_ACTIVE_KEY)) == scan_id:
        cache.delete(INCREMENTAL_ACTIVE_KEY)


def _process_incremental_payload(payload: dict[str, Any]) -> None:
    source_id = str(payload.get("source_id") or "").strip().lower()
    observed_at = _parse_cycle_as_of(payload)
    expected_bucket = str(payload.get("scan_bucket_id") or "").strip()
    if (
        source_id not in incremental_runtime.SUPPORTED_INCREMENTAL_SOURCES
        or observed_at is None
        or not expected_bucket
    ):
        return

    actual_bucket = incremental_runtime.scan_bucket_id(source_id, now=observed_at)
    if actual_bucket != expected_bucket:
        return

    cache = RuntimeCache()
    scan_id = _acquire_incremental_lease(
        cache,
        source_id=source_id,
        bucket_id=expected_bucket,
        observed_at=observed_at,
    )
    try:
        # On the first incremental scan, bridge only very recent deep-collector
        # facts whose URL + index metadata still match. This prevents immediately
        # re-fetching details that the daily authoritative cycle just verified,
        # while metadata changes remain eligible for a fresh detail check.
        bootstrap_incremental_ledger_from_canonical(
            source_id,
            now=observed_at,
            cache=cache,
        )
        status, result = incremental_runtime.run_incremental_source(
            source_id,
            now=observed_at,
            cache=cache,
        )
    finally:
        _release_incremental_lease(cache, scan_id)

    action = str(result.get("action") or "")
    if status == 200 and action in {"COMPLETED", "ALREADY_SCANNED_BUCKET"}:
        return

    error = str(result.get("error") or "UNKNOWN")
    # 409 means the authoritative daily deep collector is currently writing its
    # own source caches. Raising lets the queue redeliver later instead of racing.
    # 503 covers discovery/detail/snapshot failures and is likewise retriable.
    raise RuntimeError(
        f"INCREMENTAL_QUEUE_SCAN_FAILED:{source_id}:{status}:{error[:180]}"
    )


async def process_collector_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        return

    if _is_incremental_payload(payload):
        _process_incremental_payload(payload)
        return

    stage = str(payload.get("stage") or "").strip().lower()
    cycle_id = str(payload.get("cycle_id") or "").strip()
    cycle_as_of = _parse_cycle_as_of(payload)
    if stage not in STAGE_ORDER or not cycle_id or cycle_as_of is None:
        return

    # Vercel Queues are at-least-once. A redelivery from an older accepted cycle
    # must be acknowledged without touching the current collector namespace.
    if not _active_cycle_matches(cycle_id):
        return

    status, result = runtime.run_stage(stage, now=cycle_as_of)
    action = str(result.get("action") or "")
    if status == 200 and action in {"COMPLETED", "ALREADY_COMPLETED_TODAY"}:
        next_stage = _next_stage(stage)
        if next_stage is not None:
            # Do not extend a cycle that was superseded while this stage ran.
            if not _active_cycle_matches(cycle_id):
                return
            await _enqueue_stage(stage=next_stage, cycle_as_of=cycle_as_of, cycle_id=cycle_id)
        else:
            # Publish is the terminal stage. Releasing the lease here makes the
            # completed deep cycle stop blocking later incremental scans.
            _release_active_cycle_if_owned(cycle_id)
        return

    error = str(result.get("error") or result.get("error_code") or "UNKNOWN")
    if status == 409 and "COLLECTOR_STAGE_RETRY_LIMIT" in error:
        # Two real attempts have already failed. Acknowledge this queue message,
        # release the mutation lease, and leave the status FAILED for diagnostics.
        _release_active_cycle_if_owned(cycle_id)
        return

    # Raising asks Vercel Queues to redeliver. The active-cycle fence above makes
    # delayed retries harmless after a newer cycle becomes authoritative.
    raise RuntimeError(f"COLLECTOR_QUEUE_STAGE_FAILED:{stage}:{status}:{error[:180]}")
