from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from vercel.functions import RuntimeCache
from vercel.queue import send

import collector_incremental_runtime as incremental_runtime
import collector_runtime as runtime
from collector_schedule import SCHEDULE_VERSION, valid_cycle
from collector_incremental import scan_bucket_id
from collector_incremental_bootstrap import bootstrap_incremental_ledger_from_canonical
from collector_incremental_scheduler import (
    choose_due_incremental_source,
    mark_incremental_source_attempt,
)
from collector_incremental_ticks import (
    BUSINESS_WINDOW_END,
    BUSINESS_WINDOW_START,
    SHANGHAI as TICK_SHANGHAI,
    IncrementalTick,
    first_tick_after_deep,
    next_tick_after,
    parse_tick_schedule,
    same_china_business_date,
    tick_delay_seconds,
    tick_from_payload,
)
from collector_namespace import (
    ACTIVE_CYCLE_KEY,
    INCREMENTAL_ACTIVE_KEY,
    INCREMENTAL_ACTIVE_TTL_SECONDS,
    INCREMENTAL_CHAIN_KEY,
    INCREMENTAL_CHAIN_TTL_SECONDS,
    META_KEY,
    QUEUE_TOPIC_NAME,
    active_cycle_id,
    active_incremental_id,
    apply_runtime_namespace,
    deep_message_lease_disposition,
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


def _active_cycle_matches(cycle_id: str, *, cycle_as_of: datetime) -> bool:
    cache = RuntimeCache()
    cycle_local_date = cycle_as_of.astimezone(TICK_SHANGHAI).date().isoformat()
    current_local_date = datetime.now(timezone.utc).astimezone(TICK_SHANGHAI).date().isoformat()
    disposition = deep_message_lease_disposition(
        cache.get(ACTIVE_CYCLE_KEY),
        cache.get(META_KEY),
        cycle_id=cycle_id,
        cycle_local_date=cycle_local_date,
        current_local_date=current_local_date,
    )
    if disposition == "MATCH":
        return True
    if disposition in {"SUPERSEDED", "COMPLETED_CYCLE", "ENDED_DEGRADED_CYCLE", "EXPIRED_STALE"}:
        return False
    raise RuntimeError("COLLECTOR_ACTIVE_CYCLE_MISSING")


def _release_active_cycle_if_owned(cycle_id: str) -> None:
    cache = RuntimeCache()
    if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) == cycle_id:
        cache.delete(ACTIVE_CYCLE_KEY)


def _write_chain_state(
    cache: RuntimeCache,
    *,
    state: str,
    business_date: str | None,
    tick_id: str | None = None,
    next_tick_id: str | None = None,
    selected_source: str | None = None,
    detail: str | None = None,
) -> None:
    cache.set(
        INCREMENTAL_CHAIN_KEY,
        {
            "schema_version": "0.1",
            "state": state,
            "business_date": business_date,
            "tick_id": tick_id,
            "next_tick_id": next_tick_id,
            "selected_source": selected_source,
            "detail": str(detail or "")[:180] or None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "ttl": INCREMENTAL_CHAIN_TTL_SECONDS,
            "tags": ["medicalchannelai-collector-incremental-chain"],
        },
    )


async def _enqueue_stage(*, stage: str, cycle_as_of: datetime, cycle_id: str) -> str:
    try:
        message_id = await send(
            QUEUE_TOPIC_NAME,
            {
                "schema_version": "0.1",
                "schedule_version": SCHEDULE_VERSION,
                "stage": stage,
                "cycle_as_of": cycle_as_of.isoformat(),
                "cycle_id": cycle_id,
            },
            retention=MESSAGE_RETENTION,
            delay=NEXT_STAGE_DELAY_SECONDS if stage != "ccgp" else 0,
            idempotency_key=f"{QUEUE_TOPIC_NAME}:{cycle_id}:{stage}",
        )
    except Exception as exc:
        # This SDK exception means Queue accepted this exact idempotency key.
        # Other transport/auth errors still propagate and remain retriable.
        if type(exc).__name__ != "DuplicateIdempotencyKeyError":
            raise
        message_id = "ALREADY_QUEUED"
    return str(message_id)


async def _enqueue_incremental_tick(tick: IncrementalTick, *, now: datetime) -> str:
    delay_seconds = tick_delay_seconds(tick, now=now)
    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "mode": "incremental_tick",
            "business_date": tick.business_date,
            "scheduled_for": tick.scheduled_for,
            "tick_id": tick.tick_id,
            "sequence": tick.sequence,
        },
        retention=MESSAGE_RETENTION,
        delay=delay_seconds,
        idempotency_key=f"{QUEUE_TOPIC_NAME}:{tick.tick_id}",
    )
    return str(message_id)


async def _enqueue_incremental_source(source_id: str, *, observed_at: datetime) -> str:
    bucket_id = scan_bucket_id(source_id, now=observed_at)
    message_id = await send(
        QUEUE_TOPIC_NAME,
        {
            "schema_version": "0.1",
            "mode": "incremental",
            "source_id": source_id,
            "observed_at": observed_at.isoformat(),
            "scan_bucket_id": bucket_id,
            "trigger_source": "INTRADAY_TICK",
        },
        retention=MESSAGE_RETENTION,
        idempotency_key=f"{QUEUE_TOPIC_NAME}:{bucket_id}",
    )
    return str(message_id)


def _is_incremental_payload(payload: dict[str, Any]) -> bool:
    return str(payload.get("mode") or "").strip().lower() == "incremental"


def _is_incremental_tick_payload(payload: dict[str, Any]) -> bool:
    return str(payload.get("mode") or "").strip().lower() == "incremental_tick"


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

    delivered_at = datetime.now(timezone.utc)
    if not same_china_business_date(observed_at, delivered_at):
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
        bootstrap_incremental_ledger_from_canonical(
            source_id,
            now=delivered_at,
            cache=cache,
        )
        status, result = incremental_runtime.run_incremental_source(
            source_id,
            now=delivered_at,
            cache=cache,
        )
    finally:
        _release_incremental_lease(cache, scan_id)

    action = str(result.get("action") or "")
    if status == 200 and action in {"COMPLETED", "ALREADY_SCANNED_BUCKET"}:
        return

    error = str(result.get("error") or "UNKNOWN")
    raise RuntimeError(
        f"INCREMENTAL_QUEUE_SCAN_FAILED:{source_id}:{status}:{error[:180]}"
    )


async def _process_incremental_tick_payload(payload: dict[str, Any]) -> None:
    tick = tick_from_payload(payload)
    if tick is None:
        return
    scheduled = parse_tick_schedule(tick)
    if scheduled is None:
        return

    now = datetime.now(timezone.utc)
    now_local = now.astimezone(TICK_SHANGHAI)
    if now_local.date().isoformat() != tick.business_date:
        return
    if now_local.time() < BUSINESS_WINDOW_START or now_local.time() > BUSINESS_WINDOW_END:
        return
    if now + timedelta(seconds=30) < scheduled:
        raise RuntimeError("INCREMENTAL_TICK_DELIVERED_EARLY")

    cache = RuntimeCache()
    next_tick = next_tick_after(tick, delivered_at=now)
    if next_tick is not None:
        await _enqueue_incremental_tick(next_tick, now=now)

    if active_cycle_id(cache.get(ACTIVE_CYCLE_KEY)) is not None:
        _write_chain_state(
            cache,
            state="DEFERRED_BY_DEEP_CYCLE",
            business_date=tick.business_date,
            tick_id=tick.tick_id,
            next_tick_id=next_tick.tick_id if next_tick else None,
        )
        return

    decision = choose_due_incremental_source(cache, now=now)
    if decision.source_id is None:
        _write_chain_state(
            cache,
            state="NO_SOURCE_DUE",
            business_date=tick.business_date,
            tick_id=tick.tick_id,
            next_tick_id=next_tick.tick_id if next_tick else None,
        )
        return

    await _enqueue_incremental_source(decision.source_id, observed_at=now)
    mark_incremental_source_attempt(cache, decision.source_id, now=now)
    _write_chain_state(
        cache,
        state="SOURCE_QUEUED",
        business_date=tick.business_date,
        tick_id=tick.tick_id,
        next_tick_id=next_tick.tick_id if next_tick else None,
        selected_source=decision.source_id,
    )


async def _start_intraday_chain_after_deep() -> None:
    cache = RuntimeCache()
    now = datetime.now(timezone.utc)
    first_tick = first_tick_after_deep(now)
    if first_tick is None:
        _write_chain_state(
            cache,
            state="WINDOW_CLOSED",
            business_date=now.astimezone(TICK_SHANGHAI).date().isoformat(),
        )
        return
    try:
        await _enqueue_incremental_tick(first_tick, now=now)
    except Exception as exc:
        _write_chain_state(
            cache,
            state="SCHEDULE_RETRY_PENDING",
            business_date=first_tick.business_date,
            tick_id=first_tick.tick_id,
            detail=f"{type(exc).__name__}:{str(exc)[:140]}",
        )
        raise
    _write_chain_state(
        cache,
        state="SCHEDULED",
        business_date=first_tick.business_date,
        next_tick_id=first_tick.tick_id,
    )


async def process_collector_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != "0.1":
        return

    # Acknowledge legacy backlog without executing it or creating continuations.
    if payload.get("schedule_version") != SCHEDULE_VERSION:
        return
    if _is_incremental_tick_payload(payload) or _is_incremental_payload(payload):
        return

    if _is_incremental_tick_payload(payload):
        await _process_incremental_tick_payload(payload)
        return

    if _is_incremental_payload(payload):
        _process_incremental_payload(payload)
        return

    stage = str(payload.get("stage") or "").strip().lower()
    cycle_id = str(payload.get("cycle_id") or "").strip()
    cycle_as_of = _parse_cycle_as_of(payload)
    if stage not in STAGE_ORDER or not cycle_id or cycle_as_of is None:
        return

    if not same_china_business_date(cycle_as_of, datetime.now(timezone.utc)):
        return
    if not valid_cycle(cycle_id, cycle_as_of):
        return
    if not _active_cycle_matches(cycle_id, cycle_as_of=cycle_as_of):
        return

    status, result = runtime.run_stage(stage, now=cycle_as_of, cycle_id=cycle_id)
    action = str(result.get("action") or "")
    if status == 200 and action in {"COMPLETED", "ALREADY_COMPLETED_TODAY"}:
        next_stage = _next_stage(stage)
        if next_stage is None:
            # Only a completed publish makes this cycle authoritative and clears
            # source-local staging. A degraded terminal cycle still gets its
            # intraday chain, but leaves incremental pending barriers intact.
            incremental_runtime.clear_incremental_pending(RuntimeCache())
            _release_active_cycle_if_owned(cycle_id)
            return
        if not _active_cycle_matches(cycle_id, cycle_as_of=cycle_as_of):
            return
        await _enqueue_stage(stage=next_stage, cycle_as_of=cycle_as_of, cycle_id=cycle_id)
        return

    if result.get("terminal") is True and action in {"FAILED", "BLOCKED"}:
        next_stage = _next_stage(stage)
        if next_stage is not None:
            if not _active_cycle_matches(cycle_id, cycle_as_of=cycle_as_of):
                return
            await _enqueue_stage(stage=next_stage, cycle_as_of=cycle_as_of, cycle_id=cycle_id)
        else:
            _release_active_cycle_if_owned(cycle_id)
        return

    error = str(result.get("error") or result.get("error_code") or "UNKNOWN")
    raise RuntimeError(f"COLLECTOR_QUEUE_STAGE_FAILED:{stage}:{status}:{error[:180]}")
